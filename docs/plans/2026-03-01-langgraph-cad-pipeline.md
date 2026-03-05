# LangGraph CAD Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the hand-rolled SSE + `_event_queues` + HTTP state-machine HITL with a unified LangGraph StateGraph that manages the entire CAD Job lifecycle, providing framework-level timeout/retry, checkpoint-based resume, and pull-based event streaming.

**Architecture:** A new `backend/graph/` module owns the StateGraph. Each pipeline stage becomes a graph node. `astream_events()` replaces `_event_queues`/`PipelineBridge`. `AsyncSqliteSaver` reuses `cad3dify.db` for checkpointing. The existing `backend/pipeline/pipeline.py` functions are renamed for clarity but logic is unchanged; `backend/api/v1/jobs.py` endpoints become thin wrappers around `graph.astream_events()`.

**Tech Stack:** LangGraph 0.3+, langgraph-checkpoint-sqlite 2.0+, LCEL (langchain-core), asyncio, FastAPI SSE

**OpenSpec:** `openspec/changes/langgraph-cad-pipeline/`
**Design Doc:** `docs/plans/2026-03-01-langgraph-pipeline-design.md`

---

## Phase 概览 + 域标签 + Skill 路由

| Phase | 描述 | 域标签 | Skills | 可并行 |
|-------|------|--------|--------|--------|
| 1 | 依赖安装 | `[backend]` | — | — |
| 2 | State 定义 | `[backend]` | — | ✅ 与 3, 6 并行 |
| 3 | 函数重命名 | `[backend]` | — | ✅ 与 2, 6 并行 |
| 4 | Graph 节点 | `[backend]` | — | 依赖 2, 3 |
| 5 | Graph 路由 + 构建 | `[backend][architecture]` | — | 依赖 4 |
| 6 | LLM 超时/重试工具 | `[backend]` | — | ✅ 与 2, 3 并行 |
| 7 | API 层切换 | `[backend]` | `streaming-api-patterns` | 依赖 5, 6 |
| 8 | 废弃代码清理 | `[backend]` | — | 依赖 7 |
| 9 | 测试更新与新增 | `[test]` | `qa-testing-strategy` | 部分与 4-7 交织 |
| 10 | 验收检查 | `[test]` | — | 最终 |

**并行组:**
- **Group A (可并行):** Phase 2 + Phase 3 + Phase 6
- **Group B (依赖 A):** Phase 4 → Phase 5
- **Group C (依赖 B):** Phase 7 → Phase 8
- **Group D (贯穿):** Phase 9 随各阶段增量执行
- **Group E (最终):** Phase 10

---

## Task 1: 安装 LangGraph 依赖 `[backend]`

**Files:**
- Modify: `pyproject.toml:9-25` (dependencies array)
- Modify: `uv.lock` (auto-generated)

**Step 1: 添加依赖到 pyproject.toml**

在 `pyproject.toml` 的 `dependencies` 数组中，`"aiosqlite>=0.20.0"` 后追加：

```toml
    "langgraph>=0.3.0,<1.0",
    "langgraph-checkpoint-sqlite>=2.0.0,<3.0",
```

**Step 2: 运行 uv sync**

```bash
uv sync
```

Expected: 安装成功，无版本冲突。

**Step 3: 验证 import**

```bash
uv run python -c "
import langgraph
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import interrupt, Command
from langchain_core.callbacks import adispatch_custom_event
print('All imports OK')
"
```

Expected: `All imports OK`

**Step 4: 运行 astream_events API 烟雾测试**

```bash
uv run python -c "
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

class S(TypedDict):
    x: int

g = StateGraph(S)
g.add_node('a', lambda s: {'x': s['x']+1})
g.add_edge(START, 'a')
g.add_edge('a', END)
c = g.compile()
import asyncio
async def smoke():
    events = []
    async for ev in c.astream_events({'x': 0}, version='v2'):
        events.append(ev['event'])
    assert 'on_chain_start' in events, f'Missing events: {events}'
    print(f'Smoke test OK ({len(events)} events)')
asyncio.run(smoke())
"
```

Expected: `Smoke test OK (N events)`

**Step 5: 确认现有测试不受影响**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -5
```

Expected: 全部通过（或跳过），无新增 failure。

**Step 6: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "[impl] Add langgraph and langgraph-checkpoint-sqlite dependencies"
```

---

## Task 2: 定义 CadJobState TypedDict `[backend]`

**Files:**
- Create: `backend/graph/__init__.py`
- Create: `backend/graph/state.py`
- Test: `tests/test_graph_state.py`

**Step 1: 创建目录结构**

```bash
mkdir -p backend/graph/nodes
```

**Step 2: 创建 `backend/graph/__init__.py`**

```python
"""LangGraph CAD Job orchestration."""
```

**Step 3: 编写 failing test**

`tests/test_graph_state.py`:

```python
"""Tests for CadJobState and STATE_TO_ORM_MAPPING."""

from backend.graph.state import CadJobState, STATE_TO_ORM_MAPPING


class TestCadJobState:
    def test_state_has_required_fields(self) -> None:
        hints = CadJobState.__annotations__
        required = [
            "job_id", "input_type", "input_text", "image_path",
            "intent", "matched_template", "drawing_spec",
            "confirmed_params", "confirmed_spec", "disclaimer_accepted",
            "step_path", "model_url", "printability",
            "status", "error", "failure_reason",
        ]
        for field in required:
            assert field in hints, f"Missing field: {field}"

    def test_state_to_orm_mapping_covers_key_fields(self) -> None:
        assert STATE_TO_ORM_MAPPING["confirmed_spec"] == "drawing_spec_confirmed"
        assert STATE_TO_ORM_MAPPING["printability"] == "printability_result"
        assert STATE_TO_ORM_MAPPING["step_path"] == "output_step_path"

    def test_state_to_orm_mapping_values_are_strings(self) -> None:
        for k, v in STATE_TO_ORM_MAPPING.items():
            assert isinstance(k, str)
            assert isinstance(v, str)
```

**Step 4: 运行测试确认 fail**

```bash
uv run pytest tests/test_graph_state.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.graph.state'`

**Step 5: 实现 `backend/graph/state.py`**

```python
"""CadJobState — the single state object flowing through the CAD Job StateGraph."""

from __future__ import annotations

from typing import TypedDict


class CadJobState(TypedDict, total=False):
    # ── Input ──
    job_id: str
    input_type: str              # "text" | "drawing" | "organic"
    input_text: str | None
    image_path: str | None

    # ── Analysis outputs ──
    intent: dict | None          # IntentSpec.model_dump()
    matched_template: str | None
    drawing_spec: dict | None    # DrawingSpec.model_dump()

    # ── HITL confirmation inputs ──
    confirmed_params: dict | None
    confirmed_spec: dict | None
    disclaimer_accepted: bool

    # ── Generation outputs ──
    step_path: str | None
    model_url: str | None        # GLB preview URL
    printability: dict | None

    # ── Status & error ──
    status: str                  # mirrors JobStatus value
    error: str | None
    failure_reason: str | None   # typed: timeout | rate_limited | invalid_json | generation_error


# Maps CadJobState field names → ORM JobModel column names where they differ.
STATE_TO_ORM_MAPPING: dict[str, str] = {
    "confirmed_spec": "drawing_spec_confirmed",
    "printability": "printability_result",
    "step_path": "output_step_path",
}
```

**Step 6: 运行测试确认 pass**

```bash
uv run pytest tests/test_graph_state.py -v
```

Expected: 3 passed

**Step 7: Commit**

```bash
git add backend/graph/__init__.py backend/graph/state.py tests/test_graph_state.py
git commit -m "[impl] Add CadJobState TypedDict and STATE_TO_ORM_MAPPING"
```

---

## Task 3: Pipeline 函数重命名 `[backend]`

**Files:**
- Modify: `backend/pipeline/pipeline.py`
- Modify: `backend/api/generate.py` (imports)
- Modify: `backend/api/v1/jobs.py` (imports, 间接通过 generate.py)
- Test: `tests/test_pipeline_rename.py`

