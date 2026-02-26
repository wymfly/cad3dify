"""SSE-based generate endpoint (Phase 1 placeholder)."""

from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sse_starlette.sse import EventSourceResponse

router = APIRouter()


@router.post("/generate")
async def generate(
    image: UploadFile = File(...),
    pipeline_config: str = Form("{}"),
) -> EventSourceResponse:
    try:
        _config = json.loads(pipeline_config)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid pipeline_config JSON: {exc}") from exc

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        yield {"event": "progress", "data": json.dumps({"stage": "started"})}
        # TODO: integrate V2 pipeline
        yield {
            "event": "complete",
            "data": json.dumps({"message": "placeholder — pipeline integration pending"}),
        }

    return EventSourceResponse(event_generator())
