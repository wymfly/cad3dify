# M3 白盒化 UI — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让用户"看透"管道执行过程——实时查看每个节点的状态、耗时和 AI 推理决策链。

**Architecture:** 后端用 `@timed_node` 装饰器自动发射 `node.started/completed/failed` 生命周期事件，消除各节点中的重复 `_safe_dispatch` 样板代码。节点通过返回 `_reasoning` 键传递推理数据。前端在现有 Steps 进度条旁新增 ReactFlow DAG 专家视图 Tab，通过 EventSource (`useJobEvents`) 订阅节点状态驱动 DAG 节点状态机。点击已完成节点打开右侧 Drawer 展示输入/输出/推理过程。

**Tech Stack:** Python decorators, LangGraph custom events, @xyflow/react (ReactFlow), Ant Design Tabs/Drawer/Collapse

**Design doc:** `docs/plans/2026-03-02-m3-whitebox-ui-design.md`

---

## Agent Team 并行感知

### 域标签

| 标签 | 任务 |
|------|------|
| `[backend]` | Task 0, 1, 2, 3, 4 |
| `[frontend]` | Task 5, 6, 7, 8 |
| `[test]` | Task 0, 1, 2, 3, 4 (含 TDD), Task 9 |

### 文件交叉矩阵

| Agent | 预期修改文件 |
|-------|------------|
| **A (backend)** | `backend/graph/decorators.py` (新建), `backend/graph/nodes/lifecycle.py`, `backend/graph/nodes/analysis.py`, `backend/graph/nodes/generation.py`, `backend/graph/nodes/postprocess.py`, `backend/graph/nodes/organic.py`, `tests/test_timed_node.py` (新建), `tests/test_graph_nodes_generation.py` |
| **B (frontend)** | `frontend/package.json`, `frontend/src/components/PipelineDAG/*` (新建 6 文件), `frontend/src/components/PipelinePanel/index.tsx` (新建), `frontend/src/hooks/useJobEvents.ts`, `frontend/src/pages/Generate/index.tsx` |

**交叉**: 无。Backend 和 Frontend 文件集完全独立。

### 执行结构

```
Phase 0 (串行, team lead): Task 0 — @timed_node 装饰器核心
Phase 1 (并行):
    Agent A [backend]: Task 1-4 — 所有节点装饰器化 + reasoning
    Agent B [frontend]: Task 5-8 — ReactFlow DAG + Drawer + 集成
Phase 2 (串行): Task 9 — 集成验证
```

---

## Phase 0: 装饰器核心 (串行)

### Task 0: @timed_node 装饰器

**Files:**
- Create: `backend/graph/decorators.py`
- Create: `tests/test_timed_node.py`

**Step 1: Write failing tests**

```python
# tests/test_timed_node.py
"""Tests for @timed_node decorator."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from backend.graph.decorators import timed_node, _summarize_outputs


class TestSummarizeOutputs:
    def test_filters_underscore_keys(self):
        result = _summarize_outputs({"intent": {"x": 1}, "_reasoning": {"y": 2}})
        assert "_reasoning" not in result
        assert "intent" in result

    def test_truncates_long_strings(self):
        result = _summarize_outputs({"code": "x" * 500})
        assert len(result["code"]) <= 200

    def test_empty_dict(self):
        assert _summarize_outputs({}) == {}


class TestTimedNode:
    @pytest.mark.asyncio
    async def test_dispatches_started_and_completed(self):
        @timed_node("test_node")
        async def my_node(state):
            return {"output": "value"}

        dispatched = []
        with patch(
            "backend.graph.decorators._safe_dispatch",
            new_callable=AsyncMock,
            side_effect=lambda name, data: dispatched.append((name, data)),
        ):
            result = await my_node({"job_id": "j1"})

        assert len(dispatched) == 2
        assert dispatched[0][0] == "node.started"
        assert dispatched[0][1]["node"] == "test_node"
        assert dispatched[1][0] == "node.completed"
        assert dispatched[1][1]["elapsed_ms"] >= 0
        assert result == {"output": "value"}

    @pytest.mark.asyncio
    async def test_extracts_reasoning_from_result(self):
        @timed_node("test_node")
        async def my_node(state):
            return {"output": "v", "_reasoning": {"why": "because"}}

        dispatched = []
        with patch(
            "backend.graph.decorators._safe_dispatch",
            new_callable=AsyncMock,
            side_effect=lambda name, data: dispatched.append((name, data)),
        ):
            result = await my_node({"job_id": "j1"})

        # _reasoning removed from result (not written to state)
        assert "_reasoning" not in result
        # reasoning attached to node.completed event
        completed = dispatched[1][1]
        assert completed["reasoning"] == {"why": "because"}

    @pytest.mark.asyncio
    async def test_dispatches_failed_on_exception(self):
        @timed_node("test_node")
        async def my_node(state):
            raise ValueError("boom")

        dispatched = []
        with patch(
            "backend.graph.decorators._safe_dispatch",
            new_callable=AsyncMock,
            side_effect=lambda name, data: dispatched.append((name, data)),
        ):
            with pytest.raises(ValueError, match="boom"):
                await my_node({"job_id": "j1"})

        assert dispatched[1][0] == "node.failed"
        assert "boom" in dispatched[1][1]["error"]

    @pytest.mark.asyncio
    async def test_outputs_summary_in_completed(self):
        @timed_node("test_node")
        async def my_node(state):
            return {"step_path": "/tmp/model.step", "status": "ok"}

        dispatched = []
        with patch(
            "backend.graph.decorators._safe_dispatch",
            new_callable=AsyncMock,
            side_effect=lambda name, data: dispatched.append((name, data)),
        ):
            await my_node({"job_id": "j1"})

        summary = dispatched[1][1]["outputs_summary"]
        assert summary["step_path"] == "/tmp/model.step"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_timed_node.py -v`
