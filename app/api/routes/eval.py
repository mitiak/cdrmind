from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter(prefix="/eval", tags=["eval"])


class EvalRunRequest(BaseModel):
    dataset_path: str = "eval/golden_dataset.json"
    mode: str = "ci"


class EvalRunResponse(BaseModel):
    run_id: str
    status: str
    groundedness_avg: float | None = None
    hallucination_rate: float | None = None
    citation_accuracy: float | None = None


@router.post("/run", response_model=EvalRunResponse)
async def run_eval(request: EvalRunRequest) -> EvalRunResponse:
    # Trigger evaluation — in production this would dispatch a background task
    import subprocess
    import uuid

    run_id = str(uuid.uuid4())
    return EvalRunResponse(run_id=run_id, status="triggered")


@router.get("/results/{run_id}")
async def get_eval_results(run_id: UUID) -> dict:
    return {"run_id": str(run_id), "status": "not_found"}
