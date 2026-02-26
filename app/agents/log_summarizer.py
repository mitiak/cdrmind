from __future__ import annotations

import json
from typing import Any

from app.core.security import wrap_logs_for_prompt
from app.schemas.agent import SocAgentRequest, SocAgentResponse
from app.services import llm

_SUMMARIZE_SYSTEM = (
    "You are a senior SOC analyst. Analyze the provided security log events and extract key information. "
    "Respond ONLY with valid JSON."
)

_SUMMARIZE_PROMPT = """Analyze the following security log events and provide a structured summary.

{logs_block}

Return a JSON object with:
{{
  "log_summary": {{
    "total_events": <int>,
    "time_range": {{"start": "<ISO timestamp>", "end": "<ISO timestamp>"}},
    "key_entities": {{"users": [...], "ips": [...], "resources": [...], "services": [...]}},
    "anomalies": ["<description>", ...],
    "attack_indicators": ["<description>", ...]
  }},
  "timeline": [
    {{"timestamp": "<ISO>", "event_type": "<type>", "actor": "<id>", "resource": "<name>", "description": "<what happened>"}},
    ...
  ],
  "entities": {{"users": [...], "ips": [...], "resources": [...]}},
  "reasoning": "<brief explanation of findings>"
}}"""


async def summarize_logs(request: SocAgentRequest) -> SocAgentResponse:
    logs_block = wrap_logs_for_prompt(request.raw_logs)
    prompt = _SUMMARIZE_PROMPT.format(logs_block=logs_block)
    result: dict[str, Any] = await llm.complete_json(prompt, system=_SUMMARIZE_SYSTEM)
    return SocAgentResponse(result=result, reasoning_step="log_summarizer")
