## ADDED Requirements

### Requirement: SchemaForm anyOf 类型解析

`SchemaForm` SHALL 能正确渲染 Pydantic v2 生成的 `anyOf` 类型字段（如 `str | None` → `{"anyOf": [{"type": "string"}, {"type": "null"}]}`）。

SchemaForm SHALL 实现类型解析逻辑：从 `anyOf` 数组中提取非 `null` 的基础类型，用于控件分发。

#### Scenario: 可选 string 字段渲染为 Input
- **WHEN** schema property 为 `{"anyOf": [{"type": "string"}, {"type": "null"}], "default": null}`
- **THEN** SchemaForm 渲染为 Input 控件（而非 "未设置" 占位文本）

#### Scenario: 可选 integer 字段渲染为 InputNumber
- **WHEN** schema property 为 `{"anyOf": [{"type": "integer"}, {"type": "null"}], "default": null}`
- **THEN** SchemaForm 渲染为 InputNumber 控件

### Requirement: SchemaForm scope 过滤

`SchemaForm` 组件 SHALL 新增 `scope` prop（`"engineering"` | `"system"` | `"all"`，默认 `"engineering"`）。

过滤规则：
- `scope="engineering"` → 只渲染 `x-scope` 不存在或为 `"engineering"` 的字段
- `scope="system"` → 只渲染 `x-scope === "system"` 的字段
- `scope="all"` → 渲染所有字段

管道配置面板中的 SchemaForm 调用 SHALL 传入 `scope="engineering"`。

#### Scenario: 管道配置面板隐藏系统参数
- **WHEN** 用户在管道配置面板展开节点（如 generate_raw_mesh）
- **THEN** 不显示 API key、endpoint 等 system scope 字段
- **AND** 显示 timeout、output_format 等 engineering 字段

#### Scenario: system scope 只渲染系统字段
- **WHEN** SchemaForm 传入 `scope="system"` 和含有 system/engineering 混合字段的 schema
- **THEN** 只渲染 `x-scope: "system"` 的字段

#### Scenario: 无 system 字段时不渲染
- **WHEN** 节点的 config_schema 中所有字段都是 engineering scope
- **AND** SchemaForm 传入 `scope="system"`
- **THEN** 组件返回 null（不渲染任何内容）

### Requirement: Settings 页系统配置面板

Settings 页 SHALL 新增"系统配置"tab，展示所有节点的 system scope 参数。

面板结构：
- 调用 `GET /pipeline/system-config-schema` 获取 schema
- 每个有 system 字段的节点渲染为可折叠面板
- 面板内部复用 `SchemaForm`（`scope="system"`）
- 提供"保存"和"重置"按钮

保存操作 SHALL 调用 `PUT /pipeline/system-config`。
重置操作 SHALL 清空当前修改，恢复为上次保存的值。

#### Scenario: 系统配置 tab 可见
- **WHEN** 用户进入 Settings 页
- **THEN** 可以看到"系统配置"tab 选项

#### Scenario: 节点分组展示
- **WHEN** 用户切换到"系统配置"tab
- **THEN** 每个有 system 字段的节点显示为可折叠面板（如 "Generate Raw Mesh"、"Mesh Healer"）
- **AND** 无 system 字段的节点不出现在列表中

#### Scenario: 保存系统配置
- **WHEN** 用户修改系统参数并点击"保存"
- **THEN** 调用 API 保存配置，显示成功提示

#### Scenario: 保存后刷新值持久
- **WHEN** 用户保存系统配置后刷新页面
- **THEN** 系统配置面板显示之前保存的值

### Requirement: 前端 API 服务函数

`services/api.ts` SHALL 新增 3 个函数：

1. `getSystemConfigSchema()` → `GET /api/v1/pipeline/system-config-schema`
2. `getSystemConfig()` → `GET /api/v1/pipeline/system-config`
3. `updateSystemConfig(data)` → `PUT /api/v1/pipeline/system-config`

#### Scenario: API 函数可用
- **WHEN** 前端组件调用 `getSystemConfigSchema()`
- **THEN** 返回后端系统配置 schema 数据

#### Scenario: 更新 API 函数可用
- **WHEN** 前端组件调用 `updateSystemConfig({generate_raw_mesh: {hunyuan3d_api_key: "sk-..."}})`
- **THEN** 配置发送到后端并保存成功
