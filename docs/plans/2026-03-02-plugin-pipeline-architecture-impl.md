# Plugin Pipeline Architecture — 并行感知实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 CADPilot 的 LangGraph 管线从硬编码拓扑重构为全插件式节点架构。

**Architecture:** `@register_node` 声明式注册 → `DependencyResolver` Kahn 拓扑排序 → `PipelineBuilder` 动态生成 `StateGraph`。`PipelineState`（assets dict + data dict + 自定义 merge reducer）替代 `CadJobState`。`NodeContext` 作为视图层隔离节点实现。

**Tech Stack:** Python 3.10+, LangGraph (StateGraph, AsyncSqliteSaver, Command), Pydantic v2, FastAPI, React + TypeScript (ReactFlow), pytest

**OpenSpec Change:** `openspec/changes/plugin-pipeline-architecture/`

**审查修复集成：** Codex (3/10) + Claude sub-agent (6/10) 审查的 11 个 findings 已全部纳入修复。

---

## 关键架构修复（审查后调整）

| 问题 | 原方案 | 修复 |
|------|--------|------|
| 图编译 vs input_type | per-input_type 编译不同图 | **编译时注册全部节点 + 条件边路由**。input_type 过滤仅用于 validate API |
| finalize 拓扑顺序 | requires=[] | **引入 `is_terminal` 标记**，resolver 自动连接所有叶节点 → terminal |
| 迁移安全性 | 直接重写 builder.py | **新 builder 写到 `builder_new.py`**，`USE_NEW_BUILDER` 环境变量开关（默认 OFF） |
| State merge 语义 | to_state_diff 返回全量 dict | **assets/data 使用 `Annotated[dict, _merge_dicts]` 自定义 reducer** |
| HITL resume | 未提及 | **Task P2-3 补充 confirm 端点 resume_data 格式迁移** |
| 事件分发 | _wrap_node 重复 timed_node | **迁移时移除 @timed_node，_wrap_node 统一处理** |
| API 路由 | 新建 /pipeline/nodes 等 | **扩展现有 pipeline_config.py 路由**，保持前端兼容 |
| 前端 DAG | 全新 PipelineConfigurator | **改造现有 PipelineDAG + PipelineConfigBar 组件** |

---

## 执行阶段与并行结构

```
Phase 0 ── 串行：接口定义 + 特征测试 ─────────────────────── team-lead
    │
    ├── Task 0.1  核心数据模型（descriptor, context, state）
    ├── Task 0.2  NodeRegistry + @register_node + discovery
    ├── Task 0.3  DependencyResolver（Kahn + OR + 冲突检测）
    ├── Task 0.4  特征测试（锁定当前 SSE/HITL/DB 行为）
    └── Task 0.5  PipelineBuilder（builder_new.py, 条件边, reducer）
    │
Phase 1 ── 并行：模块实现 ────────────────────────────────── 3 agents
    │
    ├── Agent A: 前半程节点迁移（analysis + generation）
    │   ├── Task A.1  create_job + confirm_with_user
    │   ├── Task A.2  analyze_intent + analyze_vision + analyze_organic
    │   └── Task A.3  generate_step_text + generate_step_drawing + generate_organic_mesh
    │
    ├── Agent B: 后半程节点迁移（postprocess + organic split）
    │   ├── Task B.1  convert_preview + check_printability + analyze_dfam
    │   ├── Task B.2  mesh_repair + mesh_scale + boolean_cuts + export_formats
    │   └── Task B.3  finalize（assets 动态收集）
    │
    └── Agent C: 预设 + API + 兼容层
        ├── Task C.1  presets.py + compat.py
        ├── Task C.2  后端 API（扩展 pipeline_config.py）
        └── Task C.3  jobs.py 改造（initial_state + confirm resume）
    │
Phase 2 ── 串行：集成验证 ─────────────────────────────────── team-lead
    │
    ├── Task N.1  合并 + 开关切换 USE_NEW_BUILDER=1
    ├── Task N.2  全量测试 + 三条路径 E2E 验证
    └── Task N.3  旧文件清理
    │
Phase 3 ── 单独：前端改造 ─────────────────────────────────── Agent D
    │
    ├── Task D.1  改造 PipelineDAG 组件（动态节点、策略标签）
    ├── Task D.2  改造 PipelineConfigBar（节点级配置面板）
    └── Task D.3  运行时监控模式 + TypeScript 编译
```

---

## 文件交叉矩阵

