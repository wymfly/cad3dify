## Context

CADPilot 使用 LangGraph 作为 Job 编排框架（`@register_node` + `CadJobState` + `StateGraph`），但核心 LLM 调用仍依赖 LangChain 的 `SequentialChain`（`LLMChain + TransformChain` 组合）。这些 Chain 隐藏在 `backend/core/` 模块中，被 `backend/pipeline/pipeline.py` 的同步函数编排，再由 LangGraph 节点通过 `asyncio.to_thread()` 调用。

当前 LLM 调用栈（以图纸路径为例）：
```
analyze_vision_node (async)
  → asyncio.to_thread(_run_analyze_vision)
    → pipeline.analyze_vision_spec() (sync)
      → DrawingAnalyzerChain().invoke() (sync SequentialChain)
        → LLMChain → VL model → TransformChain → DrawingSpec

generate_step_drawing_node (async)
  → asyncio.to_thread(_run_generate_from_spec)
    → pipeline.generate_step_from_spec() (sync, ~400 行)
      → ModelingStrategist.select() (纯规则，无 LLM)
      → CodeGeneratorChain().invoke() (sync, 可能 N 次 Best-of-N)
      → SmartRefiner.refine() (sync, ≤3 轮循环)
        → SmartCompareChain().invoke() (sync VL)
        → SmartFixChain().invoke() (sync Coder)
```

四层间接调用（async 节点 → to_thread → pipeline 函数 → SequentialChain）导致可观测性差、错误追踪困难、检查点无法在 LLM 调用粒度恢复。

## Goals / Non-Goals

**Goals:**
- 将 4 个 SequentialChain 替换为 LCEL Runnable（`prompt | llm | parser`），全部异步 `ainvoke()`
- 将 `pipeline.py` 的 `analyze_vision_spec()` 和 `generate_step_from_spec()` 编排逻辑内联到 LangGraph 节点中，消除 `asyncio.to_thread()` 中间层
- SmartRefiner 的 Compare→Fix 循环建模为 LangGraph 子图，支持 SSE 进度事件（检查点粒度为子图整体）
- Best-of-N 代码生成改为异步并发（`asyncio.gather`）
- 保持所有 LLM 调用的提示词不变（仅改调用方式，不改提示内容）

**Non-Goals:**
- 不修改 `IntentParser` 和 `OrganicSpecBuilder`（已接近原生 async 模式）
- 不修改 `ModelingStrategist`（纯规则引擎，无 LLM 调用）
- 不修改 LangGraph 节点的注册机制（`@register_node`）和状态 schema（`CadJobState`）
- 不修改 `get_model_for_role()` 模型选择机制和 `llm_config.yaml` 配置
- 不修改 `SafeExecutor`（CadQuery 沙箱执行）和几何校验逻辑
- 不引入 LangGraph Agent / Tool calling（保持确定性管道）
- 不删除 `pipeline.py` 文件本身（保留工具函数如 `_score_geometry`、`analyze_and_generate_step`）
- 不迁移 `contour_overlay`（Layer 3.5 轮廓叠加精细分析）——此功能仅在 `precise` 预设中启用，当前使用率低，留待后续子图增强时迁移
- 不修改前端 SSE 事件消费逻辑——前端正在 V3 重建中，直接使用新 SSE 格式

## Decisions

### ADR-1: LCEL Runnable 构建器放在 `backend/graph/chains/` 而非 `backend/core/`

**决策：** 在 `backend/graph/chains/` 创建独立模块，每个 Chain 对应一个 `def build_xxx_chain() -> Runnable` **同步**工厂函数。工厂函数负责组装 LCEL 管道（`prompt | llm | parser`）并返回 `Runnable` 对象，调用方通过 `await chain.ainvoke(inputs)` 异步执行。

