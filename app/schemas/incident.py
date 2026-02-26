from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    event_type: str
    actor: str
    resource: str
    description: str
    raw: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: UUID
    chunk_id: UUID
    title: str
    score: float = Field(ge=0.0, le=1.0)
    url: str | None = None


class MitreTactic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str


class ReasoningStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: str
    reasoning: str
    output_summary: str


class IncidentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    created_at: datetime
    timeline: list[TimelineEvent]
    risk_score: float = Field(ge=0.0, le=10.0)
    evidence_citations: list[Citation]
    mitre_tactics: list[MitreTactic]
    summary: str
    recommended_actions: list[str]
    reasoning_chain: list[ReasoningStep]
