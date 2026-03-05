# Pipeline Breakpoints 实施计划（R4 修订版）

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 LangGraph 管道添加运行时断点能力——每个节点执行完毕后可按需暂停，支持状态检视和恢复继续。

**Architecture:** 统一使用 **pre-execution breakpoint** 模式。在 `_wrap_node()` 包装器开头（`try/except` 之外）注入断点检查，检查 `node_trace` 中最后一个**非跳过**节点是否在断点列表中。Terminal 节点通过在构建图时追加 `__bp_guard__` 轻量节点来实现断点（避免 post-execution interrupt 导致的副作用重执行）。

**关键设计决策（基于 R1 + R2 + R3 + R4 四轮审查修订）：**

1. **所有断点检查在 `try/except Exception` 之外。** `GraphInterrupt` 继承自 `Exception`，放在 try 内会被捕获。
2. **所有断点检查都是 pre-execution。** 断点在下一个节点的 wrapper 开头触发，当前节点已完成且 state 已提交，无副作用风险。
3. **Terminal 节点使用 guard node。** Terminal → END 无后续 wrapper，在 PipelineBuilder.build() 中插入 `__bp_guard__` → END。Guard node 仅做断点检查，无业务逻辑，re-execution 安全。*（R3-G3-1/G3-4 修复，废弃 R2 的 post-execution 方案）*
4. **Disabled 节点跳过断点但写 skip trace。** Disabled check 在 breakpoint check 之前；返回含 skip trace entry（包含 `elapsed_ms: 0`），避免幽灵重触发。*（R2-G2-3 修复）*
5. **断点检查用 last non-skipped trace entry。** 遍历 `node_trace` 反向查找首个 `skipped != True` 的条目，避免 disabled 节点后断点丢失。*（R3-C3-1 修复）*
6. **不对 HITL 节点做特殊处理。** 断点和 HITL 的 `interrupt_before` 是独立机制——HITL 用于确认数据，断点用于调试检视。可能产生双暂停，但行为正确。*（R3-G3-2 修复，废弃 R2 的 `not desc.supports_hitl` 条件）*
7. **`interrupt()` 返回值用于更新断点模式。** `Command(resume=data)` 中的 `data` 不会自动合并到 state——`interrupt()` 返回 `data`，wrapper 手动将更新写入 diff。
8. **Non-fatal 错误保留 breakpoint_update。** Except 块重建 diff 时注入 breakpoint_update。*（R3-G3-3 修复）*
9. **Resume 使用非空 sentinel。** `{"action": "continue"}` 确保可靠消费 interrupt。
10. **Wrapper 保持 DB 无关性。** 断点状态更新在 API 层 SSE 事件处理中完成。*（R2-C2-2 修复）*
11. **Resume 端点包含状态回滚。** try/finally 确保失败时恢复 BREAKPOINT 状态。*（R3-C3-6 修复）*
12. **线性管道假设。** `node_trace` 在线性链中确定性前进。
13. **Resume 端点跳过 replay SSE。** LangGraph resume 时重执行被中断的节点，`_safe_dispatch("node.breakpoint")` 会再次触发。Resume 端点用 `bp_replay_consumed` 标志跳过第一个 `node.breakpoint` 事件。*（R4-P1-A 修复）*
14. **DB 更新在 yield 之前。** `update_job(BREAKPOINT)` 必须在 `yield _sse(...)` 之前执行，否则客户端断连导致 update 永不执行，job 卡在 GENERATING。*（R4-P1-C 修复）*
15. **Breakpoint 模式必须持久化 job。** `create_job_endpoint` 当前不调用 `create_job()` 持久化到 DB。启用断点时必须先 persist，否则 `update_job` 抛 KeyError、`get_job` 返回 None。*（R4-P1-D 修复）*
16. **Resume 流正常结束后更新 COMPLETED。** 无此步骤时 job 永久卡在 GENERATING（若无后续断点）或 BREAKPOINT（若有 replay 被消费后无更新）。*（R4-P1-A 修复）*

**Tech Stack:** LangGraph 0.6+ (`interrupt` / `Command` / `GraphInterrupt`)、FastAPI、pytest

---

## 文件修改清单

| 文件 | 操作 | 任务 |
|------|------|------|
| `backend/graph/pipeline_state.py` | 修改 | T1 |
| `backend/graph/builder.py` | 修改 | T2 |
| `tests/test_runtime_skip.py` | 修改 | T2 |
| `backend/models/job.py` | 修改 | T3 |
| `backend/api/v1/jobs.py` | 修改 | T4, T5 |
| `tests/test_breakpoints.py` | **新增** | T6 |

---

### Task 1: PipelineState 添加 breakpoints 字段

**Files:**
- Modify: `backend/graph/pipeline_state.py`

**Step 1: 读取当前 PipelineState 定义**

**Step 2: 添加 breakpoints 字段**

在 `status` 字段之前添加：

```python
    # ── Debug ──
    breakpoints: list[str] | None
```

不需要 reducer（`breakpoints` 由请求传入或 resume 时覆盖，整体替换即可）。

**Step 3: 验证**

```bash
uv run python -c "from backend.graph.pipeline_state import PipelineState; print('OK')"
```