**理由：**
- `backend/core/` 中的旧 Chain 类与 core 域逻辑（DrawingSpec、ModelingContext 等数据模型）耦合。将新的 LCEL Runnable 放在 `backend/graph/` 下，明确"LLM 调用是图编排层的职责"
- 工厂函数模式便于测试——可以 mock `get_model_for_role()` 返回值后验证 chain 结构
- 旧 `backend/core/` 文件中的辅助函数（`_parse_drawing_spec`、`_parse_code`、`_extract_comparison`、`fuse_ocr_with_spec`）保留原位，由 chain builder import 调用

**替代方案：**
- 原地重写 `backend/core/` 文件 → 拒绝：破坏 core 层只包含业务逻辑和数据模型的边界
- 放在 `backend/graph/nodes/` 同文件 → 拒绝：节点文件已较长，chain 构建逻辑会使其膨胀

**文件结构：**
```
backend/graph/chains/
├── __init__.py           # re-export build_* functions
├── vision_chain.py       # build_vision_analysis_chain()
├── code_gen_chain.py     # build_code_gen_chain()
├── compare_chain.py      # build_compare_chain(structured=False)
└── fix_chain.py          # build_fix_chain()
```

### ADR-2: SmartRefiner 循环改为 LangGraph 子图而非节点内 while 循环

**决策：** 将 Compare→Fix→Re-execute→Re-render ≤3 轮循环建模为 `StateGraph` 子图（subgraph），嵌入 `generate_step_drawing_node` 后的图拓扑中。

**理由：**
- 子图中每个节点都可派发 SSE 事件（`job.refining`），前端实时显示第几轮
- 循环退出条件（VL PASS 或达到上限）通过 conditional edge 路由，比 while 循环更可视化
- 子图复用父图的 checkpointer（通过 `RunnableConfig` 透传），但**不保证**子图内部节点粒度的独立恢复——检查点在子图出入口，而非每个内部节点

**检查点策略（降级声明）：** 子图作为 `generate_step_drawing_node` 的内嵌调用（`refiner_subgraph.ainvoke(state, config=config)`），检查点粒度为子图整体完成。如果进程在子图执行中崩溃，恢复粒度为 `generate_step_drawing_node` 级别（即从节点入口重跑）。未来可通过将子图提升为主图的一等节点来实现更细粒度的恢复。

**替代方案：**
- 节点内 while 循环 + 手动状态管理 → 拒绝：无 SSE 事件粒度，无法利用 conditional edge
- 每轮循环作为顶层独立节点 → 拒绝：污染主图拓扑，且轮数不固定
- 子图作为主图的一等节点（非内嵌调用）→ 可行但暂不实施：需要 CadJobState 增加 refiner 字段，对主图 schema 侵入性强

**子图状态：**
```python
class RefinerState(TypedDict):
    code: str                        # 当前 CadQuery 代码
    step_path: str                   # STEP 文件路径
    drawing_spec: dict               # 图纸规格（子图内部存 dict，入口处由 DrawingSpec.model_dump() 转换）
    image_path: str                  # 原始图纸路径
    round: int                       # 当前轮次
    max_rounds: int                  # 最大轮次
    verdict: str                     # "pending" | "pass" | "fail" | "max_rounds_reached"
    static_notes: list[str]          # Layer 1/2 诊断
    comparison_result: str | None    # VL 对比结果（供 coder_fix 使用，崩溃恢复后无需重新调用 VL）
    rendered_image_path: str | None  # 当前轮次渲染的 PNG 路径（确保每轮 re-render 后更新）
    prev_score: float | None         # 上一轮几何分数（用于 RollbackTracker 退化检测）
```

**子图拓扑（修正版）：**
```
static_diagnose → render_for_compare → vl_compare → route_verdict
  ├─ verdict="pass" → END
  ├─ verdict="fail" + round < max_rounds → coder_fix → re_execute → render_for_compare → vl_compare → route_verdict (循环)
  └─ verdict="fail" + round >= max_rounds → END (verdict="max_rounds_reached")
```

