"""Backend tests using pytest + httpx against the FastAPI app."""
from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Set env vars BEFORE importing the app
os.environ["LLM_API_KEYS"] = "test-key-1,test-key-2"
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"
os.environ["LLM_MODEL"] = "gemini/gemini-2.0-flash"

# Use a temp database for tests
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db_path = _tmp_db.name
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db_path}"


def _make_mock_response(content: str, cache_hit: bool = False, prompt_tokens: int = 42, completion_tokens: int = 9):
    """Create a mock LiteLLM response."""
    msg = MagicMock()
    msg.content = content

    choice = MagicMock()
    choice.message = msg

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp._hidden_params = {"cache_hit": cache_hit}
    return resp


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
async def client():
    # Setup DB and cache before client runs
    from app.config import load_settings
    from app.database import init_db, close_db
    from app.llm_service import setup_cache
    from app.main import app

    settings = load_settings()
    setup_cache()
    await init_db(settings.db_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await close_db()


@pytest.mark.anyio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["keys_configured"] == 2
    assert data["cache_enabled"] is True


@pytest.mark.anyio
async def test_chat_missing_message(client: AsyncClient):
    resp = await client.post("/chat", json={"session_id": "s-1"})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_chat_empty_message(client: AsyncClient):
    resp = await client.post("/chat", json={"session_id": "s-1", "message": "   "})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_chat_message_too_long(client: AsyncClient):
    resp = await client.post("/chat", json={"session_id": "s-1", "message": "a" * 4001})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_chat_missing_session_id(client: AsyncClient):
    resp = await client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_session_not_found(client: AsyncClient):
    resp = await client.get("/sessions/nonexistent-session/messages")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "session not found"


@pytest.mark.anyio
@patch("app.llm_service.litellm.acompletion", new_callable=AsyncMock)
async def test_chat_success(mock_completion, client: AsyncClient):
    mock_completion.return_value = _make_mock_response("The capital of France is Paris.")

    resp = await client.post("/chat", json={
        "session_id": "s-test-1",
        "message": "What is the capital of France?",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "s-test-1"
    assert data["reply"] == "The capital of France is Paris."
    assert data["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert data["metadata"]["key_id"] == "key_1"
    assert data["metadata"]["input_tokens"] == 42
    assert data["metadata"]["output_tokens"] == 9
    assert data["metadata"]["fallback_attempts"] == 0


@pytest.mark.anyio
@patch("app.llm_service.litellm.acompletion", new_callable=AsyncMock)
async def test_chat_cache_hit(mock_completion, client: AsyncClient):
    mock_completion.return_value = _make_mock_response("Cached answer", cache_hit=True)

    resp = await client.post("/chat", json={
        "session_id": "s-test-cache",
        "message": "cached question",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["resolution_source"] == "LLM_CACHE"
    assert data["metadata"]["key_id"] is None
    assert data["metadata"]["fallback_attempts"] == 0


@pytest.mark.anyio
async def test_chat_simulate_failure_single_key(client: AsyncClient):
    """Simulate key_1 failure, key_2 should succeed."""
    with patch("app.llm_service.litellm.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = _make_mock_response("Fallback reply")

        resp = await client.post(
            "/chat",
            json={"session_id": "s-failover-1", "message": "test failover"},
            headers={"X-Simulate-Failure": "key_1=429"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"]["key_id"] == "key_2"
        assert data["metadata"]["fallback_attempts"] == 1


@pytest.mark.anyio
async def test_chat_simulate_failure_all_keys(client: AsyncClient):
    """Simulate all keys failing → 503."""
    resp = await client.post(
        "/chat",
        json={"session_id": "s-failover-all", "message": "test all fail"},
        headers={"X-Simulate-Failure": "*=429"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "all providers unavailable"


@pytest.mark.anyio
@patch("app.llm_service.litellm.acompletion", new_callable=AsyncMock)
async def test_session_messages(mock_completion, client: AsyncClient):
    mock_completion.return_value = _make_mock_response("Reply for history test")

    # Send a message to create session
    resp = await client.post("/chat", json={
        "session_id": "s-history-1",
        "message": "Hello history",
    })
    assert resp.status_code == 200

    # Retrieve session messages
    resp = await client.get("/sessions/s-history-1/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "s-history-1"
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "Hello history"
    assert data["messages"][1]["role"] == "assistant"
    assert data["messages"][1]["content"] == "Reply for history test"
    assert data["messages"][1]["metadata"]["resolution_source"] == "LIVE_INFERENCE"


@pytest.mark.anyio
@patch("app.llm_service.litellm.acompletion", new_callable=AsyncMock)
async def test_multi_turn(mock_completion, client: AsyncClient):
    """Verify that multi-turn sends accumulated history to LLM."""
    mock_completion.return_value = _make_mock_response("Turn 1 reply")

    # First turn
    await client.post("/chat", json={
        "session_id": "s-multi-1",
        "message": "First message",
    })

    mock_completion.return_value = _make_mock_response("Turn 2 reply")

    # Second turn
    resp = await client.post("/chat", json={
        "session_id": "s-multi-1",
        "message": "Second message",
    })
    assert resp.status_code == 200

    # Verify LLM was called with history
    call_args = mock_completion.call_args
    messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
    # Should have: user "First message", assistant "Turn 1 reply", user "Second message"
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "First message"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Turn 1 reply"
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "Second message"


@pytest.mark.anyio
@patch("app.llm_service.litellm.acompletion", new_callable=AsyncMock)
async def test_system_prompt(mock_completion, client: AsyncClient):
    mock_completion.return_value = _make_mock_response("System prompt reply")

    resp = await client.post("/chat", json={
        "session_id": "s-sys-1",
        "message": "Hello",
        "system_prompt": "You are a helpful bot",
    })
    assert resp.status_code == 200

    call_args = mock_completion.call_args
    messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are a helpful bot"


@pytest.mark.anyio
async def test_malformed_json(client: AsyncClient):
    resp = await client.post(
        "/chat",
        content="this is not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "detail" in data


@pytest.mark.anyio
async def test_no_html_error(client: AsyncClient):
    """Error responses should never contain HTML."""
    resp = await client.post("/chat", json={"session_id": "s-1"})
    assert resp.status_code == 422
    assert "text/html" not in resp.headers.get("content-type", "")
    assert "<html" not in resp.text.lower()


@pytest.mark.anyio
async def test_failed_request_not_in_history(client: AsyncClient):
    """422 and 503 should NOT add messages to session history."""
    sid = "s-no-history-on-fail"

    # This will 422 because message is missing
    resp = await client.post("/chat", json={"session_id": sid})
    assert resp.status_code == 422

    # Session should not exist
    resp = await client.get(f"/sessions/{sid}/messages")
    assert resp.status_code == 404