---

### Task 2: _wrap_node() 注入断点 + guard node 构建

**Files:**
- Modify: `backend/graph/builder.py`
- Modify: `tests/test_runtime_skip.py`

#### Step 1: 添加 helper 函数

在 `_wrap_node` 之前添加：

```python
def _last_completed_node(node_trace: list[dict[str, Any]]) -> str | None:
    """Return the name of the last non-skipped node in trace.

    R3-C3-1 fix: skip entries with {"skipped": True} to avoid
    disabled nodes causing breakpoint misses.
    """
    for entry in reversed(node_trace):
        if not entry.get("skipped"):
            return entry["node"]
    return None
```

#### Step 2: 修改 _wrap_node — 注入 pre-execution 断点

完整 wrapper 结构（R3 终稿）：

```python
    def _wrap_node(self, desc: NodeDescriptor):
        """Wrap a node function: NodeContext bridge + timing + SSE events + breakpoints."""

        async def wrapped(state: dict[str, Any]) -> dict[str, Any]:
            job_id = state.get("job_id", "unknown")

            # ── Disabled check FIRST (R2-G2-3: before breakpoint check) ──
            node_cfg = (state.get("pipeline_config") or {}).get(desc.name, {})
            if not node_cfg.get("enabled", True):
                logger.info("Node %s skipped (disabled)", desc.name)
                await _safe_dispatch("node.skipped", {
                    "job_id": job_id,
                    "node": desc.name,
                    "reason": "disabled",
                })
                # R2-G2-3: write skip trace to advance node_trace
                return {"node_trace": [{
                    "node": desc.name,
                    "skipped": True,
                    "elapsed_ms": 0,
                    "assets_produced": [],
                }]}

            # ── Pre-execution breakpoint (OUTSIDE try/except) ──
            bp_list = state.get("breakpoints") or []
            breakpoint_update: dict[str, Any] = {}
            if bp_list:
                node_trace = state.get("node_trace") or []
                last_completed = _last_completed_node(node_trace)
                if last_completed and (last_completed in bp_list or "__all__" in bp_list):
                    from langgraph.types import interrupt

                    await _safe_dispatch("node.breakpoint", {
                        "job_id": job_id,
                        "paused_after": last_completed,
                        "next_node": desc.name,
                    })

                    resume_val = interrupt({
                        "paused_after": last_completed,
                        "next_node": desc.name,
                        "status": "breakpoint",
                    })

                    if isinstance(resume_val, dict) and "action" in resume_val:
                        action = resume_val["action"]
                        if action == "step":
                            breakpoint_update["breakpoints"] = ["__all__"]
                        elif action == "run":
                            breakpoint_update["breakpoints"] = []

            # ── Normal execution (existing code structure) ──
            t0 = time.time()
            await _safe_dispatch("node.started", {
                "job_id": job_id,
                "node": desc.name,
                "timestamp": t0,
            })

            try:
                ctx = NodeContext.from_state(state, desc)
                result = await desc.fn(ctx)
                elapsed_ms = round((time.time() - t0) * 1000)

                if isinstance(result, dict):
                    diff = result
                else:
                    diff = ctx.to_state_diff()

                reasoning = diff.pop("_reasoning", None)
                trace_entry = {
                    "node": desc.name,
                    "elapsed_ms": elapsed_ms,
                    "reasoning": reasoning,
                    "assets_produced": list(diff.get("assets", {}).keys()),
                }
                if hasattr(ctx, '_fallback_trace') and ctx._fallback_trace:
                    trace_entry["fallback"] = ctx._fallback_trace

                if "node_trace" not in diff:
                    diff["node_trace"] = []
                diff["node_trace"].append(trace_entry)

                if breakpoint_update:
                    diff.update(breakpoint_update)

                await _safe_dispatch("node.completed", {
                    "job_id": job_id,
                    "node": desc.name,
                    "elapsed_ms": elapsed_ms,
                    "reasoning": reasoning,
                    "outputs_summary": _summarize_outputs(diff),
                    "assets_produced": trace_entry["assets_produced"],
                })

                return diff

            except Exception as exc:
                elapsed_ms = round((time.time() - t0) * 1000)
                await _safe_dispatch("node.failed", {
                    "job_id": job_id,
                    "node": desc.name,
                    "elapsed_ms": elapsed_ms,
                    "error": str(exc),
                })
                if desc.non_fatal:
                    logger.warning("Non-fatal node '%s' failed: %s", desc.name, exc)
                    diff = {"node_trace": [{
                        "node": desc.name,
                        "elapsed_ms": elapsed_ms,
                        "error": str(exc),
                        "non_fatal": True,
                    }]}
                    # R3-G3-3 fix: preserve breakpoint state update
                    if breakpoint_update:
                        diff.update(breakpoint_update)
                    return diff
                raise

        wrapped.__name__ = f"wrapped_{desc.name}"
        return wrapped
```

**关键变更（对比 R2 版）：**