> **注意：** 保留旧名 alias（`old_name = new_name`）确保向后兼容，不破坏现有调用。

**Step 1: 编写 failing test**

`tests/test_pipeline_rename.py`:

```python
"""Verify pipeline functions are accessible by new capability-descriptive names."""


def test_new_names_importable() -> None:
    from backend.pipeline.pipeline import (
        analyze_vision_spec,
        generate_step_from_spec,
        analyze_and_generate_step,
    )
    assert callable(analyze_vision_spec)
    assert callable(generate_step_from_spec)
    assert callable(analyze_and_generate_step)


def test_old_names_still_work() -> None:
    from backend.pipeline.pipeline import (
        analyze_drawing,
        generate_from_drawing_spec,
        generate_step_v2,
    )
    assert callable(analyze_drawing)
    assert callable(generate_from_drawing_spec)
    assert callable(generate_step_v2)
```

**Step 2: 运行测试确认 fail**

```bash
uv run pytest tests/test_pipeline_rename.py -v
```

Expected: `ImportError: cannot import name 'analyze_vision_spec'`

**Step 3: 在 `backend/pipeline/pipeline.py` 中重命名函数**

在 `pipeline.py` 中执行以下重命名（保留旧名 alias）：

1. `analyze_drawing` → `analyze_vision_spec`，文件末尾添加 `analyze_drawing = analyze_vision_spec`
2. `generate_from_drawing_spec` → `generate_step_from_spec`，文件末尾添加 `generate_from_drawing_spec = generate_step_from_spec`
3. `generate_step_v2` → `analyze_and_generate_step`，文件末尾添加 `generate_step_v2 = analyze_and_generate_step`

函数体内部所有自引用也更新（如 `analyze_and_generate_step` 内调用 `analyze_vision_spec` 而非 `analyze_drawing`）。

**Step 4: 运行测试确认 pass**

```bash
uv run pytest tests/test_pipeline_rename.py -v
```

Expected: 2 passed

**Step 5: 运行全量测试确认无回归**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -5
```

Expected: 全部通过

**Step 6: Commit**

```bash
git add backend/pipeline/pipeline.py tests/test_pipeline_rename.py
git commit -m "[impl] Rename pipeline functions to capability-descriptive names"
```

---

## Task 4: LLM 超时/重试工具模块 `[backend]`

**Files:**
- Create: `backend/graph/llm_utils.py`
- Test: `tests/test_llm_utils.py`

**Step 1: 编写 failing test**

`tests/test_llm_utils.py`:

```python
"""Tests for LLM chain builders and exception mapping."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.graph.llm_utils import (
    build_intent_chain,
    build_vision_chain,
    map_exception_to_failure_reason,
)


class TestMapExceptionToFailureReason:
    def test_timeout(self) -> None:
        assert map_exception_to_failure_reason(asyncio.TimeoutError()) == "timeout"

    def test_rate_limited_openai(self) -> None:
        exc = Exception("Rate limit exceeded")
        exc.status_code = 429  # type: ignore[attr-defined]
        assert map_exception_to_failure_reason(exc) == "rate_limited"

    def test_json_decode_error(self) -> None:
        import json
        exc = json.JSONDecodeError("Expecting value", "", 0)
        assert map_exception_to_failure_reason(exc) == "invalid_json"

    def test_generic_error(self) -> None:
        assert map_exception_to_failure_reason(ValueError("boom")) == "generation_error"


class TestBuildIntentChain:
    def test_returns_runnable(self) -> None:
        primary = MagicMock()
        primary.with_retry = MagicMock(return_value=primary)
        primary.__or__ = MagicMock(return_value=primary)
        fallback = MagicMock()
        chain = build_intent_chain(primary, fallback)
        assert hasattr(chain, "invoke") or hasattr(chain, "ainvoke")


class TestBuildVisionChain:
    def test_returns_runnable_no_fallback(self) -> None:
        primary = MagicMock()
        primary.with_retry = MagicMock(return_value=primary)
        chain = build_vision_chain(primary)
        assert hasattr(chain, "invoke") or hasattr(chain, "ainvoke")
```

**Step 2: 运行测试确认 fail**

```bash
uv run pytest tests/test_llm_utils.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: 实现 `backend/graph/llm_utils.py`**

```python
"""LLM chain builders with retry, fallback, and timeout utilities."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable


def map_exception_to_failure_reason(exc: BaseException) -> str:
    """Map an exception to a typed failure reason string."""
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    status = getattr(exc, "status_code", None)
    if status == 429:
        return "rate_limited"
    return "generation_error"


def build_intent_chain(
    primary_llm: BaseChatModel,
    fallback_llm: BaseChatModel | None = None,
) -> Runnable:
    """Build an LCEL intent-parsing chain with retry + optional fallback."""
    chain = primary_llm.with_retry(
        stop_after_attempt=3,
        wait_exponential_jitter=True,
    )
    if fallback_llm is not None:
        fallback = fallback_llm.with_retry(
            stop_after_attempt=2,
            wait_exponential_jitter=True,
        )
        chain = chain.with_fallbacks([fallback])
    return chain


def build_vision_chain(primary_llm: BaseChatModel) -> Runnable:
    """Build an LCEL vision chain with retry only (no cheap VL fallback)."""
    return primary_llm.with_retry(
        stop_after_attempt=3,
        wait_exponential_jitter=True,
    )
```

**Step 4: 运行测试确认 pass**

```bash
uv run pytest tests/test_llm_utils.py -v
```

Expected: 5 passed

**Step 5: Commit**

```bash
git add backend/graph/llm_utils.py tests/test_llm_utils.py
git commit -m "[impl] Add LLM chain builders with retry/fallback and exception mapping"
```

---

## Task 5: Graph 生命周期节点 `[backend]`

**Files:**
- Create: `backend/graph/nodes/__init__.py`
- Create: `backend/graph/nodes/lifecycle.py`
- Test: `tests/test_graph_nodes_lifecycle.py`

**依赖:** Task 2 (CadJobState)

**Step 1: 创建 `backend/graph/nodes/__init__.py`**

```python
"""Graph node implementations."""
```

**Step 2: 编写 failing test**

`tests/test_graph_nodes_lifecycle.py`:

```python
"""Tests for lifecycle graph nodes: create, confirm, finalize."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.graph.state import CadJobState


class TestCreateJobNode:
    @pytest.fixture
    def initial_state(self) -> CadJobState:
        return CadJobState(
            job_id="test-123",
            input_type="text",
            input_text="make a gear",
            image_path=None,
            status="pending",
        )

    @pytest.mark.asyncio
    async def test_creates_db_record_and_sets_status(self, initial_state) -> None:
        from backend.graph.nodes.lifecycle import create_job_node

        with patch("backend.graph.nodes.lifecycle.create_job", new_callable=AsyncMock) as mock_create:
            result = await create_job_node(initial_state)

        mock_create.assert_called_once_with(
            job_id="test-123",
            input_type="text",
            input_text="make a gear",
        )
        assert result["status"] == "created"


class TestConfirmWithUserNode:
    @pytest.mark.asyncio
    async def test_merges_confirmed_params(self) -> None:
        from backend.graph.nodes.lifecycle import confirm_with_user_node

        state = CadJobState(
            job_id="test-123",
            input_type="text",
            status="awaiting_confirmation",
            confirmed_params={"diameter": 50, "teeth": 20},
            disclaimer_accepted=True,
        )
        result = await confirm_with_user_node(state)
        assert result["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_merges_confirmed_spec_for_drawing(self) -> None:
        from backend.graph.nodes.lifecycle import confirm_with_user_node

        state = CadJobState(
            job_id="test-123",
            input_type="drawing",
            status="awaiting_drawing_confirmation",
            confirmed_spec={"part_type": "rotational", "diameter": 30},
            disclaimer_accepted=True,
        )
        result = await confirm_with_user_node(state)
        assert result["status"] == "confirmed"


class TestFinalizeNode:
    @pytest.mark.asyncio
    async def test_completed_path(self) -> None:
        from backend.graph.nodes.lifecycle import finalize_node

        state = CadJobState(
            job_id="test-123",
            input_type="text",
            status="generating",
            step_path="/outputs/test-123/model.step",
            model_url="/outputs/test-123/model.glb",
            printability={"score": 0.95},
            error=None,
        )
        with patch("backend.graph.nodes.lifecycle.update_job", new_callable=AsyncMock):
            result = await finalize_node(state)

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_failed_path(self) -> None:
        from backend.graph.nodes.lifecycle import finalize_node

        state = CadJobState(
            job_id="test-123",
            input_type="text",
            status="failed",
            error="timeout",
            failure_reason="timeout",
        )
        with patch("backend.graph.nodes.lifecycle.update_job", new_callable=AsyncMock):
            result = await finalize_node(state)

        assert result["status"] == "failed"
```

**Step 3: 运行测试确认 fail**

```bash
uv run pytest tests/test_graph_nodes_lifecycle.py -v
```

Expected: `ModuleNotFoundError`

**Step 4: 实现 `backend/graph/nodes/lifecycle.py`**

```python
"""Lifecycle nodes: create_job, confirm_with_user, finalize."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.callbacks import adispatch_custom_event

