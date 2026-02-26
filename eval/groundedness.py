"""Groundedness scorer: are report claims supported by the source logs?"""
from __future__ import annotations

import re
from collections import Counter


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-zA-Z0-9._/-]{2,}\b", text.lower())


def score_groundedness_ci(report_text: str, logs_text: str) -> float:
    """
    CI mode: token overlap between report and logs.
    Returns 0.0–1.0. Threshold: >= 0.60.
    """
    report_tokens = set(_tokenize(report_text))
    log_tokens = set(_tokenize(logs_text))
    if not report_tokens:
        return 0.0
    overlap = report_tokens & log_tokens
    return len(overlap) / len(report_tokens)


async def score_groundedness_llm(report_text: str, logs_text: str) -> float:
    """Full eval mode: LLM-as-judge groundedness scoring."""
    from app.services import llm

    prompt = f"""You are evaluating whether an incident report is grounded in the source logs.

Source logs:
<<<LOGS START>>>
{logs_text[:3000]}
<<<LOGS END>>>

Incident report:
{report_text[:2000]}

For each major claim in the report, determine if it is supported by the logs.
Return JSON: {{"grounded_claims": <int>, "total_claims": <int>, "score": <0.0-1.0>, "reasoning": "<brief>"}}"""

    try:
        result = await llm.complete_json(prompt)
        return float(result.get("score", 0.0))
    except Exception:
        return score_groundedness_ci(report_text, logs_text)