**状态映射函数：**
```python
def map_job_to_refiner(state: CadJobState, config: dict) -> RefinerState:
    """CadJobState → RefinerState 入口映射，显式 DrawingSpec→dict 转换"""
    spec = state["drawing_spec"]
    return RefinerState(
        code=state["generated_code"],
        step_path=state["step_path"],
        drawing_spec=spec.model_dump() if isinstance(spec, DrawingSpec) else spec,
        image_path=state["image_path"],
        round=0,
        max_rounds=config.get("max_refinements", 3),
        verdict="pending",
        static_notes=[],
        comparison_result=None,
        rendered_image_path=None,
        prev_score=None,
    )

def map_refiner_to_job(refiner_state: RefinerState) -> dict:
    """RefinerState → CadJobState 出口映射（部分字段更新）"""
    return {"generated_code": refiner_state["code"], "step_path": refiner_state["step_path"]}
```

**validator 类型安全：** 子图内 `static_diagnose` 节点在调用 `validate_code_params(code, spec)` 时，需将 `drawing_spec: dict` 还原为 `DrawingSpec` 对象：
```python
spec = DrawingSpec(**state["drawing_spec"])
result = validate_code_params(state["code"], spec)
```

### ADR-3: pipeline.py 编排函数渐进式迁移而非一次性删除

**决策：** 分两步迁移：
1. 先创建 LCEL chains + refiner 子图，节点层直接使用新 chain
2. 再删除 `pipeline.py` 中的 `analyze_vision_spec()` 和 `generate_step_from_spec()`

保留 `pipeline.py` 中的工具函数（`_score_geometry`、`analyze_and_generate_step`），因为 `analyze_and_generate_step` 被非 LangGraph 入口（CLI、测试）调用。

**理由：**
- 一次性删除风险高——pipeline.py 是 486 行的密集编排逻辑
- 渐进式迁移允许逐个验证每条 chain 的行为等价性
- `analyze_and_generate_step()` 入口函数可在未来改为调用 LangGraph 图代替，但不在本次范围

### ADR-4: Best-of-N 改为 asyncio.gather 并发而非串行

**决策：** 将 Best-of-N 循环从 `for i in range(N): generator.invoke(ctx)` 改为分两阶段：
1. **LLM 生成阶段**（并发）：`asyncio.gather(*[chain.ainvoke(ctx) for _ in range(N)])` — 纯 LLM 调用，无文件系统副作用
2. **执行+评分阶段**（串行）：对每个生成结果，在独立 tempdir 中调用 `SafeExecutor.execute()` + `_score_geometry()` — `SafeExecutor` 通过 subprocess 隔离 + `output_path` 参数指定输出位置

**理由：**
- LLM 生成阶段完全无状态，并发安全
- 执行阶段使用 `SafeExecutor`（AST 校验 + subprocess 隔离），而非 `PythonREPLTool`（无 FS 约束），确保文件系统安全
- 每个候选通过 `SafeExecutor(output_dir=tempdir)` 限制输出位置

**替代方案：**
- 全部串行 → 拒绝：N=3 时 LLM 延迟从 ~90s 降至 ~30s，收益明显
- 全部并发（含执行阶段）→ 拒绝：CadQuery subprocess 执行存在资源竞争风险
- 用 LangGraph Parallel Node → 拒绝：Best-of-N 是生成节点的内部策略，不值得暴露为图拓扑

### ADR-5: 旧 Chain 类标记为 @deprecated 保留一个版本周期后删除

**决策：** 第一步迁移完成后，旧 `DrawingAnalyzerChain`、`CodeGeneratorChain`、`SmartCompareChain`、`SmartFixChain` 标记 `@deprecated`，`analyze_and_generate_step()` 函数内部保留对旧 Chain 的调用。下一个版本周期再统一删除。

**理由：**
- `analyze_and_generate_step()` 是非 LangGraph 入口（CLI、benchmark 测试可能使用）
- 一步删除要求同时修改所有消费方，风险较高
- 标记 deprecated 后可通过 `grep` 追踪剩余使用方

### 补充决策：PipelineConfig 通过 LangGraph configurable 注入子图

**决策：** 子图和节点通过 `RunnableConfig["configurable"]` 接收 `PipelineConfig` 参数（如 `rollback_on_degrade`、`structured_feedback`、`topology_check`、`multi_view_render`），而非在 `RefinerState` 中携带配置字段。

