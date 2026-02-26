from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LogBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    source: Literal["aws_cloudtrail", "identity", "vpc_flow"]
    events: list[dict[str, Any]]
    actor_id: str = Field(min_length=1)
    actor_role: Literal["analyst", "responder", "admin"]
