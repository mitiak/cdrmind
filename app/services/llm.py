from __future__ import annotations

import json
from typing import Any

import openai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_client() -> openai.AsyncOpenAI:
    settings = get_settings()
    return openai.AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def complete(
    prompt: str,
    *,
    system: str = "You are a security analyst assistant. Be precise and factual.",
    max_tokens: int | None = None,
    temperature: float = 0.1,
) -> str:
    settings = get_settings()
    client = get_client()
    if max_tokens is None:
        max_tokens = settings.llm_max_tokens

    logger.info("llm.complete.started", model=settings.llm_model, prompt_len=len(prompt))
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    result = resp.choices[0].message.content or ""
    logger.info("llm.complete.done", output_len=len(result))
    return result


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def complete_json(
    prompt: str,
    *,
    system: str = "You are a security analyst assistant. Respond ONLY with valid JSON.",
    max_tokens: int | None = None,
) -> dict[str, Any]:
    raw = await complete(prompt, system=system, max_tokens=max_tokens)
    # Strip markdown code fences if present
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        # remove first and last fence lines
        inner = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        stripped = inner.strip()
    data: dict[str, Any] = json.loads(stripped)
    return data