| 文件 | Phase 0 | Agent A | Agent B | Agent C | Phase 2 | Agent D |
|------|---------|---------|---------|---------|---------|---------|
| `backend/graph/descriptor.py` (新建) | ✅ | | | | | |
| `backend/graph/context.py` (新建) | ✅ | | | | | |
| `backend/graph/pipeline_state.py` (新建) | ✅ | | | | | |
| `backend/graph/configs/base.py` (新建) | ✅ | | | | | |
| `backend/graph/registry.py` (新建) | ✅ | | | | | |
| `backend/graph/discovery.py` (新建) | ✅ | | | | | |
| `backend/graph/resolver.py` (新建) | ✅ | | | | | |
| `backend/graph/builder_new.py` (新建) | ✅ | | | | ✅ | |
| `tests/test_descriptor.py` (新建) | ✅ | | | | | |
| `tests/test_context.py` (新建) | ✅ | | | | | |
| `tests/test_registry.py` (新建) | ✅ | | | | | |
| `tests/test_resolver.py` (新建) | ✅ | | | | | |
| `tests/test_builder_new.py` (新建) | ✅ | | | | | |
| `tests/test_characterization.py` (新建) | ✅ | | | | | |
| `backend/graph/nodes/lifecycle.py` | | ✅ | | | | |
| `backend/graph/nodes/analysis.py` | | ✅ | | | | |
| `backend/graph/nodes/generation.py` | | ✅ | | | | |
| `backend/graph/nodes/organic.py` | | ✅ | | | | |
| `tests/test_graph_nodes_*.py` | | ✅ | | | | |
| `backend/graph/nodes/postprocess.py` | | | ✅ | | | |
| `backend/graph/nodes/dfam.py` | | | ✅ | | | |
| `backend/graph/nodes/mesh_repair.py` (新建) | | | ✅ | | | |
| `backend/graph/nodes/mesh_scale.py` (新建) | | | ✅ | | | |
| `backend/graph/nodes/boolean_cuts.py` (新建) | | | ✅ | | | |
| `backend/graph/nodes/export_formats.py` (新建) | | | ✅ | | | |
| `tests/test_mesh_pipeline.py` (新建) | | | ✅ | | | |
| `backend/graph/presets.py` (新建) | | | | ✅ | | |
| `backend/graph/compat.py` (新建) | | | | ✅ | | |
| `backend/api/v1/pipeline_config.py` | | | | ✅ | | |
| `backend/api/v1/jobs.py` | | | | ✅ | | |
| `tests/test_presets.py` (新建) | | | | ✅ | | |
| `tests/test_pipeline_api.py` (新建) | | | | ✅ | | |
| `backend/graph/builder.py` (旧) | | | | | ✅ | |
| `backend/main.py` | | | | | ✅ | |
| `frontend/src/components/PipelineDAG/` | | | | | | ✅ |
| `frontend/src/components/PipelineConfigBar/` | | | | | | ✅ |
| `frontend/src/services/api.ts` | | | | | | ✅ |
| `frontend/src/types/pipeline.ts` | | | | | | ✅ |

**文件独立性评估：Agent A / B / C / D 之间零交叉 ✅**

---

## Phase 0: 接口定义 + 特征测试（串行，team-lead）

Phase 0 是所有并行工作的基础——定义共享接口和数据模型，所有 agent 将基于这些接口编码。

### Task 0.1: 核心数据模型

**Files:**
- Create: `backend/graph/descriptor.py`
- Create: `backend/graph/configs/__init__.py`
- Create: `backend/graph/configs/base.py`
- Create: `backend/graph/context.py`
- Create: `backend/graph/pipeline_state.py`
- Test: `tests/test_descriptor.py`
- Test: `tests/test_context.py`

#### Step 1: NodeDescriptor + NodeStrategy + NodeResult

```python
# backend/graph/descriptor.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import BaseModel

@dataclass
class NodeDescriptor:
    name: str
    display_name: str
    fn: Any  # Callable[[NodeContext], Awaitable[None]]

    requires: list[str | list[str]] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    input_types: list[str] = field(default_factory=lambda: ["text", "drawing", "organic"])
    config_model: type[BaseModel] | None = None
    strategies: dict[str, type[NodeStrategy]] = field(default_factory=dict)
    default_strategy: str | None = None

    is_entry: bool = False
    is_terminal: bool = False  # ← 审查修复：finalize 标记为 terminal
    supports_hitl: bool = False
    non_fatal: bool = False

    description: str = ""
    estimated_duration: str = ""

@dataclass
class NodeResult:
    assets_produced: list[str] = field(default_factory=list)
    data_produced: list[str] = field(default_factory=list)
    reasoning: dict[str, Any] = field(default_factory=dict)

class NodeStrategy(ABC):
    @abstractmethod
    async def execute(self, ctx: Any) -> Any: ...
    def check_available(self) -> bool:
        return True
```

