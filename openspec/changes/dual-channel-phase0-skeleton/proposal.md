## Why

当前 LangGraph 管线节点的 `strategies` 机制只支持静态单策略选择，无法实现「算法优先、Neural fallback」的 auto 模式。后续 9 个后半段节点（mesh_healer、boolean_assemble、slice_to_gcode 等）均需要双通道（algorithm + Neural）策略支持，而基础设施尚未就绪。此外，新 builder (`builder_new.py`) 缺少拦截器支持，无法安全切换为默认 builder。

## What Changes

- **NodeDescriptor** 新增 `fallback_chain: list[str]` 字段，`@register_node` 新增对应参数
- **NodeContext.get_strategy()** 扩展：识别 `strategy: "auto"` 时按 `fallback_chain` 顺序尝试策略
- 新增 **NeuralStrategy** 基类（继承 `NodeStrategy`），内置 HTTP 健康检查逻辑
- 新增 **NeuralStrategyConfig**（继承 `BaseNodeConfig`），添加 `neural_enabled`、`neural_endpoint`、`neural_timeout` 等字段
- 新增 **AssetStore** Protocol + **LocalAssetStore** 实现，与现有 `AssetRegistry` 集成
- **builder_new.py** 补齐 `InterceptorRegistry` 支持（从 legacy builder 移植）
- **BREAKING**: `USE_NEW_BUILDER` 默认值从 `0` 改为 `1`（legacy builder 标记 deprecated）
- 新增验证用 demo 节点 `_test_dual_channel`，验证 auto fallback 端到端工作

## Capabilities

### New Capabilities

- `dual-channel-strategy`: 节点双通道策略派发机制（auto fallback + check_available 集成服务发现）
- `neural-strategy-base`: Neural 策略基类与配置模型（HTTP 健康检查、三态设计）
- `asset-store`: 资产持久化抽象层（LocalAssetStore，与 AssetRegistry 集成）

### Modified Capabilities

- `langgraph-job-orchestration`: 新 builder 成为默认，补齐拦截器支持，legacy builder 标记 deprecated

## Impact

- **核心文件**：`backend/graph/descriptor.py`、`backend/graph/registry.py`、`backend/graph/context.py`、`backend/graph/configs/base.py`、`backend/graph/builder_new.py`
- **新文件**：`backend/graph/strategies/neural.py`、`backend/graph/asset_store.py`
- **测试**：需新增策略 fallback 测试、NeuralStrategy mock 测试、拦截器迁移回归测试
- **依赖**：无新外部依赖（httpx 已在 pyproject.toml 中）
- **下游影响**：所有后续双通道节点提案（mesh_healer、boolean_assemble 等）依赖本提案完成
