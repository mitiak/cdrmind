from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.models.incident import Incident
from app.schemas.incident import IncidentReport
from app.schemas.log import LogBatch
from app.services.audit import write_audit
from app.services.taskonaut_client import TaskoNautClient

router = APIRouter(prefix="/incidents", tags=["incidents"])
logger = get_logger(__name__)


def _get_taskonaut() -> TaskoNautClient:
    return TaskoNautClient()


@router.post("", response_model=IncidentReport, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: LogBatch,
    db: AsyncSession = Depends(get_db),
    taskonaut: TaskoNautClient = Depends(_get_taskonaut),
) -> IncidentReport:
    session_id = str(payload.session_id)
    raw_logs = [json.dumps(e) for e in payload.events]

    logger.info(
        "incidents.create.started",
        session_id=session_id,
        source=payload.source,
        actor=payload.actor_id,
        events=len(raw_logs),
    )

    try:
        task_result = await taskonaut.run_and_poll(
            flow_name="soc_pipeline",
            raw_logs=raw_logs,
            session_id=session_id,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role,
            max_steps=6,
        )
    except Exception as exc:
        logger.error("incidents.create.task_failed", session_id=session_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Pipeline execution failed: {exc}",
        ) from exc

    if task_result.get("status") != "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Pipeline task did not complete: {task_result.get('status')}",
        )

    # Extract report from task output payload
    output: dict[str, Any] = task_result.get("output_payload") or {}
    report_data = _extract_report(output)

    # Build IncidentReport
    try:
        report = IncidentReport.model_validate(report_data)
    except Exception as exc:
        logger.error("incidents.create.report_invalid", session_id=session_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Report validation failed: {exc}",
        ) from exc

    # Persist to DB
    incident = Incident(
        id=report.id,
        session_id=payload.session_id,
        actor_id=payload.actor_id,
        actor_role=payload.actor_role,
        source=payload.source,
        risk_score=report.risk_score,
        summary=report.summary,
        report_json=report.model_dump(mode="json"),
        task_id=str(task_result.get("id", "")),
    )
    db.add(incident)

    await write_audit(
        db,
        session_id=session_id,
        actor_id=payload.actor_id,
        step="create_incident",
        input_data=json.dumps({"source": payload.source, "events": len(raw_logs)}),
        output_data=json.dumps({"risk_score": report.risk_score, "tactics": len(report.mitre_tactics)}),
        incident_id=report.id,
    )
    await db.commit()

    logger.info(
        "incidents.create.completed",
        incident_id=str(report.id),
        risk_score=report.risk_score,
        tactics=len(report.mitre_tactics),
    )
    return report


@router.get("/{incident_id}", response_model=IncidentReport)
async def get_incident(incident_id: UUID, db: AsyncSession = Depends(get_db)) -> IncidentReport:
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return IncidentReport.model_validate(incident.report_json)


def _extract_report(output: dict[str, Any]) -> dict[str, Any]:
    """Extract IncidentReport data from taskonaut task output_payload."""
    # taskonaut output_payload is {step_name: step_output_payload}
    report_step = output.get("report")
    if isinstance(report_step, dict):
        result = report_step.get("result", report_step)
        if isinstance(result, dict):
            return result
    # Fallback: try to find any dict with 'summary' key
    for val in output.values():
        if isinstance(val, dict) and "summary" in val:
            r = val.get("result", val)
            if isinstance(r, dict):
                return r
    return {}