#### Step 2: BaseNodeConfig

```python
# backend/graph/configs/base.py
from pydantic import BaseModel

class BaseNodeConfig(BaseModel):
    enabled: bool = True
    strategy: str = "default"
```

#### Step 3: PipelineState（含自定义 reducer）

```python
# backend/graph/pipeline_state.py
# 审查修复：assets 和 data 使用 dict merge reducer，不覆盖
from __future__ import annotations
import operator
from typing import Annotated, Any, TypedDict

def _merge_dicts(existing: dict, update: dict) -> dict:
    """Custom reducer: merge dicts instead of overwrite."""
    return {**existing, **update}

class PipelineState(TypedDict, total=False):
    job_id: str
    input_type: str
    assets: Annotated[dict[str, dict[str, Any]], _merge_dicts]  # ← 自定义 reducer
    data: Annotated[dict[str, Any], _merge_dicts]               # ← 自定义 reducer
    pipeline_config: dict[str, dict[str, Any]]
    status: str
    error: str | None
    failure_reason: str | None
    node_trace: Annotated[list[dict[str, Any]], operator.add]
```

#### Step 4: AssetRegistry + NodeContext（含 dispatch + get_strategy）

```python
# backend/graph/context.py
# 审查修复：补全 dispatch, dispatch_progress, get_strategy 方法
# 审查修复：to_state_diff 返回增量，不返回全量
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from backend.graph.configs.base import BaseNodeConfig
from backend.graph.descriptor import NodeDescriptor, NodeStrategy

@dataclass
class AssetEntry:
    key: str
    path: str
    format: str
    producer: str
    metadata: dict[str, Any] = field(default_factory=dict)

class AssetRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, AssetEntry] = {}
    def put(self, key, path, format, producer, metadata=None):
        self._entries[key] = AssetEntry(key=key, path=path, format=format,
                                         producer=producer, metadata=metadata or {})
    def get(self, key) -> AssetEntry:
        if key not in self._entries: raise KeyError(f"Asset not found: {key}")
        return self._entries[key]
    def has(self, key) -> bool: return key in self._entries
    def keys(self) -> list[str]: return list(self._entries.keys())
    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {k: e.__dict__ for k, e in self._entries.items()}
    @classmethod
    def from_dict(cls, d):
        reg = cls()
        for k, v in d.items():
            reg._entries[k] = AssetEntry(**v)
        return reg

class NodeContext:
    def __init__(self, job_id, input_type, assets, data, config, descriptor, node_name):
        self.job_id = job_id
        self.input_type = input_type
        self._assets = assets
        self._data = data
        self.config = config
        self.descriptor = descriptor
        self.node_name = node_name
        self._new_assets: dict[str, dict[str, Any]] = {}
        self._new_data: dict[str, Any] = {}
        self._trace_entries: list[dict[str, Any]] = []

    @classmethod
    def from_state(cls, state, desc):
        import copy
        assets = AssetRegistry.from_dict(state.get("assets", {}))
        data = copy.deepcopy(state.get("data", {}))  # 审查修复：深拷贝防止共享引用
        node_configs = state.get("pipeline_config", {})
        raw_config = node_configs.get(desc.name, {})
        config_cls = desc.config_model or BaseNodeConfig
        config = config_cls(**raw_config) if raw_config else config_cls()
        return cls(
            job_id=state.get("job_id", ""),
            input_type=state.get("input_type", ""),
            assets=assets, data=data, config=config,
            descriptor=desc, node_name=desc.name,
        )

    def get_asset(self, key) -> AssetEntry: return self._assets.get(key)
    def put_asset(self, key, path, format, metadata=None):
        self._assets.put(key, path, format, self.node_name, metadata)
        self._new_assets[key] = self._assets.get(key).__dict__
    def has_asset(self, key) -> bool: return self._assets.has(key)
    def get_data(self, key): return self._data.get(key)
    def put_data(self, key, value):
        self._data[key] = value
        self._new_data[key] = value

    def get_strategy(self) -> NodeStrategy:
        """审查修复：实例化当前配置选中的策略。"""
        strategy_name = self.config.strategy
        strategies = self.descriptor.strategies
        if strategy_name not in strategies:
            raise ValueError(f"Strategy '{strategy_name}' not found for {self.node_name}. "
                           f"Available: {list(strategies.keys())}")
        cls = strategies[strategy_name]
        instance = cls()
        if not instance.check_available():
            raise RuntimeError(f"Strategy '{strategy_name}' is not available "
                             f"(runtime dependency missing)")
        return instance

    async def dispatch(self, event_type, payload):
        """审查修复：节点内事件分发代理。"""
        try:
            from langchain_core.callbacks import adispatch_custom_event
            await adispatch_custom_event(event_type, {"job_id": self.job_id, **payload})
        except RuntimeError:
            pass

    async def dispatch_progress(self, current, total, message=""):
        await self.dispatch("job.progress", {
            "node": self.node_name, "current": current, "total": total, "message": message
        })

    def to_state_diff(self):
        """审查修复：只返回增量，配合自定义 reducer。"""
        diff: dict[str, Any] = {}
        if self._new_assets:
            diff["assets"] = self._new_assets  # ← 增量，不是全量
        if self._new_data:
            diff["data"] = self._new_data      # ← 增量，不是全量
        diff["node_trace"] = self._trace_entries
        return diff

    def add_trace(self, entry): self._trace_entries.append(entry)
```