from backend.graph.state import CadJobState, STATE_TO_ORM_MAPPING
from backend.models.job import create_job, update_job

logger = logging.getLogger(__name__)


async def create_job_node(state: CadJobState) -> dict[str, Any]:
    """Create DB Job record and dispatch job.created event."""
    await create_job(
        job_id=state["job_id"],
        input_type=state["input_type"],
        input_text=state.get("input_text") or "",
    )
    await adispatch_custom_event(
        "job.created",
        {"job_id": state["job_id"], "input_type": state["input_type"]},
    )
    return {"status": "created"}


async def confirm_with_user_node(state: CadJobState) -> dict[str, Any]:
    """Process Command(resume=...) data after interrupt.

    By the time this node executes, LangGraph has already merged the
    resume payload into state (confirmed_params / confirmed_spec / disclaimer_accepted).
    We just advance the status.
    """
    return {"status": "confirmed"}


async def finalize_node(state: CadJobState) -> dict[str, Any]:
    """Write final state to DB and dispatch terminal event."""
    is_failed = state.get("error") is not None or state.get("status") == "failed"
    final_status = "failed" if is_failed else "completed"

    # Build ORM update kwargs using STATE_TO_ORM_MAPPING
    orm_kwargs: dict[str, Any] = {"status": final_status}
    direct_fields = ["intent", "drawing_spec", "error", "result"]
    for field in direct_fields:
        val = state.get(field)
        if val is not None:
            orm_kwargs[field] = val

    for state_key, orm_col in STATE_TO_ORM_MAPPING.items():
        val = state.get(state_key)
        if val is not None:
            orm_kwargs[orm_col] = val

    await update_job(state["job_id"], **orm_kwargs)

    event_name = "job.failed" if is_failed else "job.completed"
    payload: dict[str, Any] = {"job_id": state["job_id"], "status": final_status}
    if is_failed:
        payload["error"] = state.get("error")
        payload["failure_reason"] = state.get("failure_reason")
    else:
        payload["model_url"] = state.get("model_url")
        payload["step_path"] = state.get("step_path")
        payload["printability"] = state.get("printability")

    await adispatch_custom_event(event_name, payload)
    return {"status": final_status}
```

**Step 5: 运行测试确认 pass**

```bash
uv run pytest tests/test_graph_nodes_lifecycle.py -v
```

Expected: 4 passed

**Step 6: Commit**

```bash
git add backend/graph/nodes/__init__.py backend/graph/nodes/lifecycle.py tests/test_graph_nodes_lifecycle.py
git commit -m "[impl] Add lifecycle graph nodes (create, confirm, finalize)"
```

---

## Task 6: Graph 分析节点 `[backend]`

**Files:**
- Create: `backend/graph/nodes/analysis.py`
- Test: `tests/test_graph_nodes_analysis.py`

**依赖:** Task 2, Task 4

**Step 1: 编写 failing test**

`tests/test_graph_nodes_analysis.py`:

```python
"""Tests for analysis graph nodes."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.graph.state import CadJobState


class TestAnalyzeIntentNode:
    @pytest.mark.asyncio
    async def test_success_returns_intent(self) -> None:
        from backend.graph.nodes.analysis import analyze_intent_node

        state = CadJobState(
            job_id="t1", input_type="text", input_text="make a 50mm gear",
            status="created",
        )
        mock_intent = {"description": "gear", "parameters": {"diameter": 50}}
        with patch("backend.graph.nodes.analysis._parse_intent", new_callable=AsyncMock, return_value=mock_intent):
            result = await analyze_intent_node(state)

        assert result["intent"] == mock_intent
        assert result["status"] == "intent_parsed"

    @pytest.mark.asyncio
    async def test_timeout_returns_failed(self) -> None:
        from backend.graph.nodes.analysis import analyze_intent_node

        state = CadJobState(
            job_id="t1", input_type="text", input_text="make a gear",
            status="created",
        )
        with patch(
            "backend.graph.nodes.analysis._parse_intent",
            new_callable=AsyncMock,
            side_effect=asyncio.TimeoutError(),
        ):
            result = await analyze_intent_node(state)

        assert result["status"] == "failed"
        assert result["failure_reason"] == "timeout"


class TestAnalyzeVisionNode:
    @pytest.mark.asyncio
    async def test_success_returns_drawing_spec(self) -> None:
        from backend.graph.nodes.analysis import analyze_vision_node

        state = CadJobState(
            job_id="t1", input_type="drawing", image_path="/tmp/test.jpg",
            status="created",
        )
        mock_spec = {"part_type": "rotational", "diameter": 30}
        with patch(
            "backend.graph.nodes.analysis.analyze_vision_spec",
            return_value=(mock_spec, "reasoning text"),
        ):
            result = await analyze_vision_node(state)

        assert result["drawing_spec"] == mock_spec
        assert result["status"] == "awaiting_drawing_confirmation"


class TestStubOrganicNode:
    @pytest.mark.asyncio
    async def test_returns_awaiting(self) -> None:
        from backend.graph.nodes.analysis import stub_organic_node

        state = CadJobState(
            job_id="t1", input_type="organic", input_text="a dragon sculpture",
            status="created",
        )
        result = await stub_organic_node(state)
        assert result["status"] == "awaiting_confirmation"
```

**Step 2: 运行测试确认 fail**

```bash
uv run pytest tests/test_graph_nodes_analysis.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: 实现 `backend/graph/nodes/analysis.py`**

```python
"""Analysis nodes: intent parsing, vision spec, organic stub."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.callbacks import adispatch_custom_event

from backend.graph.llm_utils import map_exception_to_failure_reason
from backend.graph.state import CadJobState

logger = logging.getLogger(__name__)

LLM_TIMEOUT_S = 60.0


async def _parse_intent(text: str) -> dict:
    """Async intent parsing — delegates to existing IntentParser."""
    from backend.core.intent_parser import IntentParser

    parser = IntentParser()
    return await parser.aparse(text)


