## Why

管道配置 UI 当前将 config_schema 中的所有字段混在一起渲染——API key、endpoint URL、CLI 路径等系统级参数和 layer_height、voxel_resolution 等工程参数出现在同一个面板中。这导致两个问题：

1. **用户体验差**：普通用户调整打印参数时被 API key 等运维配置干扰
2. **扩展性差**：每新增节点或工具，前端需要手动识别哪些参数该展示、哪些该隐藏

需要一套纯 schema-driven 的参数分层架构：后端 Pydantic model 声明字段 scope，前端自动按 scope 过滤渲染，新增节点/参数时零前端改动。

## What Changes

- 后端 Pydantic config model 新增 `x-scope` JSON Schema 扩展标记（`"system"` | `"engineering"`），沿用已有的 `x-sensitive` / `x-group` 模式
- `enhance_config_schema()` 新增自动推断安全网：`_endpoint`、`_path` 后缀及 `x-sensitive` 字段自动标记为 system scope
- 新增 `SystemConfigStore`：系统参数独立持久化到 JSON 文件，与 per-request 管道配置解耦
- 新增 3 个 REST API：系统配置 schema 查询、读取、保存
- `NodeContext.from_state()` 运行时合并系统配置（优先级：Pydantic default < system_config.json < per-request pipeline_config）
- 前端 `SchemaForm` 新增 `scope` prop，按 `x-scope` 过滤字段
- Settings 页新增"系统配置"面板，复用 SchemaForm 渲染 system scope 字段

## Capabilities

### New Capabilities

- `schema-scope-convention`: x-scope JSON Schema 扩展标记约定 + enhance_config_schema 自动推断安全网。定义 system/engineering 两层分类规则，作为所有节点配置字段的元数据标准。
- `system-config-persistence`: 系统级配置独立持久化层。SystemConfigStore + 3 个 REST API + NodeContext 运行时合并。
- `system-config-ui`: Settings 页系统配置面板。基于 config_schema x-scope 过滤，自动渲染 system scope 字段表单。

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

**后端（4 config model + 3 基础设施文件）：**
- `backend/graph/configs/` 下 4 个 config model 添加 x-scope 标记（generate_raw_mesh、neural、mesh_healer、slice_to_gcode）
- `backend/graph/registry.py` — enhance_config_schema 扩展
- `backend/graph/system_config.py` — 新增
- `backend/graph/context.py` — 合并逻辑
- `backend/api/v1/pipeline_config.py` — 3 个新端点

**前端（5 文件）：**
- `SchemaForm/index.tsx` — scope 过滤
- `PipelineConfigBar/CustomPanel.tsx` — 传入 scope prop
- `Settings/SystemConfigPanel.tsx` — 新增
- `Settings/index.tsx` — 新增 tab
- `services/api.ts` — 3 个新 API 函数

**API 新增：**
- `GET /api/v1/pipeline/system-config-schema`
- `GET /api/v1/pipeline/system-config`
- `PUT /api/v1/pipeline/system-config`

**不影响：** 现有管道执行逻辑、现有 per-request pipeline_config API、现有前端管道配置交互流程。
