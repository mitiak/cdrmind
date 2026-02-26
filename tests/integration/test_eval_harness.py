"""Integration tests for evaluation framework."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.groundedness import score_groundedness_ci
from eval.hallucination import score_hallucination_ci
from eval.citation_verifier import verify_citations_ci


GOLDEN_DATASET_PATH = Path(__file__).parent.parent.parent / "eval" / "golden_dataset.json"


@pytest.fixture
def golden_dataset() -> list[dict]:
    return json.loads(GOLDEN_DATASET_PATH.read_text())


@pytest.mark.integration
def test_golden_dataset_has_15_samples(golden_dataset: list[dict]) -> None:
    assert len(golden_dataset) == 15


@pytest.mark.integration
def test_golden_dataset_schema(golden_dataset: list[dict]) -> None:
    required_keys = {"id", "logs", "expected_summary_keywords", "expected_mitre_tactics",
                     "expected_risk_score_range", "key_facts"}
    for sample in golden_dataset:
        assert required_keys.issubset(set(sample.keys())), f"Sample {sample.get('id')} missing keys"
        assert len(sample["logs"]) >= 1
        assert len(sample["expected_risk_score_range"]) == 2


@pytest.mark.eval
def test_ci_eval_groundedness_passes_threshold(golden_dataset: list[dict]) -> None:
    """CI eval: groundedness scores averaged should exceed 0.60 on key_facts vs logs."""
    scores = []
    for sample in golden_dataset:
        logs_text = "\n".join(sample["logs"])
        # Use key_facts as a proxy report
        report_text = " ".join(sample["key_facts"])
        score = score_groundedness_ci(report_text, logs_text)
        scores.append(score)

    avg = sum(scores) / len(scores)
    assert avg >= 0.60, f"Groundedness avg {avg:.3f} below threshold 0.60"


@pytest.mark.eval
def test_ci_eval_hallucination_passes_threshold(golden_dataset: list[dict]) -> None:
    """CI eval: hallucination rate on key_facts vs logs should be < 0.20."""
    rates = []
    for sample in golden_dataset:
        logs_text = "\n".join(sample["logs"])
        report_text = " ".join(sample["key_facts"])
        rate = score_hallucination_ci(report_text, logs_text)
        rates.append(rate)

    avg = sum(rates) / len(rates)
    assert avg < 0.20, f"Hallucination rate {avg:.3f} above threshold 0.20"