async def analyze_intent_node(state: CadJobState) -> dict[str, Any]:
    """Parse user text into IntentSpec via LLM (with timeout)."""
    try:
        intent = await asyncio.wait_for(
            _parse_intent(state.get("input_text") or ""),
            timeout=LLM_TIMEOUT_S,
        )
    except Exception as exc:
        reason = map_exception_to_failure_reason(exc)
        logger.error("Intent analysis failed: %s (%s)", exc, reason)
        await adispatch_custom_event(
            "job.failed",
            {"job_id": state["job_id"], "error": str(exc), "failure_reason": reason},
        )
        return {"error": str(exc), "failure_reason": reason, "status": "failed"}

    # Match template if available
    matched_template = None
    try:
        from backend.api.generate import _match_template

        template_result = _match_template(state.get("input_text") or "")
        if template_result and template_result[0]:
            matched_template = template_result[0].name
    except Exception:
        pass  # Template matching is best-effort

    await adispatch_custom_event(
        "job.intent_analyzed",
        {"job_id": state["job_id"], "intent": intent, "matched_template": matched_template},
    )
    await adispatch_custom_event(
        "job.awaiting_confirmation",
        {"job_id": state["job_id"]},
    )
    return {
        "intent": intent,
        "matched_template": matched_template,
        "status": "awaiting_confirmation",
    }


async def analyze_vision_node(state: CadJobState) -> dict[str, Any]:
    """Run VL model to extract DrawingSpec from uploaded image (with timeout)."""
    await adispatch_custom_event(
        "job.vision_analyzing",
        {"job_id": state["job_id"]},
    )

    try:
        from backend.pipeline.pipeline import analyze_vision_spec

        spec, reasoning = await asyncio.wait_for(
            asyncio.to_thread(analyze_vision_spec, state["image_path"]),
            timeout=LLM_TIMEOUT_S,
        )
    except Exception as exc:
        reason = map_exception_to_failure_reason(exc)
        logger.error("Vision analysis failed: %s (%s)", exc, reason)
        await adispatch_custom_event(
            "job.failed",
            {"job_id": state["job_id"], "error": str(exc), "failure_reason": reason},
        )
        return {"error": str(exc), "failure_reason": reason, "status": "failed"}

    spec_dict = spec.model_dump() if hasattr(spec, "model_dump") else spec

    await adispatch_custom_event(
        "job.spec_ready",
        {"job_id": state["job_id"], "drawing_spec": spec_dict, "reasoning": reasoning},
    )
    await adispatch_custom_event(
        "job.awaiting_confirmation",
        {"job_id": state["job_id"]},
    )
    return {
        "drawing_spec": spec_dict,
        "status": "awaiting_drawing_confirmation",
    }


async def stub_organic_node(state: CadJobState) -> dict[str, Any]:
    """Organic input: no LLM analysis needed, go straight to HITL."""
    await adispatch_custom_event(
        "job.awaiting_confirmation",
        {"job_id": state["job_id"]},
    )
    return {"status": "awaiting_confirmation"}
```

**Step 4: 运行测试确认 pass**

```bash
uv run pytest tests/test_graph_nodes_analysis.py -v
```

Expected: 4 passed

**Step 5: Commit**

```bash
git add backend/graph/nodes/analysis.py tests/test_graph_nodes_analysis.py
git commit -m "[impl] Add analysis graph nodes (intent, vision, organic stub)"
```

---

## Task 7: Graph 生成节点 `[backend]`

**Files:**
- Create: `backend/graph/nodes/generation.py`
- Test: `tests/test_graph_nodes_generation.py`

**依赖:** Task 2, Task 3

**Step 1: 编写 failing test**

`tests/test_graph_nodes_generation.py`:

```python
"""Tests for generation graph nodes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.graph.state import CadJobState


class TestGenerateStepTextNode:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from backend.graph.nodes.generation import generate_step_text_node

        state = CadJobState(
            job_id="t1", input_type="text", status="confirmed",
            confirmed_params={"diameter": 50}, matched_template="gear_spur",
        )
        with patch(
            "backend.graph.nodes.generation._run_template_generation",
            return_value="/outputs/t1/model.step",
        ):
            result = await generate_step_text_node(state)

        assert result["step_path"] == "/outputs/t1/model.step"
        assert result["status"] == "generating"

    @pytest.mark.asyncio
    async def test_idempotent_skips_if_step_exists(self, tmp_path) -> None:
        from backend.graph.nodes.generation import generate_step_text_node

        step_file = tmp_path / "model.step"
        step_file.write_text("solid")
        state = CadJobState(
            job_id="t1", input_type="text", status="confirmed",
            step_path=str(step_file),
        )
        result = await generate_step_text_node(state)
        assert result == {}  # No-op


class TestGenerateStepDrawingNode:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from backend.graph.nodes.generation import generate_step_drawing_node

        state = CadJobState(
            job_id="t1", input_type="drawing", status="confirmed",
            image_path="/tmp/test.jpg",
            confirmed_spec={"part_type": "rotational"},
        )
        with patch("backend.graph.nodes.generation.generate_step_from_spec") as mock_gen:
            result = await generate_step_drawing_node(state)

        mock_gen.assert_called_once()
        assert result["status"] == "generating"

    @pytest.mark.asyncio
    async def test_idempotent_skips_if_step_exists(self, tmp_path) -> None:
        from backend.graph.nodes.generation import generate_step_drawing_node

        step_file = tmp_path / "model.step"
        step_file.write_text("solid")
        state = CadJobState(
            job_id="t1", input_type="drawing", status="confirmed",
            step_path=str(step_file),
        )
        result = await generate_step_drawing_node(state)
        assert result == {}
```

**Step 2: 运行测试确认 fail**

```bash
uv run pytest tests/test_graph_nodes_generation.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: 实现 `backend/graph/nodes/generation.py`**

```python
"""Generation nodes: text (template) and drawing (VL pipeline) paths."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from langchain_core.callbacks import adispatch_custom_event

from backend.graph.llm_utils import map_exception_to_failure_reason
from backend.graph.state import CadJobState

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path("outputs").resolve()


def _run_template_generation(
    job_id: str,
    confirmed_params: dict,
    matched_template: str | None,
    step_path: str,
) -> str:
    """Synchronous template generation — delegates to existing logic."""
    from backend.api.generate import _run_template_generation as _orig

    # Build a minimal job-like object for the legacy function
    from backend.models.job import Job, get_job

    class _MinimalJob:
        def __init__(self, jid: str, tpl: str | None, params: dict) -> None:
            self.job_id = jid
            self.intent = type("I", (), {"matched_template": tpl, "parameters": params})()
            self.precise_spec = type("P", (), {"confirmed_params": params})()

    job = _MinimalJob(job_id, matched_template, confirmed_params)
    _orig(job, confirmed_params, step_path)
    return step_path


async def generate_step_text_node(state: CadJobState) -> dict[str, Any]:
    """Generate STEP from text intent via TemplateEngine + Sandbox."""
    # Idempotent: skip if already generated
    existing = state.get("step_path")
    if existing and Path(existing).exists():
        return {}

    job_dir = OUTPUTS_DIR / state["job_id"]
    job_dir.mkdir(parents=True, exist_ok=True)
    step_path = str(job_dir / "model.step")

    await adispatch_custom_event(
        "job.generating",
        {"job_id": state["job_id"], "stage": "template"},
    )

    try:
        result_path = await asyncio.to_thread(
            _run_template_generation,
            state["job_id"],
            state.get("confirmed_params") or {},
            state.get("matched_template"),
            step_path,
        )
    except Exception as exc:
        reason = map_exception_to_failure_reason(exc)
        logger.error("Text generation failed: %s (%s)", exc, reason)
        return {"error": str(exc), "failure_reason": reason, "status": "failed"}

    return {"step_path": result_path, "status": "generating"}


async def generate_step_drawing_node(state: CadJobState) -> dict[str, Any]:
    """Generate STEP from confirmed DrawingSpec via VL pipeline."""
    # Idempotent: skip if already generated
    existing = state.get("step_path")
    if existing and Path(existing).exists():
        return {}

    job_dir = OUTPUTS_DIR / state["job_id"]
    job_dir.mkdir(parents=True, exist_ok=True)
    step_path = str(job_dir / "model.step")

    await adispatch_custom_event(
        "job.generating",
        {"job_id": state["job_id"], "stage": "drawing_pipeline"},
    )

    try:
        from backend.pipeline.pipeline import generate_step_from_spec

        await asyncio.to_thread(
            generate_step_from_spec,
            image_filepath=state["image_path"],
            drawing_spec=state.get("confirmed_spec") or state.get("drawing_spec"),
            output_filepath=step_path,
        )
    except Exception as exc:
        reason = map_exception_to_failure_reason(exc)
        logger.error("Drawing generation failed: %s (%s)", exc, reason)
        return {"error": str(exc), "failure_reason": reason, "status": "failed"}

    return {"step_path": step_path, "status": "generating"}
