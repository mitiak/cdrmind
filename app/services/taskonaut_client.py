from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class TaskoNautClient:
    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self._base_url = base_url or settings.taskonaut_url
        self._poll_interval = settings.task_poll_interval_secs
        self._poll_max = settings.task_poll_max_attempts

    async def create_task(
        self,
        *,
        flow_name: str,
        raw_logs: list[str],
        session_id: str,
        actor_id: str,
        actor_role: str,
    ) -> dict[str, Any]:
        payload = {
            "flow_name": flow_name,
            "raw_logs": raw_logs,
            "session_id": session_id,
            "actor_id": actor_id,
            "actor_role": actor_role,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self._base_url}/tasks", json=payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            logger.info("taskonaut.task.created", task_id=data.get("id"), flow=flow_name)
            return data

    async def run_task(self, task_id: str | UUID, max_steps: int = 12) -> dict[str, Any]:
        settings = get_settings()
        # Pipeline runs 3 LLM calls; give enough headroom for the slowest local model.
        run_timeout = settings.llm_timeout_secs * 3 + 30
        async with httpx.AsyncClient(timeout=run_timeout) as client:
            response = await client.post(
                f"{self._base_url}/tasks/{task_id}/run",
                json={"max_steps": max_steps},
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

    async def get_task(self, task_id: str | UUID) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self._base_url}/tasks/{task_id}")
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

    async def run_and_poll(
        self,
        *,
        flow_name: str,
        raw_logs: list[str],
        session_id: str,
        actor_id: str,
        actor_role: str,
        max_steps: int = 12,
    ) -> dict[str, Any]:
        task = await self.create_task(
            flow_name=flow_name,
            raw_logs=raw_logs,
            session_id=session_id,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        task_id = task["id"]

        # Run the task; on 409 (max_steps exhausted but not yet terminal) retry up to
        # 3 times — each call resumes from the current state so the pipeline will finish.
        for run_attempt in range(3):
            try:
                await self.run_task(task_id, max_steps=max_steps)
                break  # 200 — task reached a terminal state inside /run
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 409:
                    raise
                logger.warning(
                    "taskonaut.run.max_steps_exceeded",
                    task_id=task_id,
                    attempt=run_attempt,
                )
                # Taskonaut may have transitioned to COMPLETED on the very last step
                snap = await self.get_task(task_id)
                if snap.get("status") in ("COMPLETED", "FAILED"):
                    return snap
                # Non-terminal — loop to call /run again

        for attempt in range(self._poll_max):
            await asyncio.sleep(self._poll_interval)
            task_data = await self.get_task(task_id)
            status = task_data.get("status", "")
            logger.info("taskonaut.poll", task_id=task_id, status=status, attempt=attempt)
            if status in ("COMPLETED", "FAILED"):
                return task_data

        raise TimeoutError(f"Task {task_id} did not complete in {self._poll_max} polls")
