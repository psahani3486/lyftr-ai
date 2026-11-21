from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import litellm
from litellm import Cache

from app.config import Settings

# Suppress litellm debug noise
litellm.suppress_debug_info = True


@dataclass
class LLMResult:
    reply: str
    resolution_source: str  # "LIVE_INFERENCE" or "LLM_CACHE"
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: Optional[str]
    fallback_attempts: int


class SimulatedFailure(Exception):
    def __init__(self, status: int, key_id: str):
        self.status = status
        self.key_id = key_id
        super().__init__(f"Simulated {status} for {key_id}")


def _parse_failure_header(header: str) -> Dict[str, int]:
    """Parse 'key_1=429,key_2=500' or '*=429' into dict."""
    mapping: Dict[str, int] = {}
    for part in header.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        kid, status_str = part.split("=", 1)
        kid = kid.strip()
        status_str = status_str.strip()
        try:
            mapping[kid] = int(status_str)
        except ValueError:
            continue
    return mapping


def setup_cache() -> None:
    """Enable LiteLLM in-memory caching."""
    litellm.cache = Cache(type="local")


async def call_llm(
    settings: Settings,
    messages: List[dict],
    simulate_failure_header: Optional[str] = None,
) -> LLMResult:
    """Call LLM with key failover. Returns LLMResult."""
    keys = settings.llm_api_keys
    key_ids = settings.key_ids
    model = settings.llm_model

    failure_map: Dict[str, int] = {}
    if settings.enable_failure_simulation and simulate_failure_header:
        failure_map = _parse_failure_header(simulate_failure_header)

    fallback_attempts = 0
    last_error: Optional[Exception] = None

    for idx, (api_key, key_id) in enumerate(zip(keys, key_ids)):
        # Check simulation
        if failure_map:
            sim_status = failure_map.get(key_id) or failure_map.get("*")
            if sim_status:
                fallback_attempts += 1
                last_error = SimulatedFailure(sim_status, key_id)
                continue

        try:
            start = time.perf_counter()
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                api_key=api_key,
                caching=True,
            )
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            # Determine cache hit
            cache_hit = False
            if hasattr(response, "_hidden_params") and isinstance(response._hidden_params, dict):
                cache_hit = response._hidden_params.get("cache_hit", False)

            reply_text = response.choices[0].message.content or ""
            usage = response.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0

            if cache_hit:
                return LLMResult(
                    reply=reply_text,
                    resolution_source="LLM_CACHE",
                    model=model,
                    latency_ms=elapsed_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    key_id=None,
                    fallback_attempts=fallback_attempts,
                )
            else:
                return LLMResult(
                    reply=reply_text,
                    resolution_source="LIVE_INFERENCE",
                    model=model,
                    latency_ms=elapsed_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    key_id=key_id,
                    fallback_attempts=fallback_attempts,
                )

        except Exception as exc:
            fallback_attempts += 1
            last_error = exc
            # Check if retryable (429, 5xx)
            status_code = getattr(exc, "status_code", None)
            if status_code is not None and status_code in (429, 500, 502, 503):
                continue
            # LiteLLM wraps errors — check for quota / rate limit strings
            err_msg = str(exc).lower()
            if any(kw in err_msg for kw in ("rate_limit", "ratelimit", "quota", "429", "500", "502", "503")):
                continue
            # Non-retryable error — still try next key as safety net
            continue

    # All keys exhausted
    raise AllKeysFailedError("all providers unavailable")


class AllKeysFailedError(Exception):
    pass