Expected: FAIL (module not found)

**Step 3: Implement the decorator**

```python
# backend/graph/decorators.py
"""@timed_node — unified lifecycle event decorator for graph nodes."""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, Awaitable

from backend.graph.nodes.lifecycle import _safe_dispatch
from backend.graph.state import CadJobState

MAX_SUMMARY_STR_LEN = 200


def _summarize_outputs(result: dict[str, Any]) -> dict[str, Any]:
    """Create a JSON-safe summary of node outputs, excluding _ prefixed keys."""
    summary: dict[str, Any] = {}
    for k, v in result.items():
        if k.startswith("_"):
            continue
        if isinstance(v, str) and len(v) > MAX_SUMMARY_STR_LEN:
            summary[k] = v[:MAX_SUMMARY_STR_LEN] + "..."
        elif isinstance(v, (dict, list)):
            # Keep structure but cap serialized length
            import json
            s = json.dumps(v, ensure_ascii=False, default=str)
            if len(s) > MAX_SUMMARY_STR_LEN:
                summary[k] = f"({type(v).__name__}, {len(s)} chars)"
            else:
                summary[k] = v
        else:
            summary[k] = v
    return summary


def timed_node(node_name: str):
    """Decorator that wraps async graph nodes with lifecycle events.

    Automatically dispatches:
    - ``node.started`` before node execution
    - ``node.completed`` after (with elapsed_ms, reasoning, outputs_summary)
    - ``node.failed`` on exception (re-raises after dispatch)

    Nodes can return a ``_reasoning`` key in their result dict to attach
    structured reasoning data to the ``node.completed`` event. The key is
    removed from the result before it is written to graph state.
    """

    def decorator(
        fn: Callable[[CadJobState], Awaitable[dict[str, Any]]],
    ) -> Callable[[CadJobState], Awaitable[dict[str, Any]]]:
        @functools.wraps(fn)
        async def wrapper(state: CadJobState) -> dict[str, Any]:
            job_id = state.get("job_id", "unknown")
            t0 = time.time()

            await _safe_dispatch("node.started", {
                "job_id": job_id,
                "node": node_name,
                "timestamp": t0,
            })

            try:
                result = await fn(state)
            except Exception as exc:
                elapsed_ms = round((time.time() - t0) * 1000)
                await _safe_dispatch("node.failed", {
                    "job_id": job_id,
                    "node": node_name,
                    "elapsed_ms": elapsed_ms,
                    "error": str(exc),
                })
                raise

            elapsed_ms = round((time.time() - t0) * 1000)
            reasoning = result.pop("_reasoning", None)

            await _safe_dispatch("node.completed", {
                "job_id": job_id,
                "node": node_name,
                "elapsed_ms": elapsed_ms,
                "reasoning": reasoning,
                "outputs_summary": _summarize_outputs(result),
            })

            return result

        return wrapper

    return decorator
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_timed_node.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add backend/graph/decorators.py tests/test_timed_node.py
git commit -m "feat(m3): add @timed_node decorator with lifecycle events"
```

---

## Phase 1: 节点重构 (Agent A — backend)

### Task 1: 装饰 lifecycle 节点

**Files:**
- Modify: `backend/graph/nodes/lifecycle.py`

**Step 1: Apply @timed_node to create_job_node, confirm_with_user_node, finalize_node**