1. **移除了 `not desc.supports_hitl` 条件** — R3-G3-2：HITL 和断点独立运作
2. **使用 `_last_completed_node()` 替代 `node_trace[-1]["node"]`** — R3-C3-1：跳过 disabled 节点
3. **移除了整个 post-execution breakpoint 块** — R3-G3-1：改用 guard node
4. **Non-fatal except 块保留 breakpoint_update** — R3-G3-3
5. **Skip trace entry 包含 `elapsed_ms: 0` 和 `assets_produced: []`** — R3-Gemini-P2-6：兼容下游消费者
6. **Disabled check 不再 dispatch `node.started`** — 性能优化（disabled 节点无需 started 事件）

#### Step 3: 添加 guard node + 修改图构建

在 `PipelineBuilder` 类中添加 `_make_bp_guard` 方法和修改 `_build_workflow`：

```python
    def _make_bp_guard(self) -> Any:
        """Create a lightweight breakpoint guard node for terminal → END."""

        async def bp_guard(state: dict[str, Any]) -> dict[str, Any]:
            bp_list = state.get("breakpoints") or []
            if not bp_list:
                return {}

            node_trace = state.get("node_trace") or []
            last_completed = _last_completed_node(node_trace)
            if last_completed and (last_completed in bp_list or "__all__" in bp_list):
                from langgraph.types import interrupt

                job_id = state.get("job_id", "unknown")
                await _safe_dispatch("node.breakpoint", {
                    "job_id": job_id,
                    "paused_after": last_completed,
                    "next_node": "__end__",
                })

                resume_val = interrupt({
                    "paused_after": last_completed,
                    "next_node": "__end__",
                    "status": "breakpoint",
                })

                if isinstance(resume_val, dict):
                    action = resume_val.get("action")
                    if action == "run":
                        return {"breakpoints": []}
                    # R4-P2-A: "step" at terminal = continue (no next node).
                    # Guard returns {} → graph proceeds to END normally.
            return {}

        bp_guard.__name__ = "__bp_guard__"
        return bp_guard
```

修改 `_build_workflow` 中 terminal → END 的边。

**R4-P1-B 修复：必须显式删除原有代码。** 当前 `builder.py` L101-104 存在：

```python
        # ❌ 删除以下代码（原 terminal → END 直连）：
        for desc in resolved.ordered_nodes:
            if desc.is_terminal:
                workflow.add_edge(desc.name, END)
```

**替换为：**

```python
        # ✅ Terminal nodes → guard → END (R3 guard node architecture)
        guard = self._make_bp_guard()
        for desc in resolved.ordered_nodes:
            if desc.is_terminal:
                guard_name = f"__bp_guard_{desc.name}__"
                workflow.add_node(guard_name, guard)
                workflow.add_edge(desc.name, guard_name)
                workflow.add_edge(guard_name, END)
```

**⚠️ 不可同时保留两种边。** 原有 `terminal → END` 和新增 `terminal → guard → END` 共存会导致 LangGraph 图构建歧义或运行时错误。Guard node 对非断点执行透明（立即返回 `{}`）。

#### Step 4: 更新 test_runtime_skip.py

现有测试预期 disabled 节点 `return {}` 和 `node.started` 事件。更新为新行为：

```python
    async def test_skip_emits_events_and_returns_skip_trace(self, mock_dispatch):
        """Disabled node: emit node.skipped, return skip trace, don't execute fn."""
        desc = self._make_desc()
        wrapped = self._make_builder()._wrap_node(desc)

        state = {
            "job_id": "j1",
            "pipeline_config": {"test_node": {"enabled": False}},
        }

        result = await wrapped(state)

        # Returns skip trace entry (not empty dict)
        assert result == {"node_trace": [{
            "node": "test_node",
            "skipped": True,
            "elapsed_ms": 0,
            "assets_produced": [],
        }]}
        desc.fn.assert_not_called()

        # Only node.skipped event (no node.started for disabled nodes)
        events = [call.args[0] for call in mock_dispatch.call_args_list]
        assert "node.skipped" in events
        assert "node.started" not in events
```

#### Step 5: 运行测试

```bash
uv run pytest tests/test_runtime_skip.py tests/test_builder.py -v
```

---

### Task 3: JobStatus 添加 BREAKPOINT

**Files:**
- Modify: `backend/models/job.py`

在 `JobStatus` 枚举中添加：

```python
    BREAKPOINT = "breakpoint"
```

位置：在 `AWAITING_DRAWING_CONFIRMATION` 之后、`GENERATING` 之前。

验证：

```bash
uv run python -c "from backend.models.job import JobStatus; print(JobStatus.BREAKPOINT.value)"
```

---

### Task 4: Job 创建 API 接受 breakpoints + SSE 断点状态管理

**Files:**
- Modify: `backend/api/v1/jobs.py`

#### Step 1: 修改 import（R4-P2-B：合并到现有 import 行）

当前 `jobs.py` 已有 `from backend.models.job import (Job, JobStatus, create_job, get_job)`。
在该行**追加** `update_job`：

```python
from backend.models.job import (Job, JobStatus, create_job, get_job, update_job)
```

另外在文件顶部添加（如尚未存在）：

```python
import json as _json
import logging
```

#### Step 2: CreateJobRequest 添加 breakpoints

