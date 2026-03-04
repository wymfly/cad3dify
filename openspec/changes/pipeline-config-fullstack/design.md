## Context

CADPilot 使用 LangGraph 双管道架构（precision + organic），通过 `@register_node` + `DependencyResolver` 实现节点自动发现和编排。后端已具备完整的 config_schema（Pydantic → JSON Schema）、策略注册（strategies）、fallback chain 等能力，但前端 CustomPanel 仅渲染 enabled/strategy 两个字段，大量配置能力被浪费。

当前节点 enabled/disabled 在编译时过滤（`resolver.py` 的 `resolve_all()`），导致配置不可在 HITL 中断时动态调整。

详细设计见 brainstorming 产出：[`docs/plans/2026-03-04-pipeline-config-fullstack-design.md`](../../docs/plans/2026-03-04-pipeline-config-fullstack-design.md)

## Goals / Non-Goals

**Goals:**
- 整理编译层/解析层/执行层的完整能力矩阵
- 实现运行时节点跳过机制，替代编译时过滤
- 新增策略可用性检测 API
- Schema 驱动的前端配置表单引擎，后端加参数前端自动呈现
- HITL 中断时支持修改后续节点配置
- 前后端配置能力完全一致
- E2E 测试覆盖所有配置场景

**Non-Goals:**
- 运行时修改 fallback chain 顺序（架构改动大，投入产出比低）
- 自定义条件路由（需要 DSL/规则引擎，超出配置范围）
- 运行中实时改配置（LangGraph state mutation 在节点执行中不安全）
- 拖拽编排节点顺序（拓扑由 requires/produces 决定，手动排序无意义）
- 用户自定义预设保存（可后续加，MVP 不需要）

## Decisions

### ADR-1: 节点插拔机制 — 运行时跳过

**选择**: 运行时跳过（`_wrap_node()` 中检查 `state["pipeline_config"][node]["enabled"]`）

**替代方案**: Per-Job 编译（每个 Job 动态编译子图）

**理由**: 零编译开销，支持 HITL 中调整，改动最小。Per-Job 编译需要为每个 Job 维护独立的图实例，增加内存和性能负担。

### ADR-2: 参数 UI 模式 — Schema 驱动

**选择**: 完整 Schema 驱动（`config_schema` JSON Schema → 前端自动渲染 Ant Design 控件）

**替代方案**: 手写表单（每个节点单独写 React 组件）、混合模式

**理由**: 一劳永逸，后端加参数前端自动呈现。类型映射：boolean→Switch, integer/number→InputNumber/Slider, string+enum→Select, x-sensitive→Password。

### ADR-3: 配置时机 — Job 创建前 + HITL 中断时

**选择**: 两个配置窗口：Job 创建前完整配置 + HITL 中断时修改后续节点

**替代方案**: 仅创建前（灵活性不足）、全程可调（LangGraph state mutation 不安全）

**理由**: 平衡灵活性与复杂度。HITL 中断是天然的配置窗口，用户看到中间结果后可能需要调整后续节点参数。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|---------|
| Schema 驱动表单可能无法覆盖复杂 UI 需求（如联动字段） | 保留 `x-group` 分组 + `json_schema_extra` 扩展点，未来可按需添加自定义渲染器 |
| 运行时跳过可能导致下游节点收到不完整的 state | `POST /pipeline/validate` 在配置变更时实时校验拓扑合法性，前端展示验证结果 |
| HITL 中调参增加 confirm 端点复杂度 | `pipeline_config_updates` 为可选字段，deep-merge 逻辑简单，不影响现有调用方 |
| 旧 API deprecation 可能影响外部调用方 | 仅添加 Deprecated header，不立即删除，前端切换完成后再评估 |