#### Step 5: 编写单元测试并验证

Run: `uv run pytest tests/test_descriptor.py tests/test_context.py -v`

#### Step 6: Commit

```bash
git commit -m "feat(graph): add core data models — NodeDescriptor, AssetRegistry, NodeContext, PipelineState

Includes dict merge reducer for assets/data (review fix #4).
Includes dispatch(), get_strategy() methods (review fix #6)."
```

---

### Task 0.2: NodeRegistry + @register_node + discovery

**Files:**
- Create: `backend/graph/registry.py`
- Create: `backend/graph/discovery.py`
- Test: `tests/test_registry.py`

关键修复：
- `discover_nodes()` 幂等保护（审查修复 #7）
- `register()` 相同 name + 相同 fn 时幂等跳过（防止模块重复导入）

```python
# backend/graph/discovery.py
_discovered = False

def discover_nodes() -> None:
    global _discovered
    if _discovered:
        return  # 审查修复 #7：幂等
    _discovered = True
    # ... import all modules under backend/graph/nodes/
```

Run: `uv run pytest tests/test_registry.py -v`

Commit: `feat(graph): add NodeRegistry, @register_node, discover_nodes (idempotent)`

---

### Task 0.3: DependencyResolver

**Files:**
- Create: `backend/graph/resolver.py`
- Test: `tests/test_resolver.py`

关键修复：
- `is_terminal` 节点自动连接到所有叶节点之后（审查修复 #2）
- OR 依赖连接到**所有**可用 producer（不是 "取第一个"）
- 增加 input_type+OR 交叉场景测试

```python
# backend/graph/resolver.py — 关键变化
# is_terminal 处理
terminal_nodes = [d for d in candidates.values() if d.is_terminal]
non_terminal_leaves = set()  # 没有后继且不是 terminal 的节点
for d in candidates.values():
    if d.name not in all_sources and not d.is_terminal:
        non_terminal_leaves.add(d.name)
# 所有非 terminal 叶节点 → terminal 节点
for leaf in non_terminal_leaves:
    for term in terminal_nodes:
        adjacency[leaf].append(term.name)
        in_degree[term.name] += 1
        edges.append((leaf, term.name))
```

Run: `uv run pytest tests/test_resolver.py -v`

Commit: `feat(graph): add DependencyResolver with is_terminal, OR multi-producer edges`

---

### Task 0.4: 特征测试（锁定当前行为）

**Files:**
- Create: `tests/test_characterization.py`

**审查修复 #11（Codex P1）：** 在改动任何现有代码之前，先写测试锁定当前 SSE 事件序列、HITL resume 行为、DB 持久化格式、API 响应 schema。

```python
# tests/test_characterization.py
"""Characterization tests — lock down current behavior before refactoring."""

class TestSSEEventSequence:
    """Verify SSE event names and payloads match current contract."""
    # node.started, node.completed, node.failed 的 payload 结构
    # job.created, job.intent_analyzed 等业务事件

class TestHTILResumeContract:
    """Verify confirm endpoint resume_data format."""
    # confirmed_params, confirmed_spec, disclaimer_accepted 作为顶层字段

class TestFinalizePersistence:
    """Verify finalize_node writes to DB with STATE_TO_ORM_MAPPING."""
    # step_path, model_url, printability → result JSON

class TestAPIResponseSchema:
    """Verify GET /jobs/{id} response shape."""
    # 关键字段存在性和类型
```