```python
class CreateJobRequest(BaseModel):
    # ... existing fields ...
    breakpoints: list[str] | None = Field(
        default=None,
        description="节点名称列表，执行完毕后暂停。'__all__' 表示每个节点都暂停。",
    )
```

#### Step 3: create_job_endpoint 写入 breakpoints + 持久化 + SSE 状态管理

在 `initial_state` 构建后添加：

```python
    if body.breakpoints:
        initial_state["breakpoints"] = body.breakpoints
        # R4-P1-D: breakpoint 模式需要 DB 持久化（resume 端点依赖 get_job/update_job）
        await create_job(job_id, input_type=body.input_type, input_text=input_text or "")
```

修改 event_stream generator，添加断点状态管理（R4-P1-C：DB 更新在 yield 之前）：

```python
    logger_api = logging.getLogger(__name__)

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        async for event in cad_graph.astream_events(initial_state, config=config, version="v2"):
            if event["event"] == "on_custom_event":
                name = event["name"]
                data = event["data"]
                emit_event(job_id, name, data)
                # R4-P1-C: update DB BEFORE yield — client disconnect must not skip status update
                if name == "node.breakpoint":
                    try:
                        await update_job(job_id, status=JobStatus.BREAKPOINT)
                    except Exception:
                        logger_api.warning("Failed to update job %s to breakpoint", job_id)
                yield _sse(name, data)
```

#### Step 4: create_drawing_job 支持 breakpoints（R2-G2-4 修复）

在 `create_drawing_job` 中，从原始 `pipeline_config` Form 字符串解析 `_breakpoints`：

```python
    # After existing pipeline_config parsing (line ~329)
    try:
        _raw_cfg = _json.loads(pipeline_config)
    except (ValueError, TypeError):
        _raw_cfg = {}
    _bp = _raw_cfg.get("_breakpoints") if isinstance(_raw_cfg, dict) else None

    # ... (existing initial_state construction) ...

    if _bp:
        initial_state["breakpoints"] = _bp
        # R4-P1-D: breakpoint 模式需要 DB 持久化
        await create_job(job_id, input_type="drawing", input_text="")
```

同样为 `create_drawing_job` 的 event_stream 添加断点状态管理（同 Step 3，含 R4-P1-C yield 顺序修复）。

#### Step 5: 验证

```bash
uv run pytest tests/test_graph_hitl.py -v
```

---

### Task 5: 新增 resume 端点

**Files:**
- Modify: `backend/api/v1/jobs.py`

#### Step 1: 定义 ResumeRequest

```python
from typing import Literal

class ResumeRequest(BaseModel):
    """断点恢复请求。"""
    action: Literal["continue", "step", "run"] = "continue"
```

#### Step 2: 实现 resume 端点（含 R3-C3-6 状态回滚 + R4 修复）

```python
@router.post("/{job_id}/resume")
async def resume_job(job_id: str, body: ResumeRequest, request: Request) -> EventSourceResponse:
    """从断点恢复管道执行。"""
    from langgraph.types import Command

    job = await get_job(job_id)
    if job is None:
        raise JobNotFoundError(job_id)

    if job.status != JobStatus.BREAKPOINT:
        raise InvalidJobStateError(
            job_id,
            current=job.status.value,
            expected="breakpoint",
        )

    # Transition out of breakpoint (R2-C2-5)
    await update_job(job_id, status=JobStatus.GENERATING)

    cad_graph = request.app.state.cad_graph
    config = {"configurable": {"thread_id": job_id}}
    resume_data: dict[str, Any] = {"action": body.action}
    logger_api = logging.getLogger(__name__)

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        # R4-P1-A: LangGraph re-executes the interrupted node on resume.
        # The wrapper's _safe_dispatch("node.breakpoint") fires again (replay).
        # Skip the first node.breakpoint event to avoid:
        # 1) sending duplicate SSE to client
        # 2) update_job(BREAKPOINT) reverting status mid-execution
        bp_replay_consumed = False

        try:
            async for event in cad_graph.astream_events(
                Command(resume=resume_data),
                config=config,
                version="v2",
            ):
                if event["event"] == "on_custom_event":
                    name = event["name"]
                    data = event["data"]

                    # R4-P1-A: skip replayed breakpoint event
                    if name == "node.breakpoint" and not bp_replay_consumed:
                        bp_replay_consumed = True
                        continue

                    emit_event(job_id, name, data)

                    # R4-P1-C: update DB BEFORE yield — client disconnect must not skip status update
                    if name == "node.breakpoint":
                        try:
                            await update_job(job_id, status=JobStatus.BREAKPOINT)
                        except Exception:
                            logger_api.warning("Failed to update job %s to breakpoint", job_id)

                    yield _sse(name, data)

            # R4-P1-A: stream completed normally — update final status
            # Without this, job stays GENERATING (or BREAKPOINT if replay wasn't consumed)
            try:
                current = await get_job(job_id)
                if current and current.status == JobStatus.GENERATING:
                    await update_job(job_id, status=JobStatus.COMPLETED)
            except Exception:
                logger_api.warning("Failed to update job %s to completed", job_id)

        except Exception:
            # R3-C3-6 fix: rollback status on stream failure
            try:
                await update_job(job_id, status=JobStatus.BREAKPOINT)
            except Exception:
                pass
            raise

    return EventSourceResponse(event_stream())
```