Import the decorator and apply to all three nodes. Move `_safe_dispatch("job.created", ...)` out of `create_job_node` — it's now handled by `node.completed`. Keep `job.failed` and `job.completed` terminal events in `finalize_node` (they carry business data needed by the frontend).

Add `_reasoning` to each node:

- `create_job_node`: `{"input_routing": f"input_type={input_type}"}`
- `confirm_with_user_node`: `{"confirmation": "user confirmed parameters"}`
- `finalize_node`: `{"final_status": final_status, "total_stages": len(stages)}`

**Key constraint**: `finalize_node` still needs to dispatch `job.completed`/`job.failed` because the frontend `handleSSEEvent` relies on `status: "completed"/"failed"` to set terminal UI state. The `@timed_node` `node.completed` event supplements this (for the DAG) but does NOT replace the business terminal event.

**Step 2: Run existing tests**

Run: `uv run pytest tests/ -x -q`
Expected: All pass (decorator adds events transparently)

**Step 3: Commit**

```bash
git add backend/graph/nodes/lifecycle.py
git commit -m "feat(m3): decorate lifecycle nodes with @timed_node"
```

### Task 2: 装饰 analysis 节点 + 添加 reasoning

**Files:**
- Modify: `backend/graph/nodes/analysis.py`

**Step 1: Apply @timed_node to analyze_intent_node and analyze_vision_node**

Remove redundant `_safe_dispatch` calls that are now covered by `node.started/completed`:
- Remove: `job.vision_analyzing` (行 173) → replaced by `node.started`
- Keep: `job.intent_analyzed` (行 138-148) → carries `params`/`template_name` for frontend ParamForm
- Keep: `job.spec_ready` (行 214-216) → carries `drawing_spec` for DrawingSpecReview
- Keep: `job.awaiting_confirmation` → HITL interaction point
- Keep: `job.failed` in error paths → terminal business event

Remove manual timing code (`_t0`, `_duration`, `token_stats.stages.append`). The decorator handles timing via `node.completed.elapsed_ms`. (Note: token_stats stages aggregation moves to a future improvement.)

Add `_reasoning`:

```python
# analyze_intent_node
"_reasoning": {
    "part_type": part_type or "未识别",
    "template_match": f"匹配模板: {matched_template}" if matched_template else "无匹配模板",
    "candidate_count": str(len(candidates)) + " 候选模板",
    "recommendations": f"{len(recommendations)} 条工程标准建议",
}

# analyze_vision_node
"_reasoning": {
    "spec_source": "cache" if cached else "VL 模型分析",
    "part_type": spec_dict.get("part_type", "unknown") if isinstance(spec_dict, dict) else "unknown",
}
```

**Step 2: Run tests**

Run: `uv run pytest tests/ -x -q`
Expected: All pass

**Step 3: Commit**

```bash
git add backend/graph/nodes/analysis.py
git commit -m "feat(m3): decorate analysis nodes, add reasoning traces"
```

### Task 3: 装饰 generation + postprocess 节点

**Files:**
- Modify: `backend/graph/nodes/generation.py`
- Modify: `backend/graph/nodes/postprocess.py`

**Step 1: Apply @timed_node to all 4 nodes**

`generate_step_text_node`, `generate_step_drawing_node`:
- Remove: `job.generating` SSE dispatch (行 61-64, 77-80, 113-115) → replaced by `node.started` + `node.completed`
- Keep: `job.failed` dispatch in error handler (needed for frontend terminal state)
- Remove: Manual timing code

Add `_reasoning`:

```python
# generate_step_text_node
"_reasoning": {
    "method": result.method,
    "template": result.template_name or "N/A",
    "step_path": result.step_path,
}

# generate_step_drawing_node
"_reasoning": {
    "pipeline": "V2 drawing pipeline",
    "image_path": image_path,
}
```

`convert_preview_node`, `check_printability_node`:
- Remove: `job.preview_ready` → data moved to `node.completed.outputs_summary`
- Remove: `job.printability_ready` → data moved to `node.completed.outputs_summary`

Add `_reasoning`:

```python
# convert_preview_node
"_reasoning": {
    "format": "GLB",
    "result": "成功" if glb_path else "跳过（无 STEP 文件）",
}

# check_printability_node
"_reasoning": {
    "printable": str(result.get("printable", "N/A")) if result else "检查跳过",
    "issues_count": str(len(result.get("issues", []))) if result else "0",
    "recommendations_count": str(len(all_recs)),
}
```

