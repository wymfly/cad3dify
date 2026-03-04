## Why

后端 LangGraph 管道已具备完整的节点注册（registry）、配置 Schema（config_schema）、策略选择（strategies）和 fallback chain 能力，但前端 CustomPanel 仅覆盖 enabled/strategy 两个字段，导致大量节点参数无法通过 UI 配置。同时，节点启用/禁用当前在编译时过滤，无法在 HITL 中断时调整后续节点配置。需要一次性补全前后端配置能力，实现编译层/解析层/执行层的完整配置矩阵。

## What Changes

- 将节点 enabled/disabled 从编译时过滤改为运行时跳过（`_wrap_node()` 中检查 state）
- 新增 `GET /api/v1/pipeline/strategy-availability` 端点，返回每个策略的可用性状态
- 增强 `config_schema` 生成：从 Pydantic Field metadata 提取 description/min/max/x-group/x-sensitive
- 扩展 `POST /api/v1/jobs/{id}/confirm` 端点，支持 `pipeline_config_updates` 字段用于 HITL 中调参
- 新增前端 `SchemaForm` 组件：根据 JSON Schema 动态渲染表单控件
- 新增前端 `ValidationBanner` 组件：实时调用 validate API 展示配置有效性
- 重构 `NodeConfigCard`：集成 SchemaForm + 策略可用性灰化 + fallback chain 展示
- 扩展 HITL ConfirmDialog：支持修改后续未执行节点的配置
- 旧 API（`/pipeline/presets`、`/pipeline/tooltips`）添加 Deprecated header

## Capabilities

### New Capabilities

- `runtime-node-skip`: 运行时节点跳过机制，替代编译时过滤，支持 HITL 中动态调整
- `strategy-availability`: 策略可用性检测 API，查询每个策略的运行时依赖状态
- `schema-driven-config-ui`: Schema 驱动的前端配置表单引擎，根据 config_schema 自动渲染控件
- `hitl-config-adjustment`: HITL 中断时修改后续节点配置的能力

### Modified Capabilities

- `hitl-confirmation`: confirm 端点扩展 pipeline_config_updates 字段

## Impact

- **后端**: `builder.py`（运行时跳过）、`registry.py`（schema 增强）、`api/v1/jobs.py`（confirm 扩展）、新增 `api/v1/pipeline_config.py` 端点
- **前端**: 新增 `SchemaForm/`、`ValidationBanner.tsx` 组件，重构 `CustomPanel.tsx`、`NodeConfigCard`，扩展 `ConfirmDialog`
- **API 契约**: 新增 1 个端点，修改 1 个端点 body schema，2 个端点标记 deprecated
- **测试**: 后端单元测试 5 个，前端组件测试 5 个，E2E 场景 5 个
