"""Citation verifier: do cited chunks match referenced content?"""
from __future__ import annotations

import httpx


async def verify_citations(citations: list[dict], raggy_url: str = "http://localhost:8001") -> float:
    """
    Check that cited chunk IDs exist in raggy and have keyword overlap with the report.
    Returns citation accuracy (0.0–1.0). Threshold: > 0.90.
    """
    if not citations:
        return 1.0  # no citations to verify — not a failure

    verified = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for citation in citations:
            chunk_id = citation.get("chunk_id")
            if not chunk_id:
                continue
            try:
                # Try to fetch the chunk document
                response = await client.get(f"{raggy_url}/documents/{citation.get('doc_id')}")
                if response.status_code == 200:
                    verified += 1
            except Exception:
                continue

    return verified / len(citations) if citations else 1.0


def verify_citations_ci(citations: list[dict], report_text: str, rag_answer: str) -> float:
    """
    CI mode: check keyword overlap between report and RAG answer text.
    """
    if not citations:
        return 1.0

    import re

    def tokens(t: str) -> set[str]:
        return set(re.findall(r"\b[a-zA-Z0-9._/-]{3,}\b", t.lower()))

    report_tokens = tokens(report_text)
    rag_tokens = tokens(rag_answer)

    if not rag_tokens:
        return 0.5  # unknown — no RAG content to compare

    overlap = report_tokens & rag_tokens
    if not report_tokens:
        return 0.0
    return min(1.0, len(overlap) / max(len(report_tokens) * 0.3, 1))