#### Step 3: 验证

```bash
uv run pytest tests/ -v --tb=short -k "breakpoint or hitl"
```

---

### Task 6: 测试

**Files:**
- Create: `tests/test_breakpoints.py`

测试策略：用 `MemorySaver` 构建迷你图验证断点机制。T6 测试断点算法逻辑；真实 `_wrap_node` 集成由 `test_builder.py` 和 `test_runtime_skip.py` 覆盖。

```python
"""Tests for pipeline breakpoint/debug functionality."""

import operator
from typing import Annotated, Any, TypedDict

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class BPTestState(TypedDict, total=False):
    job_id: str
    node_trace: Annotated[list[dict[str, Any]], operator.add]
    breakpoints: list[str] | None
    data: Annotated[dict[str, Any], lambda a, b: {**a, **b}]
    pipeline_config: dict[str, dict[str, Any]]
    status: str


def _last_completed_node(node_trace: list[dict[str, Any]]) -> str | None:
    """Mirror of builder._last_completed_node for test nodes."""
    for entry in reversed(node_trace):
        if not entry.get("skipped"):
            return entry["node"]
    return None


def _make_node(name: str):
    """Create a test node with breakpoint check (mirrors wrapper algorithm)."""

    async def node_fn(state: dict[str, Any]) -> dict[str, Any]:
        # Disabled check
        node_cfg = (state.get("pipeline_config") or {}).get(name, {})
        if not node_cfg.get("enabled", True):
            return {"node_trace": [{"node": name, "skipped": True, "elapsed_ms": 0}]}

        # Pre-execution breakpoint
        bp_list = state.get("breakpoints") or []
        breakpoint_update: dict[str, Any] = {}
        if bp_list:
            node_trace = state.get("node_trace") or []
            last = _last_completed_node(node_trace)
            if last and (last in bp_list or "__all__" in bp_list):
                resume_val = interrupt({"paused_after": last, "next_node": name})
                if isinstance(resume_val, dict) and "action" in resume_val:
                    action = resume_val["action"]
                    if action == "step":
                        breakpoint_update["breakpoints"] = ["__all__"]
                    elif action == "run":
                        breakpoint_update["breakpoints"] = []

        # Execute
        diff: dict[str, Any] = {
            "data": {name: "done"},
            "node_trace": [{"node": name, "elapsed_ms": 1}],
        }
        if breakpoint_update:
            diff.update(breakpoint_update)
        return diff

    node_fn.__name__ = f"node_{name}"
    return node_fn


def _make_guard():
    """Create a breakpoint guard node (mirrors builder._make_bp_guard)."""

    async def bp_guard(state: dict[str, Any]) -> dict[str, Any]:
        bp_list = state.get("breakpoints") or []
        if not bp_list:
            return {}
        node_trace = state.get("node_trace") or []
        last = _last_completed_node(node_trace)
        if last and (last in bp_list or "__all__" in bp_list):
            resume_val = interrupt({"paused_after": last, "next_node": "__end__"})
            if isinstance(resume_val, dict) and resume_val.get("action") == "run":
                return {"breakpoints": []}
        return {}

    bp_guard.__name__ = "__bp_guard__"
    return bp_guard


def _build_graph(nodes: list[str]):
    """Build a linear graph: a → b → ... → guard → END."""
    workflow = StateGraph(BPTestState)
    for name in nodes:
        workflow.add_node(name, _make_node(name))

    workflow.add_edge(START, nodes[0])
    for i in range(len(nodes) - 1):
        workflow.add_edge(nodes[i], nodes[i + 1])

    # Guard node before END (R3 architecture)
    guard = _make_guard()
    workflow.add_node("__bp_guard__", guard)
    workflow.add_edge(nodes[-1], "__bp_guard__")
    workflow.add_edge("__bp_guard__", END)

    return workflow.compile(checkpointer=MemorySaver())


def _init(tid: str, breakpoints: list[str] | None = None, **extra) -> dict:
    return {
        "job_id": tid, "node_trace": [], "data": {}, "status": "pending",
        **({"breakpoints": breakpoints} if breakpoints else {}),
        **extra,
    }


@pytest.mark.asyncio
class TestBreakpoints:

    async def test_no_breakpoints_runs_to_completion(self):
        """不设断点 → 正常完成。"""
        graph = _build_graph(["a", "b", "c"])
        result = await graph.ainvoke(
            _init("t1"), config={"configurable": {"thread_id": "t1"}},
        )
        assert len(result["node_trace"]) == 3

    async def test_breakpoint_pauses_after_node(self):
        """breakpoints=["a"] → 在 a 后暂停。"""
        graph = _build_graph(["a", "b", "c"])
        cfg = {"configurable": {"thread_id": "t2"}}

        r1 = await graph.ainvoke(_init("t2", breakpoints=["a"]), config=cfg)
        assert len(r1["node_trace"]) == 1
        assert r1["node_trace"][0]["node"] == "a"

        r2 = await graph.ainvoke(Command(resume={"action": "continue"}), config=cfg)
        assert len(r2["node_trace"]) == 3

    async def test_all_breakpoint_single_step(self):
        """__all__ → 每个节点后暂停（含 terminal 通过 guard）。"""
        graph = _build_graph(["a", "b", "c"])
        cfg = {"configurable": {"thread_id": "t3"}}

        r1 = await graph.ainvoke(_init("t3", breakpoints=["__all__"]), config=cfg)
        assert len(r1["node_trace"]) == 1  # paused after a

        r2 = await graph.ainvoke(Command(resume={"action": "continue"}), config=cfg)
        assert len(r2["node_trace"]) == 2  # paused after b

        r3 = await graph.ainvoke(Command(resume={"action": "continue"}), config=cfg)
        assert len(r3["node_trace"]) == 3  # paused after c (guard fires)

        r4 = await graph.ainvoke(Command(resume={"action": "continue"}), config=cfg)
        assert len(r4["node_trace"]) == 3  # completes

    async def test_terminal_breakpoint_via_guard(self):
        """R3-G3-1: terminal 断点通过 guard node 触发，无副作用重执行。"""
        exec_count = {"b": 0}

        async def counting_b(state):
            # Same breakpoint logic as _make_node
            bp_list = state.get("breakpoints") or []
            bu = {}
            if bp_list:
                nt = state.get("node_trace") or []
                last = _last_completed_node(nt)
                if last and (last in bp_list or "__all__" in bp_list):
                    rv = interrupt({"paused_after": last, "next_node": "b"})
                    if isinstance(rv, dict) and rv.get("action") == "run":
                        bu["breakpoints"] = []
            exec_count["b"] += 1
            diff = {"data": {"b": "done"}, "node_trace": [{"node": "b", "elapsed_ms": 1}]}
            if bu:
                diff.update(bu)
            return diff

        counting_b.__name__ = "node_b"

        workflow = StateGraph(BPTestState)
        workflow.add_node("a", _make_node("a"))
        workflow.add_node("b", counting_b)
        workflow.add_node("__bp_guard__", _make_guard())
        workflow.add_edge(START, "a")
        workflow.add_edge("a", "b")
        workflow.add_edge("b", "__bp_guard__")
        workflow.add_edge("__bp_guard__", END)

        graph = workflow.compile(checkpointer=MemorySaver())
        cfg = {"configurable": {"thread_id": "t-term"}}

        r1 = await graph.ainvoke(_init("t-term", breakpoints=["b"]), config=cfg)
        assert len(r1["node_trace"]) == 2  # a + b ran
        assert exec_count["b"] == 1  # b executed once

        # Guard paused after b. Resume → completes.
        r2 = await graph.ainvoke(Command(resume={"action": "continue"}), config=cfg)
        assert len(r2["node_trace"]) == 2
        assert exec_count["b"] == 1  # b NOT re-executed (guard handled it)

    async def test_disabled_node_no_phantom_retrigger(self):
        """R2-G2-3 + R3-C3-1: disabled 节点不导致幽灵重触发。"""
        graph = _build_graph(["a", "b", "c"])
        cfg = {"configurable": {"thread_id": "t-dis"}}

        r1 = await graph.ainvoke(
            _init("t-dis", breakpoints=["a"], pipeline_config={"b": {"enabled": False}}),
            config=cfg,
        )
        # R4-P2-C fix: trace has 2 entries at pause point, not 1.
        # Flow: a executes → trace=[a]. b disabled → skip trace committed → trace=[a, b(skipped)].
        # c starts → bp check: last_completed("a") in ["a"] → interrupt. c's output NOT committed.
        assert len(r1["node_trace"]) == 2
        assert r1["node_trace"][0]["node"] == "a"
        assert r1["node_trace"][1].get("skipped") is True

        # Resume → c runs (last_completed still "a", but interrupt already consumed)
        r2 = await graph.ainvoke(Command(resume={"action": "continue"}), config=cfg)
        trace = r2["node_trace"]
        assert len(trace) == 3  # a + b(skipped) + c
        assert trace[1].get("skipped") is True

    async def test_resume_step_changes_to_all(self):
        """action=step → breakpoints 变为 __all__。"""
        graph = _build_graph(["a", "b", "c"])
        cfg = {"configurable": {"thread_id": "t-step"}}

        r1 = await graph.ainvoke(_init("t-step", breakpoints=["a"]), config=cfg)
        assert len(r1["node_trace"]) == 1

        r2 = await graph.ainvoke(Command(resume={"action": "step"}), config=cfg)
        assert len(r2["node_trace"]) == 2  # b runs, pauses before c

    async def test_resume_run_clears_breakpoints(self):
        """action=run → 清除 breakpoints，运行到结束。"""
        graph = _build_graph(["a", "b", "c"])
        cfg = {"configurable": {"thread_id": "t-run"}}

        r1 = await graph.ainvoke(_init("t-run", breakpoints=["__all__"]), config=cfg)
        assert len(r1["node_trace"]) == 1

        r2 = await graph.ainvoke(Command(resume={"action": "run"}), config=cfg)
        assert len(r2["node_trace"]) == 3  # all complete

    async def test_no_side_effect_on_resume(self):
        """断点在 pre-execution 位置 → 前一个节点不会重执行。"""
        exec_count = {"a": 0, "b": 0}

        async def counting_a(state):
            exec_count["a"] += 1
            return {"data": {"a": "done"}, "node_trace": [{"node": "a", "elapsed_ms": 1}]}

        async def counting_b(state):
            bp_list = state.get("breakpoints") or []
            bu = {}
            if bp_list:
                nt = state.get("node_trace") or []
                last = _last_completed_node(nt)
                if last and (last in bp_list or "__all__" in bp_list):
                    rv = interrupt({"paused_after": last, "next_node": "b"})
                    if isinstance(rv, dict) and rv.get("action") == "run":
                        bu["breakpoints"] = []
            exec_count["b"] += 1
            diff = {"data": {"b": "done"}, "node_trace": [{"node": "b", "elapsed_ms": 1}]}
            if bu:
                diff.update(bu)
            return diff

        counting_a.__name__ = "node_a"
        counting_b.__name__ = "node_b"

        workflow = StateGraph(BPTestState)
        workflow.add_node("a", counting_a)
        workflow.add_node("b", counting_b)
        workflow.add_node("__bp_guard__", _make_guard())
        workflow.add_edge(START, "a")
        workflow.add_edge("a", "b")
        workflow.add_edge("b", "__bp_guard__")
        workflow.add_edge("__bp_guard__", END)

        graph = workflow.compile(checkpointer=MemorySaver())
        cfg = {"configurable": {"thread_id": "t-side"}}

        await graph.ainvoke(_init("t-side", breakpoints=["a"]), config=cfg)
        assert exec_count["a"] == 1
        assert exec_count["b"] == 0

        await graph.ainvoke(Command(resume={"action": "continue"}), config=cfg)
        assert exec_count["a"] == 1  # NOT re-executed
        assert exec_count["b"] == 1
```

