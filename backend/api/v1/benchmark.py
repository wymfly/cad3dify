"""V1 评测 API — 运行评测、查看历史。

GET  /api/v1/benchmark/datasets
GET  /api/v1/benchmark/run       (SSE)
GET  /api/v1/benchmark/history
GET  /api/v1/benchmark/history/{run_id}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

from backend.api.v1.errors import APIError, ErrorCode
from backend.benchmark.runner import BenchmarkRunner

router = APIRouter(prefix="/benchmark", tags=["benchmark"])

_runner = BenchmarkRunner()

_BENCHMARKS_ROOT = Path("benchmarks")


@router.get("/datasets")
async def list_datasets() -> list[str]:
    """列出可用的评测数据集目录。"""
    if not _BENCHMARKS_ROOT.exists():
        return []
    return sorted(
        d.name
        for d in _BENCHMARKS_ROOT.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


@router.get("/run")
async def run_benchmark(
    dataset: str = Query(default="benchmarks/v1"),
    workers: int = Query(default=4, ge=1, le=16),
) -> EventSourceResponse:
    """运行评测，返回 SSE 进度流。"""

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        async for event in _runner.run_streaming(dataset, workers=workers):
            yield {
                "event": event.get("event", "message"),
                "data": json.dumps(event),
            }

    return EventSourceResponse(event_generator())


@router.get("/history")
async def list_benchmark_history() -> list[dict]:
    """列出所有已保存的评测报告。"""
    return _runner.list_reports()


@router.get("/history/{run_id}")
async def get_benchmark_report(run_id: str) -> dict:
    """获取指定 run_id 的评测报告。"""
    report = _runner.get_report(run_id)
    if report is None:
        raise APIError(
            status_code=404,
            code=ErrorCode.REPORT_NOT_FOUND,
            message=f"Report not found: {run_id}",
        )
    return report
