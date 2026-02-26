"""Hallucination scorer: detect facts in report not present in source logs."""
from __future__ import annotations

import re


# Patterns that look like facts (IPs, usernames, ARNs, resource names)
_IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_ARN_PATTERN = re.compile(r"arn:aws:[a-z0-9:/_-]+")
_EMAIL_PATTERN = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Z|a-z]{2,}\b")
_USERNAME_PATTERN = re.compile(r"\b[a-z][a-z0-9._-]{3,30}\b")


def _extract_facts(text: str) -> set[str]:
    facts: set[str] = set()
    facts.update(_IP_PATTERN.findall(text))
    facts.update(arn.lower() for arn in _ARN_PATTERN.findall(text))
    facts.update(e.lower() for e in _EMAIL_PATTERN.findall(text))
    return facts


def score_hallucination_ci(report_text: str, logs_text: str, rag_context: str = "") -> float:
    """
    CI mode: detect proper nouns / IPs / ARNs in report not present in logs + RAG context.
    Returns hallucination rate (0.0 = no hallucinations, 1.0 = all facts hallucinated).
    Threshold: < 0.20.
    """
    report_facts = _extract_facts(report_text)
    source_text = logs_text + " " + rag_context
    source_facts = _extract_facts(source_text)

    if not report_facts:
        return 0.0

    hallucinated = report_facts - source_facts
    return len(hallucinated) / len(report_facts)


async def score_hallucination_llm(report_text: str, logs_text: str) -> float:
    """Full eval mode: LLM-as-judge hallucination detection."""
    from app.services import llm

    prompt = f"""You are evaluating whether an incident report contains fabricated facts not in the source logs.

Source logs:
<<<LOGS START>>>
{logs_text[:3000]}
<<<LOGS END>>>

Incident report:
{report_text[:2000]}

Identify any specific claims (IP addresses, usernames, resource names, times, actions) in the report
that are NOT supported by the source logs.
Return JSON: {{"hallucinated_facts": ["<fact1>", ...], "hallucination_rate": <0.0-1.0>, "reasoning": "<brief>"}}"""

    try:
        result = await llm.complete_json(prompt)
        return float(result.get("hallucination_rate", 0.0))
    except Exception:
        return score_hallucination_ci(report_text, logs_text)
