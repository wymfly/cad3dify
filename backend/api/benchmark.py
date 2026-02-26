"""Benchmark API — run evaluations and view history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from backend.benchmark.runner import BenchmarkRunner

router = APIRouter()

_runner = BenchmarkRunner()

_BENCHMARKS_ROOT = Path("benchmarks")


@router.get("/benchmark/datasets")
async def list_datasets() -> list[str]:
    """List available benchmark dataset directories."""
    if not _BENCHMARKS_ROOT.exists():
        return []
    return sorted(
        d.name for d in _BENCHMARKS_ROOT.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


@router.get("/benchmark/run")
async def run_benchmark(
    dataset: str = Query(default="benchmarks/v1"),
    workers: int = Query(default=4, ge=1, le=16),
) -> EventSourceResponse:
    """Run benchmark evaluation with SSE progress streaming."""

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        async for event in _runner.run_streaming(dataset, workers=workers):
            yield {"event": event.get("event", "message"), "data": json.dumps(event)}

    return EventSourceResponse(event_generator())


@router.get("/benchmark/history")
async def list_benchmark_history() -> list[dict]:
    """List all saved benchmark reports."""
    return _runner.list_reports()


@router.get("/benchmark/history/{run_id}")
async def get_benchmark_report(run_id: str) -> dict:
    """Get a specific benchmark report by run_id."""
    report = _runner.get_report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report not found: {run_id}")
    return report
