from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.schemas.incident import (
    IncidentReport,
    MitreTactic,
    ReasoningStep,
    TimelineEvent,
)
from app.services import llm

_SYSTEM = (
    "You are a SOC analyst. Analyze security events and return a concise incident report. "
    "Respond ONLY with valid JSON."
)

_PROMPT = """Analyze these {n} security events and return a JSON incident report.

Events:
{events_block}

Return only valid JSON:
{{
  "summary": "<2-3 sentence analysis of what happened and the threat>",
  "risk_score": <0.0-10.0>,
  "mitre_tactics": [{{"id": "T####", "name": "<tactic name>", "description": "<why it applies>"}}],
  "recommended_actions": ["<action1>", "<action2>"],
  "timeline": [
    {{"timestamp": "<ISO>", "event_type": "<type>", "actor": "<id>", "resource": "<name>", "description": "<what happened>", "raw": {{}}}}
  ]
}}"""


async def run_quick_analysis(raw_logs: list[str], session_id: str) -> IncidentReport:
    events_block = "\n".join(f"[{i + 1}] {log}" for i, log in enumerate(raw_logs))
    prompt = _PROMPT.format(n=len(raw_logs), events_block=events_block)

    result: dict[str, Any] = await llm.complete_json(prompt, system=_SYSTEM, caller="quick")

    return IncidentReport(
        id=uuid.uuid4(),
        session_id=uuid.UUID(session_id),
        created_at=datetime.now(tz=timezone.utc),
        summary=result.get("summary", ""),
        risk_score=float(result.get("risk_score", 5.0)),
        mitre_tactics=[
            MitreTactic(
                id=m.get("id") or "T0000",
                name=m.get("name") or "Unknown",
                description=m.get("description") or "",
            )
            for m in result.get("mitre_tactics", [])
        ],
        recommended_actions=result.get("recommended_actions", []),
        timeline=[
            TimelineEvent(
                timestamp=t.get("timestamp") or "",
                event_type=t.get("event_type") or "unknown",
                actor=t.get("actor") or "unknown",
                resource=t.get("resource") or "",
                description=t.get("description") or "",
                raw=t.get("raw") or {},
            )
            for t in result.get("timeline", [])
        ],
        evidence_citations=[],
        reasoning_chain=[
            ReasoningStep(
                step="quick_analyst",
                reasoning="Single-pass combined analysis",
                output_summary=result.get("summary", ""),
            )
        ],
    )
