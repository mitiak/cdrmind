"""Unit tests for the evaluation scorers."""
from __future__ import annotations

import pytest

from eval.groundedness import score_groundedness_ci
from eval.hallucination import score_hallucination_ci
from eval.citation_verifier import verify_citations_ci


@pytest.mark.unit
def test_groundedness_perfect_overlap() -> None:
    logs = "user admin-svc from 203.0.113.42 attached AdministratorAccess policy"
    report = "admin-svc from 203.0.113.42 attached AdministratorAccess"
    score = score_groundedness_ci(report, logs)
    assert score >= 0.80


@pytest.mark.unit
def test_groundedness_no_overlap() -> None:
    logs = "abc def ghi"
    report = "xyz uvw rst"
    score = score_groundedness_ci(report, logs)
    assert score == 0.0


@pytest.mark.unit
def test_groundedness_empty_report() -> None:
    score = score_groundedness_ci("", "some logs here")
    assert score == 0.0


@pytest.mark.unit
def test_hallucination_no_fabrication() -> None:
    logs = "user admin from 1.2.3.4 ran GetObject on bucket prod-data"
    report = "admin from 1.2.3.4 accessed prod-data"
    rate = score_hallucination_ci(report, logs)
    assert rate == 0.0


@pytest.mark.unit
def test_hallucination_with_fabricated_ip() -> None:
    logs = "user admin from 1.2.3.4 ran GetObject"
    report = "admin from 99.88.77.66 ran GetObject and contacted 200.200.200.200"
    rate = score_hallucination_ci(report, logs)
    assert rate > 0.0


@pytest.mark.unit
def test_citation_verifier_no_citations() -> None:
    acc = verify_citations_ci([], "some report", "some rag")
    assert acc == 1.0


@pytest.mark.unit
def test_citation_verifier_with_overlap() -> None:
    citations = [{"doc_id": "abc", "chunk_id": "def", "title": "MITRE T1078", "score": 0.9}]
    report = "T1078 valid accounts attack detected"
    rag = "T1078 Valid Accounts used to gain access"
    acc = verify_citations_ci(citations, report, rag)
    assert acc > 0.0


@pytest.mark.unit
def test_groundedness_above_threshold_for_good_report() -> None:
    logs = """
    admin-svc logged in from 203.0.113.42
    admin-svc attached AdministratorAccess to backup-svc
    backup-svc assumed OrganizationAccountAccessRole from 185.220.101.15
    accessed prod-customer-data bucket
    deleted CloudTrail trail
    """
    report = "admin-svc from 203.0.113.42 escalated backup-svc to AdministratorAccess. AssumeRole from 185.220.101.15. prod-customer-data exfiltrated. CloudTrail deleted."
    score = score_groundedness_ci(report, logs)
    assert score >= 0.60, f"Expected >= 0.60, got {score}"