Run: `uv run pytest tests/test_characterization.py -v`

Commit: `test: add characterization tests for SSE, HITL, DB, API contracts`

---

### Task 0.5: PipelineBuilder（builder_new.py）

**Files:**
- Create: `backend/graph/builder_new.py`
- Test: `tests/test_builder_new.py`

关键修复：
- **审查修复 #3：** 写到 `builder_new.py`，不替换现有 `builder.py`
- **审查修复 #1：** 编译时注册全部节点 + 条件边（`add_conditional_edges` for input_type routing）
- **审查修复 #8：** `_wrap_node` 统一处理事件分发，迁移后的节点不再使用 `@timed_node`
- 添加 checkpoint round-trip 集成测试

```python
# backend/graph/builder_new.py
class PipelineBuilder:
    def build(self, resolved: ResolvedPipeline) -> StateGraph:
        workflow = StateGraph(PipelineState)
        # 注册所有节点
        for desc in resolved.ordered_nodes:
            workflow.add_node(desc.name, self._wrap_node(desc))
        # Entry → conditional edge by input_type
        entry_nodes = [d for d in resolved.ordered_nodes if d.is_entry]
        if entry_nodes:
            workflow.add_edge(START, entry_nodes[0].name)
        # 条件边：create_job 后按 input_type 路由
        # ... 使用 add_conditional_edges
        # Terminal nodes → END
        for d in resolved.ordered_nodes:
            if d.is_terminal:
                workflow.add_edge(d.name, END)
        return workflow

    def _wrap_node(self, desc):
        """统一包装：NodeContext 桥接 + 事件分发 + 计时。"""
        async def wrapped(state):
            ctx = NodeContext.from_state(state, desc)
            t0 = time.time()
            await _safe_dispatch("node.started", {...})
            try:
                await desc.fn(ctx)
                elapsed_ms = round((time.time() - t0) * 1000)
                diff = ctx.to_state_diff()
                diff["node_trace"] = [{"node": desc.name, "elapsed_ms": elapsed_ms, ...}]
                await _safe_dispatch("node.completed", {...})
                return diff
            except Exception as exc:
                if desc.non_fatal: ...
                raise
        return wrapped

# 公共入口（审查修复 #1）
async def get_compiled_graph_new(pipeline_config=None):
    """编译时注册全部节点，不按 input_type 过滤。
    条件边在运行时按 state['input_type'] 路由。"""
    discover_nodes()
    all_enabled = _get_all_enabled(registry, pipeline_config or {})
    # 注意：不传 input_type，全部注册
    resolved = DependencyResolver.resolve_all(registry, all_enabled)
    builder = PipelineBuilder()
    graph = builder.build(resolved)
    checkpointer = await _get_checkpointer()
    return graph.compile(checkpointer=checkpointer, interrupt_before=resolved.interrupt_before)
```

Run: `uv run pytest tests/test_builder_new.py -v`

Commit: `feat(graph): add PipelineBuilder in builder_new.py (USE_NEW_BUILDER flag OFF by default)`

---

## Phase 1: 并行模块实现

**前提：** Phase 0 全部完成，所有共享接口（descriptor, context, registry, resolver, builder_new）已稳定。

### Agent A: 前半程节点迁移

**Scope:** `backend/graph/nodes/lifecycle.py`, `analysis.py`, `generation.py`, `organic.py` + 相关测试

**修改文件（独占）：**
- `backend/graph/nodes/lifecycle.py` — create_job, confirm_with_user
- `backend/graph/nodes/analysis.py` — analyze_intent, analyze_vision, analyze_organic
- `backend/graph/nodes/generation.py` — generate_step_text, generate_step_drawing
- `backend/graph/nodes/organic.py` — generate_organic_mesh (保留，不拆)
- `tests/test_graph_nodes_lifecycle.py`
- `tests/test_graph_nodes_analysis.py`（新建）
- `tests/test_graph_nodes_generation.py`
- `tests/test_graph_nodes_organic.py`（新建）

**只读引用（不修改）：**
- `backend/graph/descriptor.py`
- `backend/graph/registry.py`
- `backend/graph/context.py`

**迁移模式（每个节点统一执行）：**

