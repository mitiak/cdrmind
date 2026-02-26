from __future__ import annotations

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class GuardflowClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or get_settings().guardflow_url

    async def authorize(self, *, actor_id: str, actor_role: str, tool: str, args: dict | None = None) -> None:
        """Call guardflow /authorize. Raises HTTPException on denial."""
        payload = {
            "actor": {"id": actor_id, "role": actor_role},
            "tool_call": {"tool": tool, "args": args or {}},
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(f"{self._base_url}/authorize", json=payload)
            except httpx.RequestError as exc:
                logger.error("guardflow.authorize.connection_error", tool=tool, error=str(exc))
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="guardflow unavailable",
                ) from exc
            if response.status_code == 403:
                detail = response.json().get("detail", {})
                code = detail.get("code", "FORBIDDEN") if isinstance(detail, dict) else "FORBIDDEN"
                logger.warning("guardflow.authorize.denied", tool=tool, actor=actor_id, code=code)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Authorization denied: {code}",
                )
            response.raise_for_status()
            logger.info("guardflow.authorize.ok", tool=tool, actor=actor_id)