```

**Step 4: 运行测试确认 pass**

```bash
uv run pytest tests/test_graph_nodes_generation.py -v
```

Expected: 4 passed

**Step 5: Commit**

```bash
git add backend/graph/nodes/generation.py tests/test_graph_nodes_generation.py
git commit -m "[impl] Add generation graph nodes (text template + drawing pipeline)"
```

---

## Task 8: Graph 后处理节点 `[backend]`

**Files:**
- Create: `backend/graph/nodes/postprocess.py`
- Test: `tests/test_graph_nodes_postprocess.py`

**依赖:** Task 2

**Step 1: 编写 failing test**

`tests/test_graph_nodes_postprocess.py`:

```python
"""Tests for postprocess graph nodes."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.graph.state import CadJobState


class TestConvertPreviewNode:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from backend.graph.nodes.postprocess import convert_preview_node

        state = CadJobState(
            job_id="t1", input_type="text", status="generating",
            step_path="/outputs/t1/model.step",
        )
        with patch(
            "backend.graph.nodes.postprocess._convert_step_to_glb",
            return_value="/outputs/t1/model.glb",
        ):
            result = await convert_preview_node(state)

        assert result["model_url"] is not None
        assert "model.glb" in result["model_url"]

    @pytest.mark.asyncio
    async def test_failure_is_non_fatal(self) -> None:
        from backend.graph.nodes.postprocess import convert_preview_node

        state = CadJobState(
            job_id="t1", input_type="text", status="generating",
            step_path="/outputs/t1/model.step",
        )
        with patch(
            "backend.graph.nodes.postprocess._convert_step_to_glb",
            side_effect=Exception("GLB conversion failed"),
        ):
            result = await convert_preview_node(state)

        # Preview failure is non-fatal; model_url will be None
        assert result.get("model_url") is None


class TestCheckPrintabilityNode:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from backend.graph.nodes.postprocess import check_printability_node

        state = CadJobState(
            job_id="t1", input_type="text", status="generating",
            step_path="/outputs/t1/model.step",
        )
        mock_result = {"score": 0.92, "issues": []}
        with patch(
            "backend.graph.nodes.postprocess._run_printability_check",
            return_value=mock_result,
        ):
            result = await check_printability_node(state)

        assert result["printability"] == mock_result

    @pytest.mark.asyncio
    async def test_skips_if_no_step_path(self) -> None:
        from backend.graph.nodes.postprocess import check_printability_node

        state = CadJobState(
            job_id="t1", input_type="text", status="generating",
            step_path=None,
        )
        result = await check_printability_node(state)
        assert result == {}
```

**Step 2: 运行测试确认 fail**

```bash
uv run pytest tests/test_graph_nodes_postprocess.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: 实现 `backend/graph/nodes/postprocess.py`**

```python
"""Postprocess nodes: STEP→GLB preview, printability check."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from langchain_core.callbacks import adispatch_custom_event

from backend.graph.state import CadJobState

logger = logging.getLogger(__name__)

PREVIEW_TIMEOUT_S = 30.0


def _convert_step_to_glb(step_path: str) -> str | None:
    """Synchronous STEP→GLB conversion — delegates to existing logic."""
    from backend.api.generate import _convert_step_to_glb as _orig

    glb_path = str(Path(step_path).with_suffix(".glb"))
    _orig(step_path, glb_path)
    return glb_path


def _run_printability_check(step_path: str) -> dict | None:
    """Synchronous printability check — delegates to existing logic."""
    from backend.api.generate import _run_printability_check as _orig

    return _orig(step_path)


async def convert_preview_node(state: CadJobState) -> dict[str, Any]:
    """Convert STEP to GLB for 3D preview (non-fatal on failure)."""
    step_path = state.get("step_path")
    if not step_path:
        return {}

    try:
        glb_path = await asyncio.wait_for(
            asyncio.to_thread(_convert_step_to_glb, step_path),
            timeout=PREVIEW_TIMEOUT_S,
        )
    except Exception as exc:
        logger.warning("GLB preview conversion failed (non-fatal): %s", exc)
        return {"model_url": None}

    model_url = f"/outputs/{state['job_id']}/model.glb" if glb_path else None
    await adispatch_custom_event(
        "job.preview_ready",
        {"job_id": state["job_id"], "model_url": model_url},
    )
    return {"model_url": model_url}


async def check_printability_node(state: CadJobState) -> dict[str, Any]:
    """Run DfAM printability analysis."""
    step_path = state.get("step_path")
    if not step_path:
        return {}

    try:
        result = await asyncio.to_thread(_run_printability_check, step_path)
    except Exception as exc:
        logger.warning("Printability check failed (non-fatal): %s", exc)
        return {"printability": None}

    await adispatch_custom_event(
        "job.printability_ready",
        {"job_id": state["job_id"], "printability": result},
    )
    return {"printability": result}
```

**Step 4: 运行测试确认 pass**

```bash
uv run pytest tests/test_graph_nodes_postprocess.py -v
```

Expected: 4 passed

**Step 5: Commit**

```bash
git add backend/graph/nodes/postprocess.py tests/test_graph_nodes_postprocess.py
git commit -m "[impl] Add postprocess graph nodes (preview + printability)"
```

---

## Task 9: Graph 路由函数 `[backend]`

**Files:**
- Create: `backend/graph/routing.py`
- Test: `tests/test_graph_routing.py`

**Step 1: 编写 failing test**

`tests/test_graph_routing.py`:

```python
"""Tests for graph conditional routing functions."""

from backend.graph.state import CadJobState


class TestRouteByInputType:
    def test_text(self) -> None:
        from backend.graph.routing import route_by_input_type

        state = CadJobState(job_id="t1", input_type="text", status="created")
        assert route_by_input_type(state) == "text"

    def test_drawing(self) -> None:
        from backend.graph.routing import route_by_input_type

        state = CadJobState(job_id="t1", input_type="drawing", status="created")
        assert route_by_input_type(state) == "drawing"

    def test_organic(self) -> None:
        from backend.graph.routing import route_by_input_type

        state = CadJobState(job_id="t1", input_type="organic", status="created")
        assert route_by_input_type(state) == "organic"


class TestRouteAfterConfirm:
    def test_text_routes_to_text(self) -> None:
        from backend.graph.routing import route_after_confirm

        state = CadJobState(job_id="t1", input_type="text", status="confirmed")
        assert route_after_confirm(state) == "text"

    def test_drawing_routes_to_drawing(self) -> None:
        from backend.graph.routing import route_after_confirm

        state = CadJobState(job_id="t1", input_type="drawing", status="confirmed")
        assert route_after_confirm(state) == "drawing"

    def test_organic_routes_to_finalize(self) -> None:
        from backend.graph.routing import route_after_confirm

        state = CadJobState(job_id="t1", input_type="organic", status="confirmed")
        assert route_after_confirm(state) == "finalize"

    def test_failed_routes_to_finalize(self) -> None:
        from backend.graph.routing import route_after_confirm

        state = CadJobState(job_id="t1", input_type="text", status="failed")
        assert route_after_confirm(state) == "finalize"
```

**Step 2: 运行测试确认 fail**

```bash
uv run pytest tests/test_graph_routing.py -v
```

**Step 3: 实现 `backend/graph/routing.py`**

```python
"""Conditional edge functions for the CadJob StateGraph."""

from __future__ import annotations

from backend.graph.state import CadJobState


def route_by_input_type(state: CadJobState) -> str:
    """Route after create_job_node → analysis node by input type."""
    return state["input_type"]  # "text" | "drawing" | "organic"


