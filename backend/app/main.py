from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, load_settings
from app.database import (
    close_db,
    get_history_for_llm,
    get_session_messages,
    init_db,
    save_message,
    session_exists,
)
from app.llm_service import AllKeysFailedError, call_llm, setup_cache
from app.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    MessageEntry,
    ResponseMetadata,
    SessionMessagesResponse,
)

settings: Settings = load_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_cache()
    await init_db(settings.db_path)
    yield
    # Shutdown
    await close_db()


app = FastAPI(title="LLM Chatbot API", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Error handlers ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    messages = []
    for err in errors:
        loc = " -> ".join(str(l) for l in err.get("loc", []) if l != "body")
        msg = err.get("msg", "")
        if loc:
            messages.append(f"{loc}: {msg}")
        else:
            messages.append(msg)
    detail = "; ".join(messages) if messages else str(exc)
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


# --- Endpoints ---

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        keys_configured=len(settings.llm_api_keys),
        cache_enabled=True,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure"),
):
    # Build messages list for LLM
    llm_messages: list[dict] = []

    # System prompt
    if body.system_prompt:
        llm_messages.append({"role": "system", "content": body.system_prompt})

    # Load history from SQLite
    history = await get_history_for_llm(body.session_id)
    llm_messages.extend(history)

    # Append new user message
    llm_messages.append({"role": "user", "content": body.message})

    try:
        result = await call_llm(
            settings=settings,
            messages=llm_messages,
            simulate_failure_header=x_simulate_failure,
        )
    except AllKeysFailedError:
        raise HTTPException(status_code=503, detail="all providers unavailable")

    # Save user message and assistant reply to SQLite
    await save_message(body.session_id, "user", body.message)

    assistant_meta = {
        "resolution_source": result.resolution_source,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
    }
    await save_message(body.session_id, "assistant", result.reply, metadata=assistant_meta)

    return ChatResponse(
        session_id=body.session_id,
        reply=result.reply,
        metadata=ResponseMetadata(
            resolution_source=result.resolution_source,
            model=result.model,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            key_id=result.key_id,
            fallback_attempts=result.fallback_attempts,
        ),
    )


@app.get("/sessions/{session_id}/messages", response_model=SessionMessagesResponse)
async def get_messages(session_id: str):
    exists = await session_exists(session_id)
    if not exists:
        raise HTTPException(status_code=404, detail="session not found")

    rows = await get_session_messages(session_id)
    messages = []
    for row in rows:
        messages.append(
            MessageEntry(
                role=row["role"],
                content=row["content"],
                metadata=row.get("metadata"),
            )
        )

    return SessionMessagesResponse(session_id=session_id, messages=messages)
