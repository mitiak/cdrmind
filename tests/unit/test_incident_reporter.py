"""Unit tests for incident reporter agent."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.incident_reporter import generate_report
from app.schemas.agent import SocAgentRequest


@pytest.fixture
def sample_request() -> SocAgentRequest:
    return SocAgentRequest(
        raw_logs=['{"eventName": "DeleteTrail", "userIdentity": {"userName": "attacker"}}'],
        context={
            "actor_id": "analyst-001",
            "actor_role": "analyst",
            "log_summary": {
                "total_events": 1,
                "anomalies": ["CloudTrail logging disabled"],
            },
            "classification": {
                "mitre_tactics": [{"id": "T1562", "name": "Impair Defenses", "description": "Logging disabled"}],
                "risk_score": 8.0,
                "raw_citations": [],
            },
        },
        session_id="00000000-0000-0000-0000-000000000099",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_report_returns_valid_incident_report(sample_request: SocAgentRequest) -> None:
    mock_llm_result = {
        "timeline": [
            {
                "timestamp": "2026-02-25T02:18:00Z",
                "event_type": "DefenseEvasion",
                "actor": "attacker",
                "resource": "cloudtrail",
                "description": "CloudTrail trail deleted",
                "raw": {},
            }
        ],
        "risk_score": 8.5,
        "mitre_tactics": [{"id": "T1562", "name": "Impair Defenses", "description": "Trail deleted"}],
        "summary": "Attacker deleted CloudTrail trail to cover tracks.",
        "recommended_actions": ["Re-enable CloudTrail", "Rotate credentials", "Investigate attacker account"],
        "reasoning_chain": [
            {"step": "summarize", "reasoning": "Log review", "output_summary": "Trail deletion event"},
            {"step": "classify", "reasoning": "T1562 match", "output_summary": "Defense evasion"},
            {"step": "report", "reasoning": "Combined analysis", "output_summary": "8.5 risk"},
        ],
    }
    with patch("app.agents.incident_reporter.llm.complete_json", AsyncMock(return_value=mock_llm_result)):
        response = await generate_report(sample_request)

    assert response.reasoning_step == "incident_reporter"
    result = response.result
    assert result["risk_score"] == 8.5
    assert result["summary"] == "Attacker deleted CloudTrail trail to cover tracks."
    assert len(result["mitre_tactics"]) == 1
    assert len(result["timeline"]) == 1
    assert len(result["recommended_actions"]) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_report_rejects_malformed_llm_output(sample_request: SocAgentRequest) -> None:
    """Pydantic strict validation should reject malformed risk_score."""
    bad_result = {
        "timeline": [],
        "risk_score": "not-a-number",  # invalid
        "mitre_tactics": [],
        "summary": "Test",
        "recommended_actions": [],
        "reasoning_chain": [],
    }
    with patch("app.agents.incident_reporter.llm.complete_json", AsyncMock(return_value=bad_result)):
        with pytest.raises(ValueError, match="schema validation"):
            await generate_report(sample_request)