**Important**: After removing `job.preview_ready` and `job.printability_ready`, the frontend `handleSSEEvent` won't receive these. But these events currently don't trigger any state change in `handleSSEEvent` (they're not in the switch cases). So removal is safe. The EventSource-based `useJobEvents` has them registered, but they're informational only.

**Step 2: Update generation tests for decorator**

The existing `tests/test_graph_nodes_generation.py` mocks `_safe_dispatch`. The decorator now calls `_safe_dispatch` too. Add `_safe_dispatch` mock if not already present:

```python
# Verify existing tests still pass with decorator (it swallows RuntimeError in _safe_dispatch)
```

**Step 3: Run tests**

Run: `uv run pytest tests/ -x -q`
Expected: All pass

**Step 4: Commit**

```bash
git add backend/graph/nodes/generation.py backend/graph/nodes/postprocess.py
git commit -m "feat(m3): decorate generation + postprocess nodes"
```

### Task 4: 装饰 organic 节点

**Files:**
- Modify: `backend/graph/nodes/organic.py`

**Step 1: Apply @timed_node to analyze_organic_node, generate_organic_mesh_node, postprocess_organic_node**

Organic nodes are more complex:
- `analyze_organic_node`: Remove `job.organic_spec_ready` (move data to node.completed). Keep `job.awaiting_confirmation` and `job.failed`.
- `generate_organic_mesh_node`: Keep `job.generating` with progress updates (sub-step progress can't be captured by the decorator alone, keep manual dispatch for progress events within the long-running generation).
- `postprocess_organic_node`: Keep `job.post_processing` sub-step events (7 sub-steps with individual progress). These are fine-grained progress events that supplement the decorator's lifecycle events.

Add `_reasoning`:

```python
# analyze_organic_node
"_reasoning": {
    "description": organic_spec.get("prompt", "")[:100] if isinstance(organic_spec, dict) else "",
    "provider": state.get("organic_provider", "auto"),
    "quality": state.get("organic_quality_mode", "standard"),
}

# generate_organic_mesh_node
"_reasoning": {
    "provider": provider_name,
    "mesh_generated": "true" if raw_mesh_path else "false",
}

# postprocess_organic_node
"_reasoning": {
    "steps_completed": "load,repair,scale,boolean,validate,export",
    "warnings_count": str(len(state.get("organic_warnings", []))),
}
```

**Step 2: Run tests**

Run: `uv run pytest tests/ -x -q`
Expected: All pass

**Step 3: Commit**

```bash
git add backend/graph/nodes/organic.py
git commit -m "feat(m3): decorate organic nodes, add reasoning traces"
```

---

## Phase 1: 前端 DAG (Agent B — frontend)

### Task 5: 安装 ReactFlow + 创建拓扑定义

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/components/PipelineDAG/topology.ts`

**Step 1: Install @xyflow/react**

```bash
cd frontend && npm install @xyflow/react
```

**Step 2: Create topology definition**

```typescript
// frontend/src/components/PipelineDAG/topology.ts
import type { Node, Edge } from '@xyflow/react';

export interface PipelineNode {
  id: string;
  label: string;
  group: 'init' | 'analysis' | 'hitl' | 'generation' | 'postprocess' | 'final';
}

export interface PipelineTopology {
  nodes: PipelineNode[];
  edges: Array<{ source: string; target: string }>;
}

const ALL_NODES: PipelineNode[] = [
  { id: 'create_job', label: '创建任务', group: 'init' },
  { id: 'analyze_intent', label: '意图解析', group: 'analysis' },
  { id: 'analyze_vision', label: '图纸分析', group: 'analysis' },
  { id: 'analyze_organic', label: '有机分析', group: 'analysis' },
  { id: 'confirm_with_user', label: '用户确认', group: 'hitl' },
  { id: 'generate_step_text', label: '文本生成', group: 'generation' },
  { id: 'generate_step_drawing', label: '图纸生成', group: 'generation' },
  { id: 'generate_organic_mesh', label: '有机生成', group: 'generation' },
  { id: 'postprocess_organic', label: '有机后处理', group: 'generation' },
  { id: 'convert_preview', label: 'GLB 预览', group: 'postprocess' },
  { id: 'check_printability', label: '可打印性检查', group: 'postprocess' },
  { id: 'finalize', label: '完成', group: 'final' },
];

const ALL_EDGES = [
  { source: 'create_job', target: 'analyze_intent' },
  { source: 'create_job', target: 'analyze_vision' },
  { source: 'create_job', target: 'analyze_organic' },
  { source: 'analyze_intent', target: 'confirm_with_user' },
  { source: 'analyze_vision', target: 'confirm_with_user' },
  { source: 'analyze_organic', target: 'confirm_with_user' },
  { source: 'confirm_with_user', target: 'generate_step_text' },
  { source: 'confirm_with_user', target: 'generate_step_drawing' },
  { source: 'confirm_with_user', target: 'generate_organic_mesh' },
  { source: 'generate_step_text', target: 'convert_preview' },
  { source: 'generate_step_drawing', target: 'convert_preview' },
  { source: 'generate_organic_mesh', target: 'postprocess_organic' },
  { source: 'postprocess_organic', target: 'finalize' },
  { source: 'convert_preview', target: 'check_printability' },
  { source: 'check_printability', target: 'finalize' },
];

/** Path-specific node IDs */
const PATH_NODES: Record<string, string[]> = {
  text: [
    'create_job', 'analyze_intent', 'confirm_with_user',
    'generate_step_text', 'convert_preview', 'check_printability', 'finalize',
  ],
  drawing: [
    'create_job', 'analyze_vision', 'confirm_with_user',
    'generate_step_drawing', 'convert_preview', 'check_printability', 'finalize',
  ],
  organic: [
    'create_job', 'analyze_organic', 'confirm_with_user',
    'generate_organic_mesh', 'postprocess_organic', 'finalize',
  ],
};

/** Filter topology by input_type, return ReactFlow-compatible nodes and edges. */
export function getFilteredTopology(
  inputType: string | null,
): { nodes: Node[]; edges: Edge[] } {
  const visibleIds = new Set(
    inputType && PATH_NODES[inputType]
      ? PATH_NODES[inputType]
      : ALL_NODES.map((n) => n.id),
  );

  const filteredNodes = ALL_NODES.filter((n) => visibleIds.has(n.id));
  const filteredEdges = ALL_EDGES.filter(
    (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
  );

  // Layout: vertical, 200px apart
  const nodes: Node[] = filteredNodes.map((n, i) => ({
    id: n.id,
    type: 'pipelineNode',
    position: { x: 200, y: i * 100 },
    data: { label: n.label, group: n.group },
  }));

  const edges: Edge[] = filteredEdges.map((e) => ({
    id: `${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    type: 'animatedEdge',
    animated: false,
  }));

  return { nodes, edges };
}
```

**Step 3: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/PipelineDAG/topology.ts
git commit -m "feat(m3): install @xyflow/react, add pipeline topology"
```

### Task 6: NodeCard + AnimatedEdge 自定义组件

**Files:**
- Create: `frontend/src/components/PipelineDAG/NodeCard.tsx`
- Create: `frontend/src/components/PipelineDAG/AnimatedEdge.tsx`

**Step 1: Create NodeCard**

```typescript
// frontend/src/components/PipelineDAG/NodeCard.tsx
import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Tag } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';

export type NodeStatus = 'pending' | 'running' | 'completed' | 'failed';

interface NodeCardData {
  label: string;
  group: string;
  status?: NodeStatus;
  elapsedMs?: number;
}

const STATUS_CONFIG: Record<NodeStatus, { color: string; icon: React.ReactNode }> = {
  pending: { color: 'default', icon: <ClockCircleOutlined /> },
  running: { color: 'processing', icon: <LoadingOutlined /> },
  completed: { color: 'success', icon: <CheckCircleOutlined /> },
  failed: { color: 'error', icon: <CloseCircleOutlined /> },
};

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function NodeCard({ data }: { data: NodeCardData }) {
  const status = data.status || 'pending';
  const config = STATUS_CONFIG[status];

  return (
    <div
      style={{
        padding: '8px 16px',
        borderRadius: 8,
        border: `2px solid ${status === 'running' ? '#1677ff' : '#d9d9d9'}`,
        background: status === 'failed' ? '#fff2f0' : '#fff',
        minWidth: 140,
        textAlign: 'center',
        cursor: status === 'completed' || status === 'failed' ? 'pointer' : 'default',
      }}
    >
      <Handle type="target" position={Position.Top} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center' }}>
        <Tag color={config.color} icon={config.icon} style={{ margin: 0 }}>
          {data.label}
        </Tag>
      </div>
      {data.elapsedMs != null && (
        <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
          {formatMs(data.elapsedMs)}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export default memo(NodeCard);
```

**Step 2: Create AnimatedEdge**

```typescript
// frontend/src/components/PipelineDAG/AnimatedEdge.tsx
import { memo } from 'react';
import { BaseEdge, getStraightPath, type EdgeProps } from '@xyflow/react';

function AnimatedEdge(props: EdgeProps) {
  const { sourceX, sourceY, targetX, targetY, style, ...rest } = props;
  const [edgePath] = getStraightPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
  });

  return (
    <BaseEdge
      {...rest}
      path={edgePath}
      style={{
        ...style,
        strokeWidth: 2,
        stroke: props.animated ? '#1677ff' : '#d9d9d9',
      }}
    />
  );
}

export default memo(AnimatedEdge);
```

**Step 3: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/PipelineDAG/NodeCard.tsx frontend/src/components/PipelineDAG/AnimatedEdge.tsx
git commit -m "feat(m3): add NodeCard and AnimatedEdge components"
```

### Task 7: NodeInspector Drawer + ReasoningCard

**Files:**
- Create: `frontend/src/components/PipelineDAG/ReasoningCard.tsx`
- Create: `frontend/src/components/PipelineDAG/NodeInspector.tsx`

**Step 1: Create ReasoningCard**

```typescript
// frontend/src/components/PipelineDAG/ReasoningCard.tsx
import { Collapse, Empty, Typography } from 'antd';

const { Text } = Typography;

interface ReasoningCardProps {
  reasoning: Record<string, string> | null;
}

const LABEL_MAP: Record<string, string> = {
  part_type: '零件类型识别',
  part_type_detection: '零件类型识别',
  template_match: '模板匹配',
  template_selection: '模板选择',
  candidate_count: '候选模板数',
  recommendations: '工程标准建议',
  method: '生成方法',
  template: '使用模板',
  pipeline: '生成管道',
  printable: '可打印性',
  issues_count: '问题数量',
  recommendations_count: '建议数量',
  input_routing: '输入路由',
  confirmation: '确认状态',
  final_status: '最终状态',
  spec_source: '分析来源',
  format: '输出格式',
  result: '转换结果',
};

export default function ReasoningCard({ reasoning }: ReasoningCardProps) {
  if (!reasoning || Object.keys(reasoning).length === 0) {
    return <Empty description="无推理数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const items = Object.entries(reasoning).map(([key, value]) => ({
    key,
    label: LABEL_MAP[key] || key,
    children: <Text>{value}</Text>,
  }));

  return (
    <Collapse
      size="small"
      defaultActiveKey={items.map((i) => i.key)}
      items={items}
    />
  );
}
```

**Step 2: Create NodeInspector**

```typescript
// frontend/src/components/PipelineDAG/NodeInspector.tsx
import { Drawer, Descriptions, Tag, Divider, Typography } from 'antd';
import ReasoningCard from './ReasoningCard.tsx';
import type { NodeStatus } from './NodeCard.tsx';

const { Title } = Typography;

export interface NodeInspectorData {
  nodeId: string;
  label: string;
  status: NodeStatus;
  elapsedMs?: number;
  reasoning?: Record<string, string> | null;
  outputsSummary?: Record<string, unknown> | null;
  error?: string;
}

interface NodeInspectorProps {
  open: boolean;
  data: NodeInspectorData | null;
  onClose: () => void;
}

const STATUS_LABELS: Record<NodeStatus, { text: string; color: string }> = {
  pending: { text: '等待中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
};

export default function NodeInspector({ open, data, onClose }: NodeInspectorProps) {
  if (!data) return null;

  const statusInfo = STATUS_LABELS[data.status];

  return (
    <Drawer
      title={data.label}
      open={open}
      onClose={onClose}
      width={420}
      styles={{ body: { padding: '16px' } }}
    >
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="节点">
          <code>{data.nodeId}</code>
        </Descriptions.Item>
        <Descriptions.Item label="状态">
          <Tag color={statusInfo.color}>{statusInfo.text}</Tag>
        </Descriptions.Item>
        {data.elapsedMs != null && (
          <Descriptions.Item label="耗时">
            {data.elapsedMs < 1000
              ? `${data.elapsedMs}ms`
              : `${(data.elapsedMs / 1000).toFixed(1)}s`}
          </Descriptions.Item>
        )}
        {data.error && (
          <Descriptions.Item label="错误">
            <Tag color="error">{data.error}</Tag>
          </Descriptions.Item>
        )}
      </Descriptions>

      {data.outputsSummary && Object.keys(data.outputsSummary).length > 0 && (
        <>
          <Divider orientation="left" plain>
            输出摘要
          </Divider>
          <Descriptions column={1} size="small" bordered>
            {Object.entries(data.outputsSummary).map(([key, value]) => (
              <Descriptions.Item key={key} label={key}>
                {typeof value === 'string'
                  ? value
                  : JSON.stringify(value, null, 2).slice(0, 200)}
              </Descriptions.Item>
            ))}
          </Descriptions>
        </>
      )}

      <Divider orientation="left" plain>
        推理过程
      </Divider>
      <ReasoningCard reasoning={data.reasoning ?? null} />
    </Drawer>
  );
}
```

**Step 3: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/PipelineDAG/ReasoningCard.tsx frontend/src/components/PipelineDAG/NodeInspector.tsx
git commit -m "feat(m3): add NodeInspector Drawer + ReasoningCard"
```

### Task 8: PipelineDAG 主组件 + PipelinePanel + 集成

**Files:**
- Create: `frontend/src/components/PipelineDAG/index.tsx`
- Create: `frontend/src/components/PipelinePanel/index.tsx`
- Modify: `frontend/src/hooks/useJobEvents.ts`
- Modify: `frontend/src/pages/Generate/index.tsx`

**Step 1: Extend useJobEvents to register node lifecycle events**

In `frontend/src/hooks/useJobEvents.ts`, add new event types to `SSE_EVENT_TYPES`:

```typescript
const SSE_EVENT_TYPES = [
  'status',
  'progress',
  'job.created',
  'job.intent_analyzed',
  'job.awaiting_confirmation',
  'job.vision_analyzing',
  'job.spec_ready',
  'job.generating',
  'job.completed',
  'job.failed',
  // M3: node lifecycle events
  'node.started',
  'node.completed',
  'node.failed',
  // M2: additional events
  'job.preview_ready',
  'job.printability_ready',
] as const;
```

**Step 2: Create PipelineDAG main component**

```typescript
// frontend/src/components/PipelineDAG/index.tsx
import { useState, useCallback, useEffect, useMemo } from 'react';
import { ReactFlow, Background, Controls } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import NodeCard from './NodeCard.tsx';
import AnimatedEdge from './AnimatedEdge.tsx';
import NodeInspector from './NodeInspector.tsx';
import type { NodeInspectorData } from './NodeInspector.tsx';
import type { NodeStatus } from './NodeCard.tsx';
import { getFilteredTopology } from './topology.ts';
import type { JobEvent } from '../../hooks/useJobEvents.ts';

export interface NodeState {
  status: NodeStatus;
  elapsedMs?: number;
  reasoning?: Record<string, string> | null;
  outputsSummary?: Record<string, unknown> | null;
  error?: string;
}

const nodeTypes = { pipelineNode: NodeCard };
const edgeTypes = { animatedEdge: AnimatedEdge };

interface PipelineDAGProps {
  inputType: string | null;
  events: JobEvent[];
}

export default function PipelineDAG({ inputType, events }: PipelineDAGProps) {
  const [nodeStates, setNodeStates] = useState<Map<string, NodeState>>(new Map());
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [inspectorData, setInspectorData] = useState<NodeInspectorData | null>(null);

  // Process events into node states
  useEffect(() => {
    const states = new Map<string, NodeState>();

    for (const evt of events) {
      const node = (evt as Record<string, unknown>).node as string | undefined;
      if (!node) continue;

      const status = evt.status as string;

      if (status === 'node.started' || (evt as Record<string, unknown>).timestamp) {
        // node.started event — check if this looks like a started event
        if (!states.has(node) || states.get(node)!.status === 'pending') {
          states.set(node, { status: 'running' });
        }
      }
    }

    // Second pass: overwrite with completed/failed
    for (const evt of events) {
      const evtAny = evt as Record<string, unknown>;
      const node = evtAny.node as string | undefined;
      if (!node) continue;

      if (evtAny.elapsed_ms != null && evtAny.error == null && evtAny.outputs_summary != null) {
        // node.completed
        states.set(node, {
          status: 'completed',
          elapsedMs: evtAny.elapsed_ms as number,
          reasoning: evtAny.reasoning as Record<string, string> | null,
          outputsSummary: evtAny.outputs_summary as Record<string, unknown>,
        });
      } else if (evtAny.elapsed_ms != null && evtAny.error != null) {
        // node.failed
        states.set(node, {
          status: 'failed',
          elapsedMs: evtAny.elapsed_ms as number,
          error: evtAny.error as string,
        });
      }
    }

    setNodeStates(states);
  }, [events]);

  const { nodes: baseNodes, edges: baseEdges } = useMemo(
    () => getFilteredTopology(inputType),
    [inputType],
  );

  // Enrich nodes with status data
  const nodes = useMemo(
    () =>
      baseNodes.map((n) => {
        const state = nodeStates.get(n.id);
        return {
          ...n,
          data: {
            ...n.data,
            status: state?.status || 'pending',
            elapsedMs: state?.elapsedMs,
          },
        };
      }),
    [baseNodes, nodeStates],
  );

  // Animate edges whose source is completed
  const edges = useMemo(
    () =>
      baseEdges.map((e) => {
        const sourceState = nodeStates.get(e.source);
        return {
          ...e,
          animated: sourceState?.status === 'completed',
        };
      }),
    [baseEdges, nodeStates],
  );

  const handleNodeClick = useCallback(
    (_: unknown, node: { id: string; data: { label: string } }) => {
      const state = nodeStates.get(node.id);
      if (!state || state.status === 'pending') return;

      setInspectorData({
        nodeId: node.id,
        label: node.data.label,
        status: state.status,
        elapsedMs: state.elapsedMs,
        reasoning: state.reasoning,
        outputsSummary: state.outputsSummary,
        error: state.error,
      });
      setInspectorOpen(true);
    },
    [nodeStates],
  );

  return (
    <div style={{ height: 500, border: '1px solid #f0f0f0', borderRadius: 8 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={handleNodeClick}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls />
      </ReactFlow>

      <NodeInspector
        open={inspectorOpen}
        data={inspectorData}
        onClose={() => setInspectorOpen(false)}
      />
    </div>
  );
}
```

**Step 3: Create PipelinePanel (Tab container)**

```typescript
// frontend/src/components/PipelinePanel/index.tsx
import { Tabs } from 'antd';
import {
  NodeIndexOutlined,
  UnorderedListOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';
import PipelineDAG from '../PipelineDAG/index.tsx';
import type { JobEvent } from '../../hooks/useJobEvents.ts';

interface PipelinePanelProps {
  /** The existing workflow progress component (Steps) */
  progressView: React.ReactNode;
  /** Input type for DAG path filtering */
  inputType: string | null;
  /** SSE events for DAG node state tracking */
  events: JobEvent[];
}

export default function PipelinePanel({
  progressView,
  inputType,
  events,
}: PipelinePanelProps) {
  return (
    <Tabs
      defaultActiveKey="progress"
      size="small"
      items={[
        {
          key: 'progress',
          label: (
            <span>
              <UnorderedListOutlined /> 进度
            </span>
          ),
          children: progressView,
        },
        {
          key: 'dag',
          label: (
            <span>
              <NodeIndexOutlined /> 管道
            </span>
          ),
          children: (
            <PipelineDAG inputType={inputType} events={events} />
          ),
        },
      ]}
    />
  );
}
```

**Step 4: Integrate into Generate page**

In `frontend/src/pages/Generate/index.tsx`, replace raw `<GenerateWorkflow>` with `<PipelinePanel>`:

```typescript
// Add imports:
import PipelinePanel from '../../components/PipelinePanel/index.tsx';
import { useJobEvents } from '../../hooks/useJobEvents.ts';

// Inside Generate component, add:
const { events: dagEvents } = useJobEvents({ jobId: workflow.jobId });

// Replace:
//   <GenerateWorkflow state={workflow} onPhaseChange={() => {}} />
// With:
<PipelinePanel
  progressView={<GenerateWorkflow state={workflow} onPhaseChange={() => {}} />}
  inputType={workflow.phase !== 'idle' ? 'text' : null}  // or detect from workflow
  events={dagEvents}
/>
```

**Note**: Detect `inputType` from the workflow context. If `workflow.drawingSpec` is set → `"drawing"`, otherwise `"text"`. Add this logic to the Generate component.

**Step 5: Verify TypeScript + visual test**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 6: Commit**

```bash
git add frontend/src/components/PipelineDAG/index.tsx frontend/src/components/PipelinePanel/index.tsx frontend/src/hooks/useJobEvents.ts frontend/src/pages/Generate/index.tsx
git commit -m "feat(m3): add PipelineDAG, PipelinePanel, integrate into Generate page"
```

---

## Phase 2: 集成验证 (串行)

### Task 9: 全量测试 + TypeScript 验证

**Files:** None (verification only)

**Step 1: Run full backend tests**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass (1266+ tests)

**Step 2: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 4: Run lint**

Run: `cd frontend && npm run lint`
Expected: No errors (or only pre-existing warnings)

**Step 5: Commit integration fixes if any**

```bash
git add -A
git commit -m "fix(m3): integration fixes from Phase 2 verification"
```

---

## 验收标准检查

| 标准 | 实现方式 | Task |
|------|---------|------|
| 每个管道节点 dispatch `node.started` 和 `node.completed` | @timed_node 装饰器 | 0-4 |
| 含 `elapsed_ms` | 装饰器自动计算 | 0 |
| 至少 3 个关键节点有 reasoning 数据 | 全节点覆盖 `_reasoning` | 1-4 |
| 前端看板支持分支可视化 | ReactFlow + 路径过滤 | 5-8 |
| 点击已完成节点查看输入/输出/决策 | NodeInspector Drawer | 7-8 |
| 每个节点独立显示耗时 | NodeCard 显示 elapsed_ms | 6 |