def route_after_confirm(state: CadJobState) -> str:
    """Route after confirm_with_user_node → generation or finalize."""
    if state.get("status") == "failed":
        return "finalize"

    input_type = state["input_type"]
    if input_type == "organic":
        # Organic generation handled by external endpoint; skip to finalize
        return "finalize"
    return input_type  # "text" | "drawing"
```

**Step 4: 运行测试确认 pass**

```bash
uv run pytest tests/test_graph_routing.py -v
```

Expected: 6 passed

**Step 5: Commit**

```bash
git add backend/graph/routing.py tests/test_graph_routing.py
git commit -m "[impl] Add graph conditional routing functions"
```

---

## Task 10: Graph Builder 构建 `[backend][architecture]`

**Files:**
- Create: `backend/graph/builder.py`
- Modify: `backend/graph/__init__.py` (re-export)
- Test: `tests/test_graph_builder.py`

**依赖:** Task 5, 6, 7, 8, 9 (all nodes + routing)

**Step 1: 编写 failing test**

`tests/test_graph_builder.py`:

```python
"""Tests for the compiled CadJob StateGraph."""

from __future__ import annotations

import pytest


class TestBuildGraph:
    def test_compile_without_checkpointer(self) -> None:
        from backend.graph.builder import build_graph

        graph = build_graph()
        assert graph is not None

    def test_graph_has_expected_nodes(self) -> None:
        from backend.graph.builder import build_graph

        graph = build_graph()
        node_names = set(graph.nodes.keys())
        expected = {
            "create_job",
            "analyze_intent", "analyze_vision", "stub_organic",
            "confirm_with_user",
            "generate_step_text", "generate_step_drawing",
            "convert_preview", "check_printability",
            "finalize",
        }
        # __start__ and __end__ are internal LangGraph nodes
        assert expected.issubset(node_names), f"Missing: {expected - node_names}"


class TestGetCompiledGraph:
    @pytest.mark.asyncio
    async def test_compiles_with_checkpointer(self, tmp_path) -> None:
        from backend.graph.builder import get_compiled_graph

        db_path = str(tmp_path / "test.db")
        graph = await get_compiled_graph(db_path)
        assert graph is not None
```

**Step 2: 运行测试确认 fail**

```bash
uv run pytest tests/test_graph_builder.py -v
```

**Step 3: 实现 `backend/graph/builder.py`**

```python
"""Build and compile the CadJob StateGraph."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.graph.nodes.analysis import (
    analyze_intent_node,
    analyze_vision_node,
    stub_organic_node,
)
from backend.graph.nodes.generation import (
    generate_step_drawing_node,
    generate_step_text_node,
)
from backend.graph.nodes.lifecycle import (
    confirm_with_user_node,
    create_job_node,
    finalize_node,
)
from backend.graph.nodes.postprocess import (
    check_printability_node,
    convert_preview_node,
)
from backend.graph.routing import route_after_confirm, route_by_input_type
from backend.graph.state import CadJobState


def build_graph() -> StateGraph:
    """Build the StateGraph (uncompiled) for testing."""
    workflow = StateGraph(CadJobState)

    # ── Nodes ──
    workflow.add_node("create_job", create_job_node)
    workflow.add_node("analyze_intent", analyze_intent_node)
    workflow.add_node("analyze_vision", analyze_vision_node)
    workflow.add_node("stub_organic", stub_organic_node)
    workflow.add_node("confirm_with_user", confirm_with_user_node)
    workflow.add_node("generate_step_text", generate_step_text_node)
    workflow.add_node("generate_step_drawing", generate_step_drawing_node)
    workflow.add_node("convert_preview", convert_preview_node)
    workflow.add_node("check_printability", check_printability_node)
    workflow.add_node("finalize", finalize_node)

    # ── Edges ──
    workflow.add_edge(START, "create_job")

    # create_job → route to analysis by input type
    workflow.add_conditional_edges(
        "create_job",
        route_by_input_type,
        {
            "text": "analyze_intent",
            "drawing": "analyze_vision",
            "organic": "stub_organic",
        },
    )

    # All analysis nodes → confirm
    workflow.add_edge("analyze_intent", "confirm_with_user")
    workflow.add_edge("analyze_vision", "confirm_with_user")
    workflow.add_edge("stub_organic", "confirm_with_user")

    # confirm → route to generation by input type
    workflow.add_conditional_edges(
        "confirm_with_user",
        route_after_confirm,
        {
            "text": "generate_step_text",
            "drawing": "generate_step_drawing",
            "finalize": "finalize",  # organic or failed
        },
    )

    # Generation → postprocess → finalize
    workflow.add_edge("generate_step_text", "convert_preview")
    workflow.add_edge("generate_step_drawing", "convert_preview")
    workflow.add_edge("convert_preview", "check_printability")
    workflow.add_edge("check_printability", "finalize")
    workflow.add_edge("finalize", END)

    return workflow.compile()


async def get_compiled_graph(db_path: str):
    """Compile graph with AsyncSqliteSaver checkpointer for production."""
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    checkpointer = AsyncSqliteSaver.from_conn_string(db_path)
    await checkpointer.setup()

    workflow = StateGraph(CadJobState)

    # ── Nodes (same as build_graph) ──
    workflow.add_node("create_job", create_job_node)
    workflow.add_node("analyze_intent", analyze_intent_node)
    workflow.add_node("analyze_vision", analyze_vision_node)
    workflow.add_node("stub_organic", stub_organic_node)
    workflow.add_node("confirm_with_user", confirm_with_user_node)
    workflow.add_node("generate_step_text", generate_step_text_node)
    workflow.add_node("generate_step_drawing", generate_step_drawing_node)
    workflow.add_node("convert_preview", convert_preview_node)
    workflow.add_node("check_printability", check_printability_node)
    workflow.add_node("finalize", finalize_node)

    # ── Edges (same as build_graph) ──
    workflow.add_edge(START, "create_job")
    workflow.add_conditional_edges(
        "create_job",
        route_by_input_type,
        {"text": "analyze_intent", "drawing": "analyze_vision", "organic": "stub_organic"},
    )
    workflow.add_edge("analyze_intent", "confirm_with_user")
    workflow.add_edge("analyze_vision", "confirm_with_user")
    workflow.add_edge("stub_organic", "confirm_with_user")
    workflow.add_conditional_edges(
        "confirm_with_user",
        route_after_confirm,
        {"text": "generate_step_text", "drawing": "generate_step_drawing", "finalize": "finalize"},
    )
    workflow.add_edge("generate_step_text", "convert_preview")
    workflow.add_edge("generate_step_drawing", "convert_preview")
    workflow.add_edge("convert_preview", "check_printability")
    workflow.add_edge("check_printability", "finalize")
    workflow.add_edge("finalize", END)

    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["confirm_with_user"],
    )
```

**Step 4: 更新 `backend/graph/__init__.py`**

```python
"""LangGraph CAD Job orchestration."""

from backend.graph.builder import build_graph, get_compiled_graph

__all__ = ["build_graph", "get_compiled_graph"]
```

**Step 5: 运行测试确认 pass**

```bash
uv run pytest tests/test_graph_builder.py -v
```

Expected: 3 passed

**Step 6: Commit**

```bash
git add backend/graph/builder.py backend/graph/__init__.py tests/test_graph_builder.py
git commit -m "[impl] Add StateGraph builder with conditional routing and checkpointing"
```

---

## Task 11: API 层切换 — Graph 初始化 `[backend]`

**Files:**
- Modify: `backend/main.py:37-40` (lifespan)
- Test: 手动验证

**依赖:** Task 10

**Step 1: 在 lifespan 中初始化 Graph**

在 `backend/main.py` 的 `lifespan` 函数中，`await init_db()` 之后添加：

```python
from backend.graph import get_compiled_graph
from backend.db.database import DB_PATH

app.state.cad_graph = await get_compiled_graph(str(DB_PATH))
```

**Step 2: 验证启动无报错**

```bash
uv run python -c "
import asyncio
from backend.main import app
# Just verify the lifespan can initialize
print('main.py imports OK')
"
```

**Step 3: Commit**

```bash
git add backend/main.py
git commit -m "[impl] Initialize LangGraph in app lifespan"
```

---

## Task 12: API 层切换 — POST /api/v1/jobs `[backend]`

**Files:**
- Modify: `backend/api/v1/jobs.py:136-228` (create_text_job endpoint)
- Test: `tests/test_jobs_api_graph.py`

**依赖:** Task 11

**Step 1: 编写 failing test**

`tests/test_jobs_api_graph.py`:

```python
"""Tests for Graph-powered /api/v1/jobs endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.fixture
def mock_graph():
    """Mock the compiled graph on app.state."""
    graph = MagicMock()

    async def fake_astream_events(input_state, config, version):
        # Simulate a minimal event stream
        yield {"event": "on_custom_event", "name": "job.created", "data": {"job_id": input_state["job_id"]}}
        yield {"event": "on_custom_event", "name": "job.intent_analyzed", "data": {"job_id": input_state["job_id"]}}
        yield {"event": "on_custom_event", "name": "job.awaiting_confirmation", "data": {"job_id": input_state["job_id"]}}

    graph.astream_events = fake_astream_events
    app.state.cad_graph = graph
    return graph


