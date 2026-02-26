"""Integration tests for SOC pipeline with mocked external services."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient


@pytest.fixture
def mock_taskonaut_completed_task() -> dict:
    return {
        "id": str(uuid.uuid4()),
        "status": "COMPLETED",
        "flow_name": "soc_pipeline",
        "current_step": 3,
        "output_payload": {
            "report": {
                "result": {
                    "id": str(uuid.uuid4()),
                    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "created_at": datetime.now(tz=timezone.utc).isoformat(),
                    "timeline": [
                        {
                            "timestamp": "2026-02-25T02:14:33Z",
                            "event_type": "ConsoleLogin",
                            "actor": "admin-svc",
                            "resource": "console",
                            "description": "Login from external IP",
                            "raw": {},
                        }
                    ],
                    "risk_score": 9.0,
                    "evidence_citations": [],
                    "mitre_tactics": [
                        {"id": "T1078", "name": "Valid Accounts", "description": "Account compromise"},
                        {"id": "T1562", "name": "Impair Defenses", "description": "CloudTrail deleted"},
                    ],
                    "summary": "Complete AWS account compromise with privilege escalation and data exfiltration.",
                    "recommended_actions": [
                        "Immediately revoke all access keys for admin-svc",
                        "Enable CloudTrail in all regions",
                        "Review all S3 bucket policies",
                    ],
                    "reasoning_chain": [
                        {"step": "summarize", "reasoning": "Log analysis", "output_summary": "20 events analyzed"},
                        {"step": "classify", "reasoning": "MITRE mapping", "output_summary": "T1078, T1562 identified"},
                        {"step": "report", "reasoning": "Full synthesis", "output_summary": "Risk 9.0"},
                    ],
                }
            }
        },
    }


@pytest.fixture
def sample_cloudtrail_payload() -> dict:
    return {
        "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "source": "aws_cloudtrail",
        "events": [
            {
                "eventTime": "2026-02-25T02:14:33Z",
                "eventName": "ConsoleLogin",
                "userIdentity": {"userName": "admin-svc"},
                "sourceIPAddress": "203.0.113.42",
            }
        ],
        "actor_id": "analyst-001",
        "actor_role": "analyst",
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_incident_end_to_end(
    sample_cloudtrail_payload: dict,
    mock_taskonaut_completed_task: dict,
) -> None:
    """Test full incident creation flow with mocked external services."""
    from app.main import app

    mock_taskonaut = MagicMock()
    mock_taskonaut.run_and_poll = AsyncMock(return_value=mock_taskonaut_completed_task)

    mock_db_session = AsyncMock()
    mock_db_session.add = MagicMock()
    mock_db_session.flush = AsyncMock()
    mock_db_session.commit = AsyncMock()
    mock_db_session.execute = AsyncMock()

    async def override_get_db():
        yield mock_db_session

    from app.db.session import get_db

    with patch("app.api.routes.incidents.TaskoNautClient", return_value=mock_taskonaut):
        app.dependency_overrides[get_db] = override_get_db
        try:
            transport = httpx.ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/incidents", json=sample_cloudtrail_payload)
        finally:
            app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 201
    data = response.json()
    assert data["risk_score"] == 9.0
    assert len(data["mitre_tactics"]) == 2
    assert data["mitre_tactics"][0]["id"] == "T1078"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_summarize_endpoint() -> None:
    """Test /agents/summarize with mocked guardflow and LLM."""
    from app.main import app

    mock_guardflow = MagicMock()
    mock_guardflow.authorize = AsyncMock()

    mock_result = {
        "log_summary": {"total_events": 1, "anomalies": ["test"], "key_entities": {}, "attack_indicators": []},
        "timeline": [],
        "entities": {},
        "reasoning": "test",
    }

    payload = {
        "raw_logs": ['{"eventName": "ConsoleLogin"}'],
        "context": {"actor_id": "analyst-001", "actor_role": "analyst"},
        "session_id": "test-session",
    }

    with (
        patch("app.api.routes.agents.GuardflowClient", return_value=mock_guardflow),
        patch("app.agents.log_summarizer.llm.complete_json", AsyncMock(return_value=mock_result)),
    ):
        transport = httpx.ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/agents/summarize", json=payload)

    assert response.status_code == 200
    assert response.json()["reasoning_step"] == "log_summarizer"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_health() -> None:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