运行测试：

```bash
uv run pytest tests/test_breakpoints.py -v
uv run pytest tests/ -v --tb=short
```

---

### Task 7: 验证 + 提交

```bash
uv run pytest tests/ -v --tb=short
git add backend/graph/pipeline_state.py backend/graph/builder.py backend/models/job.py backend/api/v1/jobs.py tests/test_breakpoints.py tests/test_runtime_skip.py
git commit -m "feat(graph): add runtime breakpoint support for pipeline debugging"
```

---

## 依赖图

```
T1 (state) → T2 (wrapper + guard + skip-test) → T3 (JobStatus) → T4 (API) → T5 (resume)
                                                                                    ↓
                                                                               T6 (测试)
                                                                                    ↓
                                                                               T7 (验证)
```

---

## 审查修复追溯

### R1 修复（原始架构缺陷）

| # | 来源 | 问题 | 修复 |
|---|------|------|------|
| C1 | Codex | `GraphInterrupt` 被 `except Exception` 捕获 | 断点放在 try/except 外 |
| C2 | Codex | `interrupt()` 导致节点重执行 | 断点在下一节点 wrapper 开头 |
| C3 | Codex | `Command(resume={})` 不消费 interrupt | `{"action": "continue"}` 非空 |
| C4 | Codex+Gemini | resume data 不自动合并 state | 手动写入 diff |
| G1 | Gemini | 断点暂停时 state 显示 pre-node | 断点在下一节点开头，state 已提交 |
| G2 | Gemini | Resume data 不更新 state | 写入 breakpoint_update dict |
| C6 | Codex | HITL + breakpoint 交互未定义 | ~~跳过 HITL 节点~~ → R3 改为不做特殊处理 |

