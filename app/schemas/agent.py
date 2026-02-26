from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class SocAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_logs: list[str]
    context: dict[str, Any]
    session_id: str


class SocAgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: dict[str, Any]
    reasoning_step: str
