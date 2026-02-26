from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class RaggyClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or get_settings().raggy_url

    async def query(self, query: str, top_k: int = 5) -> dict[str, Any]:
        """Query the raggy vector store for relevant documents."""
        payload = {"query": query, "top_k": top_k}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self._base_url}/query", json=payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            logger.info("raggy.query.completed", query=query, citations=len(data.get("citations", [])))
            return data

    async def ingest(self, title: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Ingest a document into raggy."""
        payload = {
            "source_type": "md",
            "title": title,
            "content": content,
            "metadata": metadata or {},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self._base_url}/documents", json=payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data
