from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.schemas.agent import SocAgentRequest, SocAgentResponse
from app.schemas.incident import (
    Citation,
    IncidentReport,
    MitreTactic,
    ReasoningStep,
    TimelineEvent,
)
from app.services import llm

_REPORT_SYSTEM = (
    "You are a senior security incident responder. Generate a comprehensive incident report. "
    "Respond ONLY with valid JSON."
)

_REPORT_PROMPT = """Generate a structured incident report based on the analysis below.

Log Summary:
{log_summary}

Threat Classification:
{classification}

Return a JSON object matching this schema exactly:
{{
  "timeline": [
    {{"timestamp": "<ISO>", "event_type": "<type>", "actor": "<id>", "resource": "<name>", "description": "<what>", "raw": {{}}}}
  ],
  "risk_score": <0.0-10.0>,
  "mitre_tactics": [
    {{"id": "<T####>", "name": "<name>", "description": "<desc>"}}
  ],
  "summary": "<2-3 sentence incident summary>",
  "recommended_actions": ["<action1>", "<action2>", ...],
  "reasoning_chain": [
    {{"step": "<step_name>", "reasoning": "<what was analyzed>", "output_summary": "<key finding>"}}
  ]
}}"""


def _build_citations(raw_citations: list[dict[str, Any]], session_id: str) -> list[Citation]:
    citations: list[Citation] = []
    for c in raw_citations[:10]:
        try:
            citations.append(
                Citation(
                    doc_id=uuid.UUID(str(c.get("doc_id", uuid.uuid4()))),
                    chunk_id=uuid.UUID(str(c.get("chunk_id", uuid.uuid4()))),
                    title=str(c.get("title", "Unknown")),
                    score=float(c.get("score", 0.5)),
                    url=c.get("url"),
                )
            )
        except (ValueError, KeyError):
            continue
    return citations


async def generate_report(request: SocAgentRequest) -> SocAgentResponse:
    log_summary = request.context.get("log_summary", {})
    classification = request.context.get("classification", {})
    raw_citations: list[dict[str, Any]] = classification.get("raw_citations", [])

    prompt = _REPORT_PROMPT.format(
        log_summary=json.dumps(log_summary, indent=2),
        classification=json.dumps({k: v for k, v in classification.items() if k != "raw_citations"}, indent=2),
    )
    llm_result: dict[str, Any] = await llm.complete_json(prompt, system=_REPORT_SYSTEM)

    # Build IncidentReport with strict validation
    try:
        report = IncidentReport(
            id=uuid.uuid4(),
            session_id=uuid.UUID(request.session_id) if _is_uuid(request.session_id) else uuid.uuid4(),
            created_at=datetime.now(tz=timezone.utc),
            timeline=[
                TimelineEvent(
                    timestamp=t.get("timestamp", ""),
                    event_type=t.get("event_type", "unknown"),
                    actor=t.get("actor", "unknown"),
                    resource=t.get("resource", ""),
                    description=t.get("description", ""),
                    raw=t.get("raw", {}),
                )
                for t in llm_result.get("timeline", [])
            ],
            risk_score=float(llm_result.get("risk_score", 5.0)),
            evidence_citations=_build_citations(raw_citations, request.session_id),
            mitre_tactics=[
                MitreTactic(
                    id=m.get("id", "T0000"),
                    name=m.get("name", "Unknown"),
                    description=m.get("description", ""),
                )
                for m in llm_result.get("mitre_tactics", [])
            ],
            summary=llm_result.get("summary", "Incident analysis completed."),
            recommended_actions=llm_result.get("recommended_actions", []),
            reasoning_chain=[
                ReasoningStep(
                    step=r.get("step", ""),
                    reasoning=r.get("reasoning", ""),
                    output_summary=r.get("output_summary", ""),
                )
                for r in llm_result.get("reasoning_chain", [])
            ],
        )
    except (ValidationError, ValueError) as exc:
        raise ValueError(f"LLM output failed schema validation: {exc}") from exc

    return SocAgentResponse(
        result=report.model_dump(mode="json"),
        reasoning_step="incident_reporter",
    )


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