class TestCreateJobViaGraph:
    @pytest.mark.asyncio
    async def test_text_job_returns_sse(self, mock_graph) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/jobs",
                json={"input_type": "text", "input_text": "make a gear"},
                headers={"Accept": "text/event-stream"},
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
```

> **注意：** 此测试依赖 jobs.py 端点已切换到 Graph 模式。先写测试，然后修改端点。

**Step 2: 修改 `backend/api/v1/jobs.py` 的 POST 端点**

替换 `create_text_job` 端点的 SSE 生成逻辑为：

```python
@router.post("")
async def create_text_job(body: CreateJobRequest, request: Request):
    job_id = str(uuid.uuid4())
    cad_graph = request.app.state.cad_graph
    config = {"configurable": {"thread_id": job_id}}

    initial_state = {
        "job_id": job_id,
        "input_type": body.input_type,
        "input_text": body.input_text or "",
        "image_path": None,
        "status": "pending",
    }

    async def event_stream():
        async for event in cad_graph.astream_events(initial_state, config=config, version="v2"):
            if event["event"] == "on_custom_event":
                yield _sse(event["name"], event["data"])

    return EventSourceResponse(event_stream())
```

**Step 3: 运行测试**

```bash
uv run pytest tests/test_jobs_api_graph.py -v
```

**Step 4: Commit**

```bash
git add backend/api/v1/jobs.py tests/test_jobs_api_graph.py
git commit -m "[impl] Switch POST /api/v1/jobs to Graph astream_events"
```

---

## Task 13: API 层切换 — POST /api/v1/jobs/upload `[backend]`

**Files:**
- Modify: `backend/api/v1/jobs.py:230-320` (upload endpoint)

**依赖:** Task 12

**Step 1: 修改 upload 端点**

替换 upload 端点的 SSE 生成逻辑为类似 Task 12 的 Graph 模式，但 `input_type="drawing"` 且 `image_path` 指向上传文件路径。

**Step 2: 运行全量测试**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -5
```

**Step 3: Commit**

```bash
git add backend/api/v1/jobs.py
git commit -m "[impl] Switch POST /api/v1/jobs/upload to Graph astream_events"
```

---

## Task 14: API 层切换 — POST /api/v1/jobs/{id}/confirm `[backend]`

**Files:**
- Modify: `backend/api/v1/jobs.py:396-585` (confirm endpoint)
- Test: `tests/test_jobs_api_graph.py` (append)

**依赖:** Task 12

**Step 1: 编写 failing test**

Append to `tests/test_jobs_api_graph.py`:

```python
class TestConfirmJobViaGraph:
    @pytest.mark.asyncio
    async def test_confirm_resumes_graph(self, mock_graph) -> None:
        # Override astream_events to simulate confirm flow
        async def fake_resume(command, config, version):
            yield {"event": "on_custom_event", "name": "job.generating", "data": {"job_id": "test-id"}}
            yield {"event": "on_custom_event", "name": "job.completed", "data": {"job_id": "test-id"}}

        mock_graph.astream_events = fake_resume

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/jobs/test-id/confirm",
                json={"confirmed_params": {"diameter": 50}, "disclaimer_accepted": True},
            )
        assert resp.status_code == 200
```

**Step 2: 修改 confirm 端点**

替换为 `Command(resume=...)` 模式：

```python
@router.post("/{job_id}/confirm")
async def confirm_job(job_id: str, body: ConfirmJobRequest, request: Request):
    from langgraph.types import Command

    cad_graph = request.app.state.cad_graph
    config = {"configurable": {"thread_id": job_id}}

    resume_data = body.model_dump()

    async def event_stream():
        async for event in cad_graph.astream_events(
            Command(resume=resume_data),
            config=config,
            version="v2",
        ):
            if event["event"] == "on_custom_event":
                yield _sse(event["name"], event["data"])

    return EventSourceResponse(event_stream())
```

**Step 3: 运行测试**

```bash
uv run pytest tests/test_jobs_api_graph.py -v
```

**Step 4: Commit**

```bash
git add backend/api/v1/jobs.py tests/test_jobs_api_graph.py
git commit -m "[impl] Switch POST /api/v1/jobs/{id}/confirm to Graph Command(resume)"
```

---

## Task 15: 废弃代码清理 `[backend]`

**Files:**
- Modify: `backend/api/v1/jobs.py` (remove old imports and dead code)

**依赖:** Task 12, 13, 14

**Step 1: 从 jobs.py 中移除旧 SSE 引用**

1. 删除对 `_event_queues`、`emit_event`、`cleanup_queue`、`PipelineBridge` 的 import
2. 删除手写 SSE 生成器函数（`_text_sse_generator` 等已在 Task 12-14 替换）
3. 删除 `_finalize_sse` 函数（已被 Graph 的 postprocess + finalize 节点替代）

**Step 2: 验证 generate.py 不受影响**

```bash
uv run python -c "from backend.api.generate import router; print('generate.py OK')"
```

Expected: `generate.py OK`

**Step 3: 验证 grep 清理完整**

```bash
grep -n "_event_queues\|emit_event\|PipelineBridge\|cleanup_queue" backend/api/v1/jobs.py
```

Expected: 无输出

**Step 4: 运行全量测试**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -5
```

**Step 5: Commit**

```bash
git add backend/api/v1/jobs.py
git commit -m "[impl] Remove deprecated _event_queues/PipelineBridge from jobs.py"
```

---

## Task 16: 更新前端 SSE 事件名 `[frontend]`

**Files:**
- Modify: `frontend/src/` (所有消费 SSE 事件的文件)

**Step 1: 搜索旧事件名**

```bash
grep -rn "job_created\|intent_parsed\|analyzing\|drawing_spec_ready\|awaiting_confirmation\|generating\|refining\|completed\|failed" frontend/src/ --include="*.ts" --include="*.tsx"
```

**Step 2: 替换为新命名**

| 旧名 | 新名 |
|------|------|
| `job_created` | `job.created` |
| `intent_parsed` | `job.intent_analyzed` |
| `analyzing` | `job.vision_analyzing` |
| `drawing_spec_ready` | `job.spec_ready` |
| `awaiting_confirmation` | `job.awaiting_confirmation` |
| `generating` | `job.generating` |
| `refining` | `job.generating` |
| `completed` | `job.completed` |
| `failed` | `job.failed` |

**Step 3: TypeScript 编译检查**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

**Step 4: Commit**

```bash
git add frontend/src/
git commit -m "[impl] Adapt frontend SSE event names to job.* format"
```

---

## Task 17: 更新现有测试事件名 `[test]`

**Files:**
- Modify: `tests/test_sse_bridge.py`
- Modify: `tests/test_pipeline_integration.py`
- Modify: 其他引用旧事件名的测试文件

**Step 1: 搜索旧事件名**

```bash
grep -rn "job_created\|intent_parsed\|\"generating\"\|\"refining\"\|\"completed\"\|\"failed\"" tests/ --include="*.py"
```

**Step 2: 更新断言中的事件名**

**Step 3: 运行全量测试**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -5
```

