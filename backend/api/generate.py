"""SSE-based generate endpoint with Job session protocol (Phase 4 Task 4.6).

Supports two modes:
1. **text** mode: POST /generate/text → IntentParser → pause for confirmation → generate
2. **drawing** mode: POST /generate/drawing → V2 Pipeline → direct generate (placeholder)

Job lifecycle events are streamed as SSE to the client.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncGenerator

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.models.job import (
    JobStatus,
    clear_jobs,
    create_job,
    get_job,
    list_jobs,
    update_job,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class TextGenerateRequest(BaseModel):
    """Request body for text-based generation."""

    text: str
    pipeline_config: dict[str, Any] = {}


class ConfirmRequest(BaseModel):
    """Request body for parameter confirmation."""

    confirmed_params: dict[str, float] = {}
    base_body_method: str = "extrude"


# ---------------------------------------------------------------------------
# SSE event helpers
# ---------------------------------------------------------------------------


def _sse(event: str, data: dict[str, Any]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


# ---------------------------------------------------------------------------
# POST /generate — text mode (JSON body)
# ---------------------------------------------------------------------------


@router.post("/generate")
async def generate_text(body: TextGenerateRequest) -> EventSourceResponse:
    """Create a new text-mode generate job.

    Flow: text → IntentParser → pause for confirmation → generate
    """
    job_id = str(uuid.uuid4())
    job = create_job(job_id, input_type="text", input_text=body.text)

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        yield _sse("job_created", {
            "job_id": job.job_id,
            "status": job.status.value,
        })

        # Stage 1: Intent parsing
        update_job(job_id, status=JobStatus.INTENT_PARSED)
        yield _sse("intent_parsed", {
            "job_id": job_id,
            "status": JobStatus.INTENT_PARSED.value,
            "message": "意图解析完成，等待参数确认",
        })

        # Pause — client must call POST /generate/{job_id}/confirm
        update_job(job_id, status=JobStatus.AWAITING_CONFIRMATION)
        yield _sse("awaiting_confirmation", {
            "job_id": job_id,
            "status": JobStatus.AWAITING_CONFIRMATION.value,
            "message": "请确认参数后继续",
        })

    return EventSourceResponse(event_stream())


# ---------------------------------------------------------------------------
# POST /generate/drawing — drawing mode (multipart)
# ---------------------------------------------------------------------------


@router.post("/generate/drawing")
async def generate_drawing(
    image: UploadFile = File(...),
    pipeline_config: str = Form("{}"),
) -> EventSourceResponse:
    """Create a new drawing-mode generate job.

    Flow: image → V2 Pipeline → direct generate (placeholder)
    """
    try:
        _config = json.loads(pipeline_config)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pipeline_config JSON: {exc}",
        ) from exc

    job_id = str(uuid.uuid4())
    job = create_job(job_id, input_type="drawing")

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        yield _sse("job_created", {
            "job_id": job.job_id,
            "status": job.status.value,
        })

        update_job(job_id, status=JobStatus.GENERATING)
        yield _sse("generating", {
            "job_id": job_id,
            "status": JobStatus.GENERATING.value,
            "message": "正在生成 3D 模型…",
        })

        # TODO: integrate V2 pipeline execution
        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            result={"message": "pipeline integration pending"},
        )
        yield _sse("completed", {
            "job_id": job_id,
            "status": JobStatus.COMPLETED.value,
            "message": "placeholder — pipeline integration pending",
        })

    return EventSourceResponse(event_stream())


# ---------------------------------------------------------------------------
# POST /generate/{job_id}/confirm — resume after parameter confirmation
# ---------------------------------------------------------------------------


@router.post("/generate/{job_id}/confirm")
async def confirm_params(
    job_id: str, body: ConfirmRequest
) -> EventSourceResponse:
    """Confirm parameters and resume the generate pipeline."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job.status != JobStatus.AWAITING_CONFIRMATION:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Job {job_id} is in state '{job.status.value}', "
                f"expected 'awaiting_confirmation'"
            ),
        )

    update_job(job_id, status=JobStatus.GENERATING)

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        yield _sse("generating", {
            "job_id": job_id,
            "status": JobStatus.GENERATING.value,
            "confirmed_params": body.confirmed_params,
            "message": "参数已确认，正在生成…",
        })

        # Stage: refining
        update_job(job_id, status=JobStatus.REFINING)
        yield _sse("refining", {
            "job_id": job_id,
            "status": JobStatus.REFINING.value,
            "message": "正在优化模型…",
        })

        # Stage: completed
        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            result={
                "message": "生成完成",
                "confirmed_params": body.confirmed_params,
            },
        )
        yield _sse("completed", {
            "job_id": job_id,
            "status": JobStatus.COMPLETED.value,
            "message": "生成完成",
        })

    return EventSourceResponse(event_stream())


# ---------------------------------------------------------------------------
# GET /generate/jobs — list all jobs (must be before /{job_id} route)
# ---------------------------------------------------------------------------


@router.get("/generate/jobs")
async def list_all_jobs() -> list[dict[str, Any]]:
    """Return all jobs (for debugging / dashboard)."""
    return [j.model_dump() for j in list_jobs()]


# ---------------------------------------------------------------------------
# GET /generate/{job_id} — query job status
# ---------------------------------------------------------------------------


@router.get("/generate/{job_id}")
async def get_job_status(job_id: str) -> dict[str, Any]:
    """Return current job state."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job.model_dump()
