## 1. [backend] Config Model x-scope 标记

- [ ] 1.1 `generate_raw_mesh.py` — 5 个字段添加 x-scope=system（hunyuan3d_api_key 合并 x-sensitive + x-scope，其余 4 个 endpoint 字段新增 Field）
- [ ] 1.2 `neural.py` — 3 个字段添加 x-scope=system（neural_enabled, neural_endpoint, health_check_path）
- [ ] 1.3 `mesh_healer.py` — retopo_endpoint 添加 x-scope=system
- [ ] 1.4 `slice_to_gcode.py` — prusaslicer_path, orcaslicer_path 添加 x-scope=system

**文件：**
- 修改: `backend/graph/configs/generate_raw_mesh.py`
- 修改: `backend/graph/configs/neural.py`
- 修改: `backend/graph/configs/mesh_healer.py`
- 修改: `backend/graph/configs/slice_to_gcode.py`

## 2. [backend] enhance_config_schema 自动推断

- [ ] 2.1 `registry.py` — 添加 `_SYSTEM_PATTERN` 正则（`_endpoint$` + 精确匹配 `prusaslicer_path|orcaslicer_path` + `^neural_enabled$`）+ x-scope 自动推断逻辑（在现有 x-sensitive 检测之后；x-sensitive 字段也自动标 system）
- [ ] 2.2 `test_schema_sensitive.py` — 扩展测试：x-scope 自动推断、显式标注不被覆盖、x-sensitive 联动、非 CLI path 字段不被误标

**文件：**
- 修改: `backend/graph/registry.py`
- 修改: `tests/test_schema_sensitive.py`

## 3. [backend] SystemConfigStore 持久化

- [ ] 3.1 新建 `backend/graph/system_config.py` — SystemConfigStore 类（load/save/get_node，threading.Lock + NamedTemporaryFile 原子写入）
- [ ] 3.2 测试 SystemConfigStore — load/save/get_node 基础测试 + 文件不存在时返回空 dict + 原子写入安全

**文件：**
- 新增: `backend/graph/system_config.py`
- 新增: `tests/test_system_config.py`

## 4. [backend] 系统配置 REST API

- [ ] 4.1 `pipeline_config.py` — 新增 GET /pipeline/system-config-schema 端点（提取各节点 system scope 字段 schema，同步处理 required 列表）
- [ ] 4.2 `pipeline_config.py` — 新增 GET /pipeline/system-config 端点（x-sensitive 字段做掩码处理）
- [ ] 4.3 `pipeline_config.py` — 新增 PUT /pipeline/system-config 端点（scope 校验 + config_model 类型验证，replace 语义）
- [ ] 4.4 API 测试 — 覆盖：正常读写、掩码返回、拒绝 engineering 字段、拒绝类型错误值、unknown node 处理

**文件：**
- 修改: `backend/api/v1/pipeline_config.py`
- 新增: `tests/test_system_config_api.py`

## 5. [backend] NodeContext 运行时合并

- [ ] 5.1 `context.py` — from_state() 中合并 system_config_store.get_node() 作为 defaults（优先级：Pydantic default < system_config < per-request）
- [ ] 5.2 测试合并优先级 + 无系统配置时行为不变 + null 值正确传递

**文件：**
- 修改: `backend/graph/context.py`

## 6. [frontend] SchemaForm 增强

- [ ] 6.1 `SchemaForm/index.tsx` — 新增 `resolveType()` 工具函数，处理 Pydantic v2 anyOf 类型（从 anyOf 中提取非 null 基础类型），所有控件分发改用 resolveType()
- [ ] 6.2 `SchemaForm/index.tsx` — JsonSchemaProperty 接口新增 `'x-scope'?: string` 和 `anyOf?: Array<{type?: string}>`，SchemaFormProps 新增 `scope` prop（默认 engineering），添加字段过滤逻辑（`scope === 'all' || fieldScope === scope`）
- [ ] 6.3 `CustomPanel.tsx` — SchemaForm 调用处传入 `scope="engineering"`

**文件：**
- 修改: `frontend/src/components/SchemaForm/index.tsx`
- 修改: `frontend/src/components/PipelineConfigBar/CustomPanel.tsx`

## 7. [frontend] Settings 页系统配置面板

- [ ] 7.1 `api.ts` — 新增 getSystemConfigSchema(), getSystemConfig(), updateSystemConfig() 3 个 API 函数
- [ ] 7.2 新建 `SystemConfigPanel.tsx` — 调用 API 获取 schema + 数据，按节点渲染 Collapse 面板 + SchemaForm(scope="system")，保存/重置按钮
- [ ] 7.3 `Settings/index.tsx` — 新增"系统配置"tab

**文件：**
- 修改: `frontend/src/services/api.ts`
- 新增: `frontend/src/pages/Settings/SystemConfigPanel.tsx`
- 修改: `frontend/src/pages/Settings/index.tsx`

## 8. [test] 集成验证

- [ ] 8.1 后端：uv run pytest tests/ -v 全量通过
- [ ] 8.2 前端：npx tsc --noEmit + npm run lint 零错误
- [ ] 8.3 E2E 验证：管道配置面板不显示 system 字段、Settings 页显示 system 字段、保存后刷新持久
