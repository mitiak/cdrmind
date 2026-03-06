from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import openai
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_client() -> openai.AsyncOpenAI:
    settings = get_settings()
    return openai.AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_secs,
    )


@retry(
    retry=retry_if_not_exception_type(openai.RateLimitError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def complete(
    prompt: str,
    *,
    caller: str = "",
    system: str = "You are a security analyst assistant. Be precise and factual.",
    max_tokens: int | None = None,
    temperature: float = 0.1,
) -> str:
    settings = get_settings()
    client = get_client()
    if max_tokens is None:
        max_tokens = settings.llm_max_tokens

    logger.info("llm.complete.started", caller=caller, model=settings.llm_model, prompt_len=len(prompt))
    try:
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except openai.RateLimitError as exc:
        meta: dict[str, Any] = {}
        if exc.body and isinstance(exc.body, dict):
            meta = exc.body.get("error", {}).get("metadata", {}).get("headers", {})
        reset_ms = int(meta.get("X-RateLimit-Reset", 0))
        reset_dt = (
            datetime.fromtimestamp(reset_ms / 1000, UTC).isoformat()
            if reset_ms else "unknown"
        )
        logger.warning(
            "llm.rate_limited",
            caller=caller,
            model=settings.llm_model,
            limit=meta.get("X-RateLimit-Limit"),
            remaining=meta.get("X-RateLimit-Remaining"),
            reset=reset_dt,
        )
        raise
    result = resp.choices[0].message.content or ""
    logger.info("llm.complete.done", caller=caller, output_len=len(result), result=result)
    return result


async def complete_json(
    prompt: str,
    *,
    caller: str = "",
    system: str = "You are a security analyst assistant. Respond ONLY with valid JSON.",
    max_tokens: int | None = None,
) -> dict[str, Any]:
    raw = await complete(prompt, caller=caller, system=system, max_tokens=max_tokens)
    # Strip markdown code fences if present
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        # remove first and last fence lines
        inner = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        stripped = inner.strip()
    data: dict[str, Any] = json.loads(stripped)
    return data