**Step 4: Commit**

```bash
git add tests/
git commit -m "[impl] Update test assertions to use new job.* event names"
```

---

## Task 18: HITL 集成测试 `[test]`

**Files:**
- Create: `tests/test_graph_hitl.py`

**依赖:** Task 10

**Step 1: 编写 HITL 集成测试**

```python
"""Integration tests for HITL interrupt/resume via LangGraph."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


class TestHitlInterruptResume:
    @pytest.mark.asyncio
    async def test_text_path_interrupts_before_confirm(self) -> None:
        from backend.graph.builder import get_compiled_graph
        import tempfile, os

        db_path = os.path.join(tempfile.mkdtemp(), "test.db")
        graph = await get_compiled_graph(db_path)

        config = {"configurable": {"thread_id": "hitl-test-1"}}
        initial = {
            "job_id": "hitl-test-1",
            "input_type": "text",
            "input_text": "make a gear",
            "status": "pending",
        }

        # Patch all external calls
        with (
            patch("backend.graph.nodes.lifecycle.create_job", new_callable=AsyncMock),
            patch("backend.graph.nodes.lifecycle.update_job", new_callable=AsyncMock),
            patch("backend.graph.nodes.analysis._parse_intent", new_callable=AsyncMock, return_value={"desc": "gear"}),
        ):
            # First run — should stop at interrupt_before confirm
            events = []
            async for event in graph.astream_events(initial, config=config, version="v2"):
                if event["event"] == "on_custom_event":
                    events.append(event["name"])

            assert "job.created" in events
            assert "job.intent_analyzed" in events
            assert "job.awaiting_confirmation" in events
            # Should NOT have generating events yet
            assert "job.generating" not in events

    @pytest.mark.asyncio
    async def test_resume_after_confirm_completes(self) -> None:
        from backend.graph.builder import get_compiled_graph
        from langgraph.types import Command
        import tempfile, os

        db_path = os.path.join(tempfile.mkdtemp(), "test.db")
        graph = await get_compiled_graph(db_path)
        config = {"configurable": {"thread_id": "hitl-test-2"}}

        initial = {
            "job_id": "hitl-test-2",
            "input_type": "text",
            "input_text": "make a gear",
            "status": "pending",
        }

        with (
            patch("backend.graph.nodes.lifecycle.create_job", new_callable=AsyncMock),
            patch("backend.graph.nodes.lifecycle.update_job", new_callable=AsyncMock),
            patch("backend.graph.nodes.analysis._parse_intent", new_callable=AsyncMock, return_value={"desc": "gear"}),
            patch("backend.graph.nodes.generation._run_template_generation", return_value="/tmp/model.step"),
            patch("backend.graph.nodes.postprocess._convert_step_to_glb", return_value="/tmp/model.glb"),
            patch("backend.graph.nodes.postprocess._run_printability_check", return_value={"score": 0.9}),
        ):
            # First run — interrupts
            async for _ in graph.astream_events(initial, config=config, version="v2"):
                pass

            # Resume with confirm data
            resume_events = []
            async for event in graph.astream_events(
                Command(resume={
                    "confirmed_params": {"diameter": 50},
                    "disclaimer_accepted": True,
                }),
                config=config,
                version="v2",
            ):
                if event["event"] == "on_custom_event":
                    resume_events.append(event["name"])

            assert "job.generating" in resume_events
            assert "job.completed" in resume_events or "job.failed" in resume_events
```

**Step 2: 运行测试**

```bash
uv run pytest tests/test_graph_hitl.py -v
```

**Step 3: Commit**

```bash
git add tests/test_graph_hitl.py
git commit -m "[impl] Add HITL interrupt/resume integration tests"
```

---

## Task 19: LLM 超时测试 `[test]`

**Files:**
- Append to: `tests/test_graph_nodes_analysis.py`

**Step 1: 添加超时行为测试**

```python
class TestTimeoutBehavior:
    @pytest.mark.asyncio
    async def test_intent_timeout_returns_failure_reason(self) -> None:
        from backend.graph.nodes.analysis import analyze_intent_node

        state = CadJobState(job_id="t1", input_type="text", input_text="x", status="created")
        with patch(
            "backend.graph.nodes.analysis._parse_intent",
            new_callable=AsyncMock,
            side_effect=asyncio.TimeoutError(),
        ):
            result = await analyze_intent_node(state)

        assert result["status"] == "failed"
        assert result["failure_reason"] == "timeout"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_vision_timeout_returns_failure_reason(self) -> None:
        from backend.graph.nodes.analysis import analyze_vision_node

        state = CadJobState(job_id="t1", input_type="drawing", image_path="/tmp/x.jpg", status="created")
        with patch(
            "backend.graph.nodes.analysis.analyze_vision_spec",
            side_effect=asyncio.TimeoutError(),
        ):
            result = await analyze_vision_node(state)

        assert result["status"] == "failed"
        assert result["failure_reason"] == "timeout"
```

**Step 2: 运行测试**

```bash
uv run pytest tests/test_graph_nodes_analysis.py -v
```

**Step 3: Commit**

```bash
git add tests/test_graph_nodes_analysis.py
git commit -m "[impl] Add LLM timeout behavior tests"
```

---

## Task 20: 验收检查 `[test]`

**Files:** 无新文件

**Step 1: 全量测试**

```bash
uv run pytest tests/ -v 2>&1 | tail -20
```

Expected: 全部通过（≥1192 个）

**Step 2: 验证 _event_queues 已从 jobs.py 清除**

```bash
grep -r "_event_queues" backend/api/v1/jobs.py
```

Expected: 无输出

**Step 3: 验证 generate.py（organic 旧端点）仍可正常运行**

```bash
uv run python -c "
from backend.api.generate import router
from backend.pipeline.sse_bridge import PipelineBridge
print('Organic endpoints + PipelineBridge still available')
"
```

Expected: `Organic endpoints + PipelineBridge still available`

**Step 4: TypeScript 编译检查**

```bash
cd frontend && npx tsc --noEmit
```

**Step 5: Commit**

```bash
git add -A
git commit -m "[impl] LangGraph CAD pipeline migration complete — all tests pass"
```

---

## 依赖关系图

```
Task 1 (deps)
   ├── Task 2 (state)     ─┐
   ├── Task 3 (rename)     ├── Task 5 (lifecycle nodes) ──┐
   └── Task 4 (llm utils) ─┤                              │
                            ├── Task 6 (analysis nodes) ───┤
                            ├── Task 7 (generation nodes) ─┤
                            └── Task 8 (postprocess nodes)─┤
                                                           │
                            Task 9 (routing) ──────────────┤
                                                           │
                            Task 10 (builder) ─────────────┤
                                                           │
                            Task 11 (app init) ────────────┤
                                                           │
                            Task 12 (POST /jobs) ──────────┤
                            Task 13 (POST /upload) ────────┤
                            Task 14 (POST /confirm) ───────┤
                                                           │
                            Task 15 (cleanup) ─────────────┤
                            Task 16 (frontend SSE) ────────┤
                            Task 17 (test event names) ────┤
                            Task 18 (HITL integration) ────┤
                            Task 19 (timeout tests) ───────┤
                                                           │
                            Task 20 (acceptance) ──────────┘
```

**可并行执行组：**
- **Group A:** Task 2 + Task 3 + Task 4（互相独立）
- **Group B:** Task 5 + Task 6 + Task 7 + Task 8 + Task 9（节点各自独立，仅依赖 Group A）
- **Group C:** Task 16 + Task 17（前端和测试事件名更新，互相独立）
