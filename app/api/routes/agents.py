from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents import incident_reporter, log_summarizer, threat_classifier
from app.core.logging import get_logger
from app.schemas.agent import SocAgentRequest, SocAgentResponse
from app.services.guardflow_client import GuardflowClient
from app.services.raggy_client import RaggyClient

router = APIRouter(prefix="/agents", tags=["agents"])
logger = get_logger(__name__)


def _guardflow() -> GuardflowClient:
    return GuardflowClient()


def _raggy() -> RaggyClient:
    return RaggyClient()


@router.post("/summarize", response_model=SocAgentResponse)
async def summarize(
    request: SocAgentRequest,
    guardflow: GuardflowClient = Depends(_guardflow),
) -> SocAgentResponse:
    actor_id = request.context.get("actor_id", "unknown")
    actor_role = request.context.get("actor_role", "analyst")

    await guardflow.authorize(actor_id=actor_id, actor_role=actor_role, tool="log_read")

    logger.info("agents.summarize.started", session_id=request.session_id, logs=len(request.raw_logs))
    try:
        response = await log_summarizer.summarize_logs(request)
    except Exception as exc:
        logger.error("agents.summarize.failed", session_id=request.session_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Summarization failed: {exc}",
        ) from exc
    logger.info("agents.summarize.completed", session_id=request.session_id)
    return response


@router.post("/classify", response_model=SocAgentResponse)
async def classify(
    request: SocAgentRequest,
    guardflow: GuardflowClient = Depends(_guardflow),
    raggy: RaggyClient = Depends(_raggy),
) -> SocAgentResponse:
    actor_id = request.context.get("actor_id", "unknown")
    actor_role = request.context.get("actor_role", "analyst")

    await guardflow.authorize(actor_id=actor_id, actor_role=actor_role, tool="threat_lookup")

    logger.info("agents.classify.started", session_id=request.session_id)
    try:
        response = await threat_classifier.classify_threats(request, raggy=raggy)
    except Exception as exc:
        logger.error("agents.classify.failed", session_id=request.session_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Classification failed: {exc}",
        ) from exc
    logger.info("agents.classify.completed", session_id=request.session_id)
    return response


@router.post("/report", response_model=SocAgentResponse)
async def report(
    request: SocAgentRequest,
    guardflow: GuardflowClient = Depends(_guardflow),
) -> SocAgentResponse:
    actor_id = request.context.get("actor_id", "unknown")
    actor_role = request.context.get("actor_role", "analyst")

    await guardflow.authorize(actor_id=actor_id, actor_role=actor_role, tool="report_generate")

    logger.info("agents.report.started", session_id=request.session_id)
    try:
        response = await incident_reporter.generate_report(request)
    except ValueError as exc:
        logger.error("agents.report.validation_failed", session_id=request.session_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("agents.report.failed", session_id=request.session_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation failed: {exc}",
        ) from exc
    logger.info("agents.report.completed", session_id=request.session_id)
    return response
