"""独立 SSE 事件订阅端点 — GET /api/v1/jobs/{id}/events。

与 POST 响应解耦，客户端可独立订阅 Job 进度流。
"""

from __future__ import annotations

import asyncio
import json
import queue as queue_mod
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from backend.api.v1.errors import JobNotFoundError
from backend.models.job import get_job

router = APIRouter(prefix="/jobs", tags=["events"])

# ---------------------------------------------------------------------------
# 全局事件注册表：job_id → Queue
# ---------------------------------------------------------------------------

_event_queues: dict[str, queue_mod.Queue[dict[str, Any]]] = {}


def get_event_queue(job_id: str) -> queue_mod.Queue[dict[str, Any]]:
    """获取或创建 Job 的事件队列。"""
    if job_id not in _event_queues:
        _event_queues[job_id] = queue_mod.Queue()
    return _event_queues[job_id]


def emit_event(job_id: str, event: str, data: dict[str, Any]) -> None:
    """向 Job 的事件队列发送事件。"""
    q = get_event_queue(job_id)
    q.put_nowait({
        "event": event,
        "job_id": job_id,
        "data": {"job_id": job_id, "status": event, "message": "", **data},
    })


def cleanup_queue(job_id: str) -> None:
    """清理 Job 的事件队列。"""
    _event_queues.pop(job_id, None)


# ---------------------------------------------------------------------------
# SSE 格式辅助
# ---------------------------------------------------------------------------


def _sse(event: str, data: dict[str, Any]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


# ---------------------------------------------------------------------------
# GET /api/v1/jobs/{job_id}/events — SSE 订阅
# ---------------------------------------------------------------------------


@router.get("/{job_id}/events")
async def subscribe_job_events(job_id: str) -> EventSourceResponse:
    """订阅 Job 的实时管道进度事件。

    客户端通过 EventSource 连接此端点，接收结构化 SSE 事件流。
    当收到 completed 或 failed 事件时流终止。
    """
    job = await get_job(job_id)
    if job is None:
        raise JobNotFoundError(job_id)

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        # 先发送当前状态
        yield _sse("status", {
            "job_id": job_id,
            "status": job.status.value,
            "message": f"已连接，当前状态: {job.status.value}",
        })

        # 如果 Job 已终结，直接返回（不创建队列，避免泄漏）
        if job.status.value in ("completed", "failed"):
            yield _sse(job.status.value, {
                "job_id": job_id,
                "status": job.status.value,
                "message": "Job 已结束",
                "result": job.result,
                "error": job.error,
            })
            return

        q = get_event_queue(job_id)

        # 持续消费队列事件，带超时保护
        terminal_events = {"completed", "failed"}
        idle_seconds = 0
        max_idle_seconds = 300  # 5 分钟无事件则断开
        heartbeat_interval = 30  # 每 30 秒发心跳

        while True:
            try:
                event = q.get_nowait()
                idle_seconds = 0
            except queue_mod.Empty:
                await asyncio.sleep(0.5)
                idle_seconds += 0.5

                # 心跳
                if idle_seconds > 0 and int(idle_seconds) % heartbeat_interval == 0 and idle_seconds == int(idle_seconds):
                    yield _sse("heartbeat", {"job_id": job_id, "message": "keepalive"})

                # 超时检查：重新查询 DB 判断是否已终结
                if idle_seconds >= max_idle_seconds:
                    refreshed = await get_job(job_id)
                    if refreshed and refreshed.status.value in terminal_events:
                        yield _sse(refreshed.status.value, {
                            "job_id": job_id,
                            "status": refreshed.status.value,
                            "message": "Job 已结束（超时检测）",
                        })
                    cleanup_queue(job_id)
                    return

                # 中间检查：每 10 秒查一次 DB 看是否已终结
                if idle_seconds > 0 and idle_seconds % 10 == 0:
                    refreshed = await get_job(job_id)
                    if refreshed and refreshed.status.value in terminal_events:
                        yield _sse(refreshed.status.value, {
                            "job_id": job_id,
                            "status": refreshed.status.value,
                            "message": "Job 已结束",
                            "result": refreshed.result,
                            "error": refreshed.error,
                        })
                        cleanup_queue(job_id)
                        return

                continue

            event_type = event.get("event", "progress")
            data = event.get("data", {})
            yield _sse(event_type, data)

            if event_type in terminal_events:
                cleanup_queue(job_id)
                return

    return EventSourceResponse(event_stream())