**理由：**
- 配置是不可变的运行时参数，不属于状态流转数据
- LangGraph 的 `configurable` 机制天然支持透传到子图——`refiner_subgraph.ainvoke(state, config=config)` 中的 config 自动传递
- 避免 `RefinerState` 膨胀

**用法示例：**
```python
# 节点内获取配置
pipeline_config = config["configurable"].get("pipeline_config", PipelineConfig())
if pipeline_config.topology_check:
    compare_topology(...)
```

### 补充决策：生成节点编排逻辑抽取为 helper 函数

**决策：** `generate_step_drawing_node` 内联的编排逻辑（Stage 1.5 策略选择 → Stage 2 代码生成/Best-of-N → Stage 3 执行 → Stage 3.5 验证 → Stage 4 子图 → Stage 5 后置检查）抽取为独立的 async helper 函数 `async def _orchestrate_drawing_generation(state, config) -> dict`，放在 `backend/graph/nodes/generation.py` 同文件中。节点函数只负责状态映射、SSE dispatch 和异常处理。

**理由：**
- 避免节点函数膨胀到 300+ 行，保持与其他节点函数的一致性
- helper 函数可独立单测（传入 mock state + config，无需 LangGraph 图上下文）
- 与 ADR-1（chain 构建逻辑拆到独立文件）的设计哲学一致

### 补充决策：LLM 超时策略分层

**决策：** 超时策略按节点类型区分：
- **轻量节点**（`analyze_intent_node`、`analyze_vision_node`）：`asyncio.wait_for(timeout=60.0)` — 单次 LLM 调用
- **重量节点**（`generate_step_drawing_node`）：`asyncio.wait_for(timeout=300.0)` — 包含 Best-of-N 并发 + Refiner 子图多轮循环
- **单次 LLM 调用级超时**：每个 LCEL chain 通过 `chain.with_retry(stop_after_attempt=3)` + 内部 per-call timeout 控制，不依赖节点级超时

**理由：**
- generation 节点在 Best-of-N=3 + max_refinements=3 时可能涉及 10+ 次 LLM 调用，60s 绝对不够
- per-call timeout + 节点级 timeout 双层保护：单次 LLM 调用卡死时 per-call timeout 先触发，全流程超时时节点级 timeout 兜底

## Risks / Trade-offs

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| **提示词行为不一致** — LCEL 管道与 SequentialChain 的提示词格式化可能有微妙差异 | 中 | 高 | 每个 chain 迁移后运行 prompt 等价性测试（相同输入→相同 prompt text） |
| **子图状态映射错误** — Refiner 子图与主图的状态字段映射不正确 | 中 | 高 | 子图使用独立 TypedDict + 显式映射函数 + `DrawingSpec` dict↔model 显式转换 |
| **`prep_inputs()` 适配丢失** — 旧 Chain 的输入预处理逻辑在 LCEL 迁移中被遗忘 | 中 | 高 | 节点层在调用 `chain.ainvoke()` 前显式执行 `ImageData` → flat dict 转换，chain spec 文档化输入格式 |
| **并发 Best-of-N 资源竞争** — 多个 CadQuery 执行同时写文件 | 低 | 中 | LLM 并发 + 执行串行分离，`SafeExecutor` subprocess 隔离 |
| **测试回归** — 大量测试 mock 需要从 `.invoke()` 改为 `.ainvoke()` | 高 | 中 | 先创建测试工具函数（mock LCEL chain factory），再批量迁移 |
| **pipeline.py 残留调用** — 迁移不彻底导致新旧混用 | 低 | 低 | 迁移完成后 grep 验证无 `pipeline.analyze_vision_spec` / `pipeline.generate_step_from_spec` 调用 |
| **contour_overlay 功能回归** — precise 预设丢失 Layer 3.5 | 低 | 低 | 标注为 Non-Goals，保留旧 SmartRefiner 代码可被 `analyze_and_generate_step()` 继续调用 |
