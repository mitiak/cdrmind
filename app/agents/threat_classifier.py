from __future__ import annotations

import json
from typing import Any

from app.core.security import wrap_logs_for_prompt
from app.schemas.agent import SocAgentRequest, SocAgentResponse
from app.services import llm
from app.services.raggy_client import RaggyClient

_CLASSIFY_SYSTEM = (
    "You are a threat intelligence analyst specializing in MITRE ATT&CK framework. "
    "Respond ONLY with valid JSON."
)

_CLASSIFY_PROMPT = """Classify the security threats in the following log summary and context.

Log Summary:
{log_summary}

{logs_block}

Relevant MITRE ATT&CK context from knowledge base:
{rag_context}

Return a JSON object with:
{{
  "threat_indicators": [
    {{"indicator": "<description>", "confidence": <0.0-1.0>, "evidence": "<log reference>"}}
  ],
  "mitre_tactics": [
    {{"id": "<T####>", "name": "<tactic name>", "description": "<why this applies>"}}
  ],
  "risk_score": <0.0-10.0>,
  "rag_context": [
    {{"title": "<doc title>", "relevance": "<why relevant>"}}
  ],
  "reasoning": "<classification rationale>"
}}"""


async def classify_threats(request: SocAgentRequest, raggy: RaggyClient | None = None) -> SocAgentResponse:
    if raggy is None:
        raggy = RaggyClient()

    log_summary = request.context.get("log_summary", {})
    entities = log_summary.get("entities", {}) if isinstance(log_summary, dict) else {}
    anomalies = log_summary.get("anomalies", []) if isinstance(log_summary, dict) else []

    # Build search query from entities and anomalies
    search_terms: list[str] = []
    if isinstance(entities, dict):
        search_terms.extend(entities.get("services", [])[:3])
    search_terms.extend([str(a) for a in anomalies[:2]])
    search_query = " ".join(search_terms) or "security threat attack pattern"

    try:
        rag_result = await raggy.query(search_query, top_k=5)
        citations = rag_result.get("citations", [])
        rag_context_text = "\n".join(
            f"- [{c.get('title', 'doc')}]: {rag_result.get('answer', '')[:300]}"
            for c in citations[:3]
        )
    except Exception:
        rag_context_text = "No RAG context available."
        citations = []

    logs_block = wrap_logs_for_prompt(request.raw_logs[:20])  # limit for classify
    prompt = _CLASSIFY_PROMPT.format(
        log_summary=json.dumps(log_summary, indent=2),
        logs_block=logs_block,
        rag_context=rag_context_text or "No relevant documents found.",
    )

    result: dict[str, Any] = await llm.complete_json(prompt, system=_CLASSIFY_SYSTEM)
    result["raw_citations"] = citations
    return SocAgentResponse(result=result, reasoning_step="threat_classifier")