1. 添加 `@register_node(...)` 装饰器
2. 函数签名从 `(state: CadJobState) -> dict` 改为 `(ctx: NodeContext) -> None`
3. `state.get("xxx")` → `ctx.get_data("xxx")` / `ctx.get_asset("xxx")`
4. `return {"xxx": val}` → `ctx.put_data("xxx", val)` / `ctx.put_asset(...)`
5. `_safe_dispatch(...)` → `ctx.dispatch(...)`
6. **移除** `@timed_node` 装饰器（审查修复 #8）
7. 保留旧函数的逻辑不变（DB 写入、LLM 调用、错误处理）
8. 每迁移一个节点 → 运行该节点的单元测试

**节点注册清单：**

```python
# lifecycle.py
@register_node(name="create_job", display_name="创建任务",
    is_entry=True, produces=["job_info"])
@register_node(name="confirm_with_user", display_name="用户确认",
    supports_hitl=True,
    requires=[["intent_spec", "drawing_spec", "organic_spec"]],
    produces=["confirmed_params"])

# analysis.py
@register_node(name="analyze_intent", display_name="分析用户意图",
    requires=["text_input"], produces=["intent_spec"], input_types=["text"],
    strategies={"default": DefaultIntentStrategy, "two_pass": TwoPassStrategy})
@register_node(name="analyze_vision", display_name="图纸分析",
    requires=["drawing_input"], produces=["drawing_spec"], input_types=["drawing"])
@register_node(name="analyze_organic", display_name="有机分析",
    requires=["organic_input"], produces=["organic_spec"], input_types=["organic"])

# generation.py
@register_node(name="generate_step_text", display_name="文本→STEP生成",
    requires=["confirmed_params"], produces=["step_model"], input_types=["text"],
    strategies={"template_first": TemplateFirstStrategy, "llm_only": LLMOnlyStrategy})
@register_node(name="generate_step_drawing", display_name="图纸→STEP生成",
    requires=["confirmed_params"], produces=["step_model"], input_types=["drawing"])

# organic.py
@register_node(name="generate_organic_mesh", display_name="有机网格生成",
    requires=["confirmed_params"], produces=["raw_mesh"], input_types=["organic"],
    strategies={"tripo3d": Tripo3DStrategy, "hunyuan3d": Hunyuan3DStrategy, "auto": AutoStrategy})
```

Run: `uv run pytest tests/test_graph_nodes_*.py -v`

Commit: `feat(graph): migrate front-half nodes (8 nodes) to @register_node + NodeContext`

---

### Agent B: 后半程节点迁移 + organic split

**Scope:** `backend/graph/nodes/postprocess.py`, `dfam.py` + 4 个新文件

**修改文件（独占）：**
- `backend/graph/nodes/postprocess.py` — convert_preview, check_printability
- `backend/graph/nodes/dfam.py` — analyze_dfam
- `backend/graph/nodes/mesh_repair.py` (新建)
- `backend/graph/nodes/mesh_scale.py` (新建)
- `backend/graph/nodes/boolean_cuts.py` (新建)
- `backend/graph/nodes/export_formats.py` (新建)
- `backend/graph/nodes/lifecycle.py:finalize_node` — **仅 finalize 函数**（与 Agent A 不冲突，Agent A 改 create_job + confirm）
- `tests/test_mesh_pipeline.py` (新建)
- `tests/test_graph_nodes_postprocess.py`（新建）

**节点注册清单：**

```python
# postprocess.py
@register_node(name="convert_preview", display_name="生成3D预览",
    requires=[["step_model"]], produces=["preview_glb"], non_fatal=True,
    input_types=["text", "drawing"])
@register_node(name="check_printability", display_name="可打印性检查",
    requires=[["step_model", "watertight_mesh"]], produces=["printability_report"])
# dfam.py
@register_node(name="analyze_dfam", display_name="DfAM分析",
    requires=[["step_model", "watertight_mesh"]], produces=["dfam_glb", "dfam_stats"],
    non_fatal=True)
# mesh_repair.py
@register_node(name="mesh_repair", display_name="网格修复",
    requires=["raw_mesh"], produces=["watertight_mesh"], input_types=["organic"],
    strategies={"pymeshlab": PymeshlabStrategy, "trimesh_voxel": TrimeshVoxelStrategy})
# mesh_scale.py
@register_node(name="mesh_scale", display_name="网格缩放",
    requires=["watertight_mesh"], produces=["scaled_mesh"], input_types=["organic"])
# boolean_cuts.py
@register_node(name="boolean_cuts", display_name="布尔运算",
    requires=["scaled_mesh"], produces=["final_mesh"], input_types=["organic"],
    strategies={"manifold3d": Manifold3DStrategy})
# export_formats.py
@register_node(name="export_formats", display_name="导出格式",
    requires=[["final_mesh", "scaled_mesh", "watertight_mesh"]],
    produces=["export_bundle"], input_types=["organic"])
# lifecycle.py — finalize
@register_node(name="finalize", display_name="完成",
    is_terminal=True,  # ← 审查修复 #2
    produces=[])
```

