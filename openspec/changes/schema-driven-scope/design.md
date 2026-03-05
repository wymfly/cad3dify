## Context

CADPilot 的 LangGraph 管道使用 `@register_node` + Pydantic config model 架构，每个节点声明 `config_model`，由 `enhance_config_schema()` 自动生成 JSON Schema 供前端渲染。当前已有 `x-sensitive`（密码输入）和 `x-group`（分组）两个 JSON Schema 扩展。

前端 `SchemaForm` 组件根据 config_schema 自动渲染表单控件（Switch/Slider/Input/Select/Password），已跳过 `enabled` 和 `strategy` 字段。但所有其余字段——包括 API key、endpoint URL、CLI 路径——都出现在管道配置面板中，与工程参数混杂。

系统参数（API key、endpoint、CLI path、neural_enabled）需要独立管理：不随每次作业变化，由管理员一次性配置，跨作业共享。

## Goals / Non-Goals

**Goals:**
- 纯 schema-driven：新增节点或参数时零前端代码改动
- 管道配置面板只展示工程参数（per-job tunable）
- Settings 页自动渲染系统参数表单
- 系统参数独立持久化，运行时透明合并
- 延续 x-sensitive / x-group 已有模式，最小概念引入

**Non-Goals:**
- 用户权限/角色管理（谁能修改系统配置）
- 加密存储 API key（当前用明文 JSON，后续可升级）
- 多环境配置切换（dev/staging/prod profiles）
- 字段级依赖/联动（如 strategy=neural 时才显示 neural_endpoint）

## Decisions

### D1: x-scope 扩展标记 + 自动推断安全网

**选择：** `json_schema_extra={"x-scope": "system"}` 显式标记 + `enhance_config_schema()` 自动推断兜底

**备选方案：**
- A) 纯自动推断（不标记，全靠命名约定）— 脆弱，新字段命名不规范时会漏标
- B) 纯显式标记（每个字段必须手写 x-scope）— 冗余，大部分工程参数不需要标记
- C) 混合模式（显式优先 + 自动兜底）— 最佳平衡 ✓

**自动推断规则：**
1. 已标 `x-sensitive` → 自动 system（API key 必然是系统配置）
2. 字段名匹配 `_endpoint$` → system（部署地址）
3. 字段名匹配 `_cli_path$` 或精确匹配 `prusaslicer_path|orcaslicer_path` → system（工具 CLI 路径）
4. 字段名匹配 `^neural_enabled$` → system（开关控制工具能力）
5. 未匹配 + 未显式标注 → 不添加 x-scope（前端默认当 engineering 处理）

> **注意**：不使用宽泛的 `_path$` 匹配，避免误标未来的工程路径参数（如 `model_path`、`export_path`）。`health_check_path` 由 T1 显式标注，不依赖自动推断。

显式标注始终优先于自动推断。

### D2: 系统配置持久化层

**选择：** 独立 JSON 文件（`backend/data/system_config.json`）+ `SystemConfigStore` 单例

**备选方案：**
- A) 数据库存储 — 过重，系统配置低频写入，不需要 ACID
- B) 环境变量 / .env — 无法通过 UI 修改，不满足 Settings 页需求
- C) JSON 文件 — 简单、可读、支持 UI 修改、原子写入安全 ✓

**原子写入：** 使用 `tempfile.NamedTemporaryFile(dir=..., delete=False)` 生成唯一临时文件 → 写入 → `os.replace()` 原子重命名。避免写入中断导致文件损坏，且多线程/进程场景下临时文件名不冲突。

### D3: 配置合并优先级

**选择：** Pydantic default < system_config.json < per-request pipeline_config

这保证了：
- 开发者在 Pydantic model 中定义合理默认值
- 管理员在 Settings 页覆盖系统配置（如填入 API key）
- 单次作业可临时覆盖任何配置（灵活性不受限）

合并发生在 `NodeContext.from_state()` 中，对节点实现完全透明。

### D4: 前端 scope 过滤策略

**选择：** SchemaForm 新增 `scope` prop，过滤逻辑在组件内部

**规则：**
- `scope="engineering"`（默认）→ 只渲染 `x-scope` 不存在或为 `"engineering"` 的字段
- `scope="system"` → 只渲染 `x-scope === "system"` 的字段
- `scope="all"` → 渲染所有字段（调试用）

管道配置面板传 `scope="engineering"`，Settings 页传 `scope="system"`。

**实现注意：** 过滤逻辑必须处理 `scope="all"` 特殊值：`scope === 'all' || fieldScope === scope`。

### D5: SchemaForm anyOf 类型解析

**问题：** Pydantic v2 将 `str | None` 序列化为 `{"anyOf": [{"type": "string"}, {"type": "null"}]}`，不含顶层 `type` 字段。当前 SchemaForm 的控件分发逻辑依赖 `prop.type`，anyOf 字段会 fallthrough 到 "未设置" 占位符，导致不可编辑。

**选择：** SchemaForm 新增 `resolveType()` 工具函数，从 `anyOf` 中提取非 null 的基础类型：
```typescript
function resolveType(prop: JsonSchemaProperty): string | undefined {
  if (prop.type) return prop.type;
  const types = prop.anyOf?.map(s => s.type).filter(t => t !== 'null');
  return types?.[0];
}
```

所有控件分发改用 `resolveType(prop)` 替代 `prop.type`。

### D6: Settings 页系统配置面板结构

**选择：** 复用 SchemaForm + Collapse 面板，按节点分组

每个有 system scope 字段的节点渲染为一个 Collapse 面板，内部用 SchemaForm（scope="system"）。前端通过 `GET /pipeline/system-config-schema` 获取各节点的 system 字段 schema，无需硬编码节点列表。

## Risks / Trade-offs

**[Risk] JSON 文件并发写入** → 使用 `threading.Lock` + 原子写入。单实例部署场景下安全；多实例部署需升级为数据库存储，但当前是 Non-Goal。

**[Risk] 自动推断误标** → 自动推断仅在字段未显式标注时生效，且仅覆盖高置信度模式（`_endpoint`、特定 CLI path、`x-sensitive`）。不使用宽泛的 `_path$` 模式。新增节点开发者可显式标注 x-scope 覆盖自动推断。

**[Risk] GET /system-config 暴露 API key** → GET 端点对 `x-sensitive` 字段做掩码处理（返回 `"sk-****1234"` 格式），前端通过 Password 输入框编辑时只发送新值。PUT 端点接收原始值存储。

**[Trade-off] 默认无 x-scope 标注视为 engineering** → 减少冗余标注，但如果开发者忘记标注系统字段，该字段会出现在管道配置面板中。自动推断安全网缓解此问题。

**[Trade-off] system_config.json 明文存储 API key** → 当前阶段可接受（本地部署），后续可引入加密存储或 vault 集成，不影响 API 和前端设计。
