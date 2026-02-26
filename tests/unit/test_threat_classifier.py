"""Unit tests for threat classifier agent."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.threat_classifier import classify_threats
from app.schemas.agent import SocAgentRequest
from app.services.raggy_client import RaggyClient


@pytest.fixture
def sample_request() -> SocAgentRequest:
    return SocAgentRequest(
        raw_logs=['{"eventName": "AssumeRole", "sourceIPAddress": "185.220.101.15"}'],
        context={
            "actor_id": "analyst-001",
            "actor_role": "analyst",
            "log_summary": {
                "entities": {"services": ["iam", "s3"]},
                "anomalies": ["Cross-account role assumption from external IP"],
            },
        },
        session_id="test-session-002",
    )


@pytest.fixture
def mock_raggy() -> RaggyClient:
    raggy = MagicMock(spec=RaggyClient)
    raggy.query = AsyncMock(return_value={
        "answer": "MITRE T1078 Valid Accounts. Cross-account role assumption.",
        "citations": [
            {"doc_id": "00000000-0000-0000-0000-000000000001", "chunk_id": "00000000-0000-0000-0000-000000000002", "title": "MITRE T1078", "score": 0.9},
        ],
        "confidence": 0.85,
    })
    return raggy


@pytest.mark.unit
@pytest.mark.asyncio
async def test_classify_threats_returns_mitre_tactics(
    sample_request: SocAgentRequest,
    mock_raggy: RaggyClient,
) -> None:
    mock_llm_result = {
        "threat_indicators": [{"indicator": "AssumeRole from external IP", "confidence": 0.9, "evidence": "event"}],
        "mitre_tactics": [{"id": "T1078", "name": "Valid Accounts", "description": "Account abuse"}],
        "risk_score": 7.5,
        "rag_context": [{"title": "MITRE T1078", "relevance": "direct match"}],
        "reasoning": "Cross-account lateral movement detected.",
    }
    with patch("app.agents.threat_classifier.llm.complete_json", AsyncMock(return_value=mock_llm_result)):
        response = await classify_threats(sample_request, raggy=mock_raggy)

    assert response.reasoning_step == "threat_classifier"
    assert response.result["risk_score"] == 7.5
    assert len(response.result["mitre_tactics"]) == 1
    assert response.result["mitre_tactics"][0]["id"] == "T1078"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_classify_handles_raggy_failure(sample_request: SocAgentRequest) -> None:
    failing_raggy = MagicMock(spec=RaggyClient)
    failing_raggy.query = AsyncMock(side_effect=Exception("raggy unavailable"))

    mock_llm_result = {
        "threat_indicators": [],
        "mitre_tactics": [],
        "risk_score": 3.0,
        "rag_context": [],
        "reasoning": "Fallback due to RAG unavailability.",
    }
    with patch("app.agents.threat_classifier.llm.complete_json", AsyncMock(return_value=mock_llm_result)):
        response = await classify_threats(sample_request, raggy=failing_raggy)

    # Should still return a response even when raggy fails
    assert response.reasoning_step == "threat_classifier"
    assert response.result["risk_score"] == 3.0