**organic split 提取策略：**
从现有 `postprocess_organic_node`（350 行）按逻辑步骤拆分：
- Load + Repair → `mesh_repair_node`
- Scale → `mesh_scale_node`
- Boolean → `boolean_cuts_node`
- Export GLB/STL/3MF → `export_formats_node`
- Validate + Printability → 已有 `check_printability_node`

Run: `uv run pytest tests/test_mesh_pipeline.py tests/test_graph_nodes_postprocess.py -v`

Commit: `feat(graph): migrate back-half nodes + split postprocess_organic into 4 nodes`

---

### Agent C: 预设 + API + 兼容层

**Scope:** `backend/graph/presets.py`, `backend/graph/compat.py`, `backend/api/v1/pipeline_config.py`, `backend/api/v1/jobs.py`

**修改文件（独占）：**
- `backend/graph/presets.py` (新建)
- `backend/graph/compat.py` (新建)
- `backend/api/v1/pipeline_config.py` — 扩展现有路由（审查修复 #9）
- `backend/api/v1/jobs.py` — initial_state 格式 + confirm resume（审查修复 #5）
- `tests/test_presets.py` (新建)
- `tests/test_pipeline_api.py` (新建)

**API 扩展策略（审查修复 #9）：**
在现有 `pipeline_config.py` 中添加新端点，不创建新路由文件：

```python
# backend/api/v1/pipeline_config.py — 追加
@router.get("/nodes")
async def list_pipeline_nodes(): ...

@router.post("/validate")
async def validate_pipeline_config(req: ValidateRequest): ...

# 现有 /presets 端点保持兼容，新增字段
@router.get("/presets")
async def get_pipeline_presets():
    # 返回旧格式 + 新格式的合并响应
    ...
```

**jobs.py 改造（审查修复 #5）：**

```python
# initial_state 双格式：根据 USE_NEW_BUILDER 选择
if os.environ.get("USE_NEW_BUILDER") == "1":
    initial_state = {
        "job_id": job_id,
        "input_type": input_type,
        "assets": {},
        "data": {"text_input": text, "image_path": image_path, ...},
        "pipeline_config": pipeline_config,
        "status": "created",
        "node_trace": [],
    }
else:
    initial_state = {... current format ...}

# confirm resume 改造
if os.environ.get("USE_NEW_BUILDER") == "1":
    resume_data = {
        "data": {
            "confirmed_params": body.confirmed_params,
            "confirmed_spec": body.confirmed_spec,
        }
    }
else:
    resume_data = {... current format ...}
```

Run: `uv run pytest tests/test_presets.py tests/test_pipeline_api.py -v`

Commit: `feat(api): add pipeline nodes/validate endpoints + jobs compat layer`

---

## Phase 2: 集成验证（串行，team-lead）

### Task N.1: 合并 + 开关切换

1. 合并 Agent A / B / C 的产出
2. 确认无文件冲突
3. 修改 `backend/graph/__init__.py`：

```python
# backend/graph/__init__.py
import os
if os.environ.get("USE_NEW_BUILDER") == "1":
    from backend.graph.builder_new import get_compiled_graph_new as get_compiled_graph
else:
    from backend.graph.builder import get_compiled_graph
```

4. 修改 `backend/main.py` lifespan（审查修复）：

```python
if os.environ.get("USE_NEW_BUILDER") == "1":
    from backend.graph.discovery import discover_nodes
    discover_nodes()
    from backend.graph.builder_new import get_compiled_graph_new
    app.state.cad_graph = await get_compiled_graph_new(pipeline_config)
else:
    app.state.cad_graph = await get_compiled_graph()
```

### Task N.2: 全量测试 + E2E

Run: `USE_NEW_BUILDER=1 uv run pytest tests/ -v`

E2E 验证清单（对照特征测试）：
- [ ] TEXT 路径完整执行 + SSE 事件正确
- [ ] DRAWING 路径完整执行
- [ ] ORGANIC 路径完整执行（含 mesh 拆分）
- [ ] HITL confirm/resume 正常工作
- [ ] DB 持久化格式正确
- [ ] 旧格式 pipeline_config 自动转换
- [ ] `USE_NEW_BUILDER=0`（默认）仍然正常

