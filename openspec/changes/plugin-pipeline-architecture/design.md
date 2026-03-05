## Context

CADPilot 的 LangGraph 管线当前是手写拓扑（`builder.py` 硬编码 13 个节点 + 边），`CadJobState` 包含 25+ 个散装字段，精密路径和有机路径的后处理逻辑完全独立。Codex 审查识别出 6 个 P1 架构问题，核心是：添加新节点需改 3 处文件、`pipeline_config` 未使用、`postprocess_organic_node` 350 行巨型函数导致路径分叉。

端到端 3D 打印路线图（Gemini 节点分析）规划了 orientation_optimizer、slice_to_gcode、apply_lattice 等新节点，当前架构无法低成本支撑。

完整设计细节见 `docs/plans/2026-03-02-plugin-pipeline-architecture.md`。

## Goals / Non-Goals

**Goals:**
- 新增节点零改动 builder：一个文件 + `@register_node` 装饰器即可注册
- 声明式依赖：节点通过 requires/produces 声明 asset 依赖，系统自动推导拓扑
- 多策略支持：每个节点可配置多种实现（算法 vs AI 模型），运行时按配置选择
- 精细化配置：每个节点独立配置参数，预设覆盖 + 用户微调
- 路径归一化：精密/有机/混合路径在后处理阶段通过 OR 依赖自然共享节点
- 保留 LangGraph 基础设施：checkpoint、HITL interrupt、SSE 事件分发不变

**Non-Goals:**
- 不自研编排引擎替代 LangGraph
- 不实现节点的运行时热插拔（图在编译时确定，非运行时动态变更）
- 不在本变更中实现具体的新节点算法（orientation/slicing/lattice），只搭建架构
- 不重写前端所有页面，只新增 PipelineConfigurator 组件

## Decisions

### D1: 保留 LangGraph 作为执行引擎，用 NodeRegistry 在编译时动态生成图

**选择**: 方案 A — LangGraph + 编译时动态图生成
**替代**: 方案 B — 自研轻量编排器
**理由**: LangGraph 的 checkpoint/replay、HITL interrupt_before、AsyncSqliteSaver 已经验证稳定。自研需要重写状态持久化、中断恢复、事件分发，工作量 3-5 倍且要重写全部测试。NodeContext 作为视图层隔离节点与 LangGraph State 的耦合。

### D2: 声明式 requires/produces 依赖图，支持 AND/OR 语法

**选择**: 纯 DAG 拓扑排序（Kahn 算法）
**替代**: 显式 order 数字排序、固定阶段 + 阶段内排序
**理由**: requires/produces 是最自然的表达——节点只需声明"我需要什么、我产出什么"，系统自动推导顺序。OR 依赖（`[["step_model", "watertight_mesh"]]`）允许节点跨路径复用。显式 order 缺乏语义且容易冲突，固定阶段会限制灵活性。

### D3: 依赖不满足时报错，而非自动拉起上游节点

**选择**: 严格报错
**替代**: 自动启用依赖节点
**理由**: 自动拉起可能产生意外开销（如拉起付费 API 节点），用户应该显式控制哪些节点启用。报错信息明确告知缺少哪个节点，交互比"静默启用一堆节点"更友好。

### D4: PipelineState 用 assets dict + data dict 替代散装字段

**选择**: 两个通用字典（assets 存文件产物，data 存语义数据）
**替代**: 保留大 TypedDict 继续扩展
**理由**: CadJobState 已有 25 个字段，新增 orientation/slicing/lattice/support 会推到 35+，finalize_node 的路径分支 merge 会进一步失控。assets/data 字典让每个节点只通过 NodeContext 读写自己声明的 key，字段命名由注册元数据约束而非全局 TypedDict。

### D5: 策略作为节点配置的 strategy 字段，而非独立节点

**选择**: 策略内聚在节点内
**替代**: 每种策略注册为独立互斥节点（如 repair_pymeshlab、repair_trimesh）
**理由**: 策略共享同一个 requires/produces 契约，区别仅在实现。独立节点会导致节点数膨胀（3 种修复策略 × 2 种切片策略 = 6 个节点 vs 2 个节点），且 UI 上的互斥选择比节点开关更直观。

### D6: 全管线统一注册（前半程 + 后半程）

**选择**: 分析/生成节点也纳入 NodeRegistry
**替代**: 仅后处理节点可插拔
**理由**: 统一体系使分析节点也可切换策略（如 analyze_intent 的 default/two_pass/multi_vote），前端配置 UI 一致。前半程节点通过 `input_types` 字段自动按输入类型过滤。

## Risks / Trade-offs

- **[Risk] LangGraph State 序列化嵌套 dict** → assets/data 是嵌套字典，需验证 AsyncSqliteSaver 的 checkpoint 序列化兼容性。**Mitigation**: 所有 value 限制为 JSON-serializable 类型，写集成测试验证 checkpoint round-trip。

- **[Risk] 大规模迁移的回归风险** → 所有现有节点需改签名，测试需重写。**Mitigation**: 保留 `compat.py` 兼容层，支持旧格式 pipeline_config 自动转换；迁移按节点逐个进行，每迁移一个跑全量测试。

- **[Risk] OR 依赖的拓扑歧义** → 一个节点声明 `requires=[["a", "b"]]`，如果 a 和 b 的 producer 都存在，取哪个？**Mitigation**: 按 producer 在拓扑序中的位置取最近的；在 ResolvedPipeline.validate() 中对 OR 歧义发出 warning。

- **[Trade-off] NodeContext 视图层增加一层间接** → 每次节点调用需要 from_state + to_state_diff 的转换开销。实际开销微秒级，远小于节点本身的 IO/计算时间，可接受。

- **[Trade-off] 图在编译时确定，不支持运行时动态变更** → 同一个 job 不能中途改配置。这是 LangGraph 的设计约束，且符合管线语义（一次执行的拓扑应该是确定的）。

## Migration Plan

1. **Phase 1 — 核心框架**：实现 descriptor / registry / context / resolver / builder 骨架，用最简单的 2 个 stub 节点验证全链路
2. **Phase 2 — 节点迁移**：逐个将现有节点迁移到新体系（改签名 + @register_node），每迁移一个跑全量测试
3. **Phase 3 — postprocess_organic 拆分**：拆为 mesh_repair + mesh_scale + boolean_cuts + export_formats
4. **Phase 4 — API + 兼容层**：新增管线 API 端点，旧 pipeline_config 格式兼容
5. **Phase 5 — 前端 UI**：PipelineConfigurator 组件（DAG 编辑 + 节点面板 + 监控）
6. **Phase 6 — 清理**：删除旧 builder/routing/state/interceptors，移除兼容层

**Rollback**: Phase 1-3 期间保留旧 builder.py（重命名为 builder_legacy.py），可通过环境变量 `USE_LEGACY_BUILDER=1` 回退。

## Open Questions

- LangGraph 的 `add_conditional_edges` 是否支持从 ResolvedPipeline 动态生成任意拓扑？需要在 Phase 1 的 spike 中验证。
- `mesh_scale` 和 `boolean_cuts` 拆分后，`watertight_mesh` asset 被原地更新（同 key 覆盖）——这在 LangGraph 的 checkpoint 中是否有 race condition 风险？