### R2 修复（边界情况）

| # | 来源 | 问题 | 修复 |
|---|------|------|------|
| G2-1 | Gemini | Terminal 断点不触发 | ~~post-execution breakpoint~~ → R3 改为 guard node |
| G2-3/C2-1 | 共识 | Disabled 幽灵重触发 | Skip trace + disabled check 前置 |
| G2-4/C2-4 | 共识 | `pc_raw` 不存在 | 从原始字符串解析 |
| C2-2 | Codex | wrapper DB 依赖 | 移至 API 层 |
| C2-5 | Codex | Resume 无状态转换 | 端点开头 update_job |

### R3 修复（架构重构 + 边界完善）

| # | 来源 | 问题 | 修复 |
|---|------|------|------|
| G3-1 | Gemini [P1] | Post-execution breakpoint 导致 terminal 副作用重执行 | **guard node 替代 post-execution** |
| G3-2 | Gemini [P1] | `not desc.supports_hitl` 吞掉前节点断点 | **移除 HITL 特殊处理** |
| G3-3 | Gemini [P1→P2] | Non-fatal 丢弃 breakpoint_update | **except 块保留 update** |
| G3-4/C3-2 | 共识 | Stale bp_list 导致 terminal 无限循环 | **guard node 从 state 读最新值** |
| C3-1 | Codex [P2] | Disabled-first 丢弃前节点断点 | **`_last_completed_node()` 跳过 skipped** |
| C3-3 | Codex [P2] | Skip-trace backward-incompatible | **更新 test_runtime_skip.py** |
| C3-5 | Codex [P2] | API 缺少 import | **T4 Step 1 添加 import** |
| C3-6 | Codex [P2] | Resume 状态不回滚 | **try/finally + 回滚** |