### Task N.3: 切换默认值 + 清理

1. 设置 `USE_NEW_BUILDER` 默认为 `"1"`
2. 删除旧文件（逐个确认无引用）：

```bash
rg "from backend.graph.routing" backend/ tests/  # 确认 0 匹配
rg "from backend.graph.interceptors" backend/ tests/  # 确认 0 匹配
rg "CadJobState" backend/ tests/  # 确认 0 匹配（或仅在 compat.py 中）
```

3. 删除：`routing.py`, `interceptors.py`, `builder.py`（rename `builder_new.py` → `builder.py`）

Commit: `chore: switch to new builder by default, remove legacy files`

---

## Phase 3: 前端改造（Agent D）

**Scope:** 改造现有 PipelineDAG + PipelineConfigBar 组件（审查修复 #10）

**修改文件（独占）：**
- `frontend/src/components/PipelineDAG/topology.ts` — 从硬编码改为 API 动态获取
- `frontend/src/components/PipelineDAG/index.tsx` — 添加 enable toggle + strategy 标签
- `frontend/src/components/PipelineDAG/NodeCard.tsx` — 扩展配置模式
- `frontend/src/components/PipelineDAG/NodeInspector.tsx` — 策略选择 + 参数表单
- `frontend/src/components/PipelineConfigBar/index.tsx` — 节点级配置面板
- `frontend/src/services/api.ts` — 新增 pipeline API 调用
- `frontend/src/types/pipeline.ts` — 更新类型定义

**改造而非重建：**
现有 `PipelineDAG` 已经使用 ReactFlow 渲染节点卡片和连线。改造要点：
1. `topology.ts` 的 `ALL_NODES` 从硬编码改为从 `GET /pipeline/nodes` 动态获取
2. `NodeCard` 添加 enabled toggle（配置模式）
3. `NodeInspector` 扩展为策略选择器 + 参数表单
4. `PipelineConfigBar` 添加节点级配置面板
5. 预设选择器改造为支持新预设格式

Run: `cd frontend && npx tsc --noEmit && npm run lint`

Commit: `feat(ui): upgrade PipelineDAG to dynamic node-level configuration`

---

## G2 关卡评估

| 条件 | 值 | 满足？ |
|------|---|--------|
| 域标签数 ≥ 3 | `[backend:graph]` `[backend:api]` `[frontend]` `[test]` = 4 | ✅ |
| 可并行任务数 ≥ 2 | Agent A, B, C 三组并行 | ✅ |
| 总任务数 ≥ 5 | Phase 0 (5) + Phase 1 (9) + Phase 2 (3) + Phase 3 (3) = 20 | ✅ |
| 并行任务文件无交叉 | 见上方矩阵，零交叉 | ✅ |

**G2 决策：推荐 Agent Team**

- Phase 0: team-lead 串行执行（基础框架）
- Phase 1: 3 agents 并行（A=前半程, B=后半程, C=API）
- Phase 2: team-lead 串行集成
- Phase 3: 1 agent（前端）

---

## 完整节点目录（参考）

| Node | requires | produces | input_types | strategies | is_terminal |
|------|----------|----------|-------------|------------|-------------|
| create_job | — | job_info | all | — | |
| analyze_intent | text_input | intent_spec | text | default, two_pass, multi_vote | |
| analyze_vision | drawing_input | drawing_spec | drawing | default | |
| analyze_organic | organic_input | organic_spec | organic | default | |
| confirm_with_user | intent_spec OR drawing_spec OR organic_spec | confirmed_params | all (HITL) | — | |
| generate_step_text | confirmed_params | step_model | text | template_first, llm_only | |
| generate_step_drawing | confirmed_params | step_model | drawing | v2_pipeline, llm_direct | |
| generate_organic_mesh | confirmed_params | raw_mesh | organic | tripo3d, hunyuan3d, auto | |
| mesh_repair | raw_mesh | watertight_mesh | organic | pymeshlab, trimesh_voxel | |
| mesh_scale | watertight_mesh | scaled_mesh | organic | — | |
| boolean_cuts | scaled_mesh | final_mesh | organic | manifold3d | |
| export_formats | final_mesh OR scaled_mesh OR watertight_mesh | export_bundle | organic | — | |
| convert_preview | step_model | preview_glb | text, drawing | — | |
| check_printability | step_model OR watertight_mesh | printability_report | all | — | |
| analyze_dfam | step_model OR watertight_mesh | dfam_glb, dfam_stats | all | — | |
| finalize | — (is_terminal) | — | all | — | ✅ |
