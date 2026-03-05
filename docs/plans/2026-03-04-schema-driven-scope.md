# Schema-Driven 参数分层：x-scope 实施方案

## Context

管道配置 UI 当前把所有 config_schema 字段混在一起渲染——API key、endpoint URL 等系统参数出现在管道配置面板中。用户需要一套纯 schema-driven 架构：后端 Pydantic model 标注 `x-scope`，前端自动按 scope 过滤渲染，新增节点/参数时零前端改动。

## 方案概要

在已有的 `x-sensitive` / `x-group` 扩展模式基础上，新增 `x-scope: "system" | "engineering"`（默认 engineering）。管道配置面板只渲染 engineering 字段，设置页新增面板渲染 system 字段。系统参数持久化到 JSON 文件，运行时合并到节点配置。

---

## T1: 后端 Config Model 添加 x-scope 标记

**文件：**
- `backend/graph/configs/generate_raw_mesh.py` — 5 个字段标注 system
- `backend/graph/configs/neural.py` — 3 个字段标注 system（neural_enabled, neural_endpoint, health_check_path）
- `backend/graph/configs/mesh_healer.py` — 1 个字段标注 system（retopo_endpoint）
- `backend/graph/configs/slice_to_gcode.py` — 2 个字段标注 system（prusaslicer_path, orcaslicer_path）

标注方式（与 x-sensitive 相同模式）：
```python
hunyuan3d_endpoint: str | None = Field(
    default=None,
    json_schema_extra={"x-scope": "system"},
)
```

对于已有 `x-sensitive` 的字段，合并到同一个 dict：
```python
hunyuan3d_api_key: str | None = Field(
    default=None,
    json_schema_extra={"x-sensitive": True, "x-scope": "system"},
)
```

**不标注的字段**（默认 engineering）：timeout, output_format, voxel_resolution, layer_height, neural_timeout 等所有工程参数。

---

## T2: enhance_config_schema() 添加 x-scope 安全网

**文件：** `backend/graph/registry.py`

在现有 x-sensitive 自动检测之后，新增 x-scope 自动推断：
- 已标 x-sensitive 的字段 → 自动 system
- 字段名匹配 `_endpoint`、`_path`（但排除 `health_check_path` 已由 T1 显式标注）→ system
- 字段名匹配 `neural_enabled` → system

新增正则：`_SYSTEM_PATTERN = re.compile(r"(_endpoint$|_path$|^neural_enabled$)", re.IGNORECASE)`

仅在字段**未显式标注** x-scope 时生效。

---

## T3: 后端系统配置持久化 + API

**新增文件：** `backend/graph/system_config.py`
- `SystemConfigStore` 类：JSON 文件读写（`backend/data/system_config.json`）
- 线程安全，原子写入（tmp + rename）
- 模块级 singleton `system_config_store`

**修改文件：** `backend/api/v1/pipeline_config.py`

新增 3 个端点：
- `GET /pipeline/system-config-schema` — 返回每个节点的 system scope 字段 schema（供 Settings 页渲染表单）
- `GET /pipeline/system-config` — 返回当前系统配置值
- `PUT /pipeline/system-config` — 保存系统配置（校验只接受 system scope 字段）

---

## T4: NodeContext.from_state() 合并系统配置

**文件：** `backend/graph/context.py` L137-156

在构建 config 对象前，合并系统配置作为 defaults：
```python
from backend.graph.system_config import system_config_store
system_defaults = system_config_store.get_node(desc.name)
merged = {**system_defaults, **raw_config} if system_defaults else raw_config
config = config_cls(**merged) if merged else config_cls()
```

优先级：Pydantic default < system_config.json < per-request pipeline_config

---

## T5: 前端 SchemaForm scope 过滤

**文件：** `frontend/src/components/SchemaForm/index.tsx`
- `JsonSchemaProperty` 接口新增 `'x-scope'?: string`
- `SchemaFormProps` 新增 `scope?: 'engineering' | 'system' | 'all'`（默认 `'engineering'`）
- 字段过滤逻辑：`fieldScope = prop['x-scope'] ?? 'engineering'; return fieldScope === scope`

**文件：** `frontend/src/components/PipelineConfigBar/CustomPanel.tsx`
- SchemaForm 调用处传入 `scope="engineering"`（显式声明，虽然是默认值）

---

## T6: 前端 Settings 页 SystemConfigPanel

**新增文件：** `frontend/src/pages/Settings/SystemConfigPanel.tsx`
- 调用 `getSystemConfigSchema()` 获取各节点 system 字段 schema
- 调用 `getSystemConfig()` / `updateSystemConfig()` 读写配置
- 每个有 system 字段的节点渲染为 Collapse 面板
- 内部复用 SchemaForm（scope="system"）
- 保存/重置按钮

**修改文件：** `frontend/src/pages/Settings/index.tsx`
- 新增 "系统配置" tab

**修改文件：** `frontend/src/services/api.ts`
- 新增 `getSystemConfigSchema()`, `getSystemConfig()`, `updateSystemConfig()` 3 个函数

---

## T7: 测试 + 验证

**后端测试：** `tests/test_schema_sensitive.py` 扩展
- x-scope 自动推断（endpoint → system, 普通字段 → 无标注）
- x-scope 不覆盖显式标注
- x-sensitive 字段自动获得 x-scope=system
- SystemConfigStore load/save 基础测试

**E2E 验证：**
- 管道配置面板：展开节点后不显示 API key / endpoint 字段
- 设置页系统配置 tab：显示 API key / endpoint 字段
- 保存系统配置 → 刷新 → 值持久
- tsc --noEmit + lint 零错误

---

## 文件修改清单

| 文件 | 操作 | 任务 |
|------|------|------|
| `backend/graph/configs/generate_raw_mesh.py` | 修改 | T1 |
| `backend/graph/configs/neural.py` | 修改 | T1 |
| `backend/graph/configs/mesh_healer.py` | 修改 | T1 |
| `backend/graph/configs/slice_to_gcode.py` | 修改 | T1 |
| `backend/graph/registry.py` | 修改 | T2 |
| `backend/graph/system_config.py` | **新增** | T3 |
| `backend/api/v1/pipeline_config.py` | 修改 | T3 |
| `backend/graph/context.py` | 修改 | T4 |
| `frontend/src/components/SchemaForm/index.tsx` | 修改 | T5 |
| `frontend/src/components/PipelineConfigBar/CustomPanel.tsx` | 修改 | T5 |
| `frontend/src/pages/Settings/SystemConfigPanel.tsx` | **新增** | T6 |
| `frontend/src/pages/Settings/index.tsx` | 修改 | T6 |
| `frontend/src/services/api.ts` | 修改 | T6 |
| `tests/test_schema_sensitive.py` | 修改 | T7 |

## 依赖图

```
T1 (config models) → T2 (enhance_config_schema) → T5 (前端 scope 过滤)
                                                  → T6 (Settings 面板, 依赖 T3+T5)
T3 (持久化 + API) → T4 (context 合并)
                   → T6
T7 (测试) → 依赖全部
```

后端 T1-T4 和前端 T5-T6 天然文件隔离，可前后端并行开发。