### R4 修复（Sonnet 4.6 独立审查 + 自审）

| # | 来源 | 问题 | 修复 |
|---|------|------|------|
| P1-A | 自审 | Resume 时 `node.breakpoint` SSE 重复 → job 卡在 BREAKPOINT | **`bp_replay_consumed` 标志 + COMPLETED 状态更新** |
| P1-B | Sonnet | 原有 `terminal → END` 边未在 diff 中显式删除 | **显式标注删除原代码 + 替换** |
| P1-C | Sonnet | `yield` 在 `update_job` 之前 → 客户端断连=状态丢失 | **DB 更新在 yield 之前** |
| P1-D | Sonnet | `create_job()` 未调用 → resume 404 | **breakpoint 模式先 `create_job()` 持久化** |
| P2-A | Sonnet (降级) | guard node 未处理 `action == "step"` | **添加注释：terminal step = continue** |
| P2-B | Sonnet (降级) | `update_job` import 表述不清 | **合并到现有 import 行** |
| P2-C | Sonnet | 测试断言 `len == 1` 应为 `len == 2` | **修复断言 + 添加注释说明** |

### 全部已拒绝 findings

| # | 来源 | 问题 | 拒绝原因 |
|---|------|------|---------|
| G2-2 | Gemini R2 | 并行分支 node_trace 不可靠 | 线性管道（YAGNI） |
| G2-5 | Gemini R2 | Resume 缺 state mutation | v1 不需要（YAGNI） |
| C2-6 | Codex R2 | 缺 API 测试 | 后续增强 |

---

## 执行流程图

```
Client: POST /jobs {breakpoints: ["node_a"]}
  │
  ├── create_job wrapper: disabled? no. bp check: no previous → skip → execute
  ├── node_a wrapper: disabled? no. bp check: last_completed=create_job, not in bp → execute
  ├── node_b wrapper: disabled? no. bp check: last_completed=node_a, IN bp →
  │     ├── dispatch "node.breakpoint" SSE
  │     ├── API layer: update_job(status="breakpoint")
  │     ├── interrupt({paused_after: "node_a", next_node: "node_b"})
  │     └── graph pauses
  │
Client: POST /jobs/{id}/resume {action: "continue"}
  │
  ├── update_job(status="generating")
  ├── Command(resume={"action":"continue"})
  ├── node_b re-executes wrapper:
  │     ├── _safe_dispatch("node.breakpoint") ← R4: replay event, resume 端点跳过
  │     ├── bp check → interrupt() returns {"action":"continue"} → no update
  │     ├── execute node_b
  │     └── return diff
  ├── node_c wrapper → execute
  ├── __bp_guard__ → last_completed=node_c, not in bp → return {} → END
  ├── graph completes
  └── R4: update_job(status="completed") ← 流正常结束后更新

Terminal breakpoint (R3 guard node):
  ├── finalize wrapper: execute finalize (side effects: DB write)
  ├── __bp_guard_finalize__:
  │     ├── bp check: last_completed=finalize, IN bp_list →
  │     ├── interrupt({paused_after: "finalize", next_node: "__end__"})
  │     └── graph pauses
  ├── resume → guard re-executes (no side effects, just bp check) → END
  └── finalize NOT re-executed ← R3 fix

Disabled node (R3 fix):
  ├── node_a: executes, trace: [{node:"a"}]
  ├── node_b: disabled → return {node_trace: [{node:"b", skipped:true}]}
  ├── node_c: bp check: _last_completed_node() → skips b(skipped) → finds "a"
  │     └── if "a" in breakpoints → pause; else → execute
  └── no phantom re-trigger on "a" by node_c

HITL + breakpoint (R3 fix: independent):
  ├── analysis: executes, breakpoints=["analysis"]
  ├── confirm_with_user: interrupt_before fires (LangGraph) → HITL pause
  ├── user sends confirm → graph resumes → confirm wrapper starts
  ├── confirm wrapper: bp check: last_completed="analysis", IN bp → breakpoint pause
  ├── user sends resume → confirm wrapper continues → executes confirm
  └── two separate pauses, two separate purposes
```

---

## 架构限制

1. **线性管道假设。** `_last_completed_node()` 在线性链中确定性。并行分支需重新设计。
2. **Guard node 可见性。** `__bp_guard__` 出现在图中但不产生 trace。对 frontend 透明。
3. **HITL 双暂停。** 在 HITL 节点前设断点会导致两次暂停（断点 + HITL）。这是正确行为但可能影响 UX。可通过文档说明。
4. **Non-fatal + breakpoint。** Non-fatal 失败节点保留 breakpoint_update，但断点状态更新可能在节点失败上下文中。用户需理解断点模式改变不代表节点成功。
5. **Breakpoint 模式的 DB 依赖。** 仅启用 breakpoints 时调用 `create_job()` 持久化。非断点模式仍走纯 SSE 流（无 DB 记录），行为不变。
6. **Resume SSE replay。** Resume 端点固定跳过第一个 `node.breakpoint` 事件。如果 LangGraph 的 resume 行为在未来版本中不再重执行中断节点，此逻辑需要适配。
