## Why

当前 CAD3Dify 平台存在严重的"最后一公里"问题：75+ 核心模块已编码完成（PrintabilityChecker、IntentParser、OCR 引擎、数据库 ORM），但各模块独立运行、未串入主管道。同时后端 API 缺乏统一规范（分散端点、不一致的错误格式、内存存储），前端仍是原型级 UI（侧边栏布局、无暗色模式、无零件库）。要从"技术 Demo"演进为"可对外交付的 B2B 工业级产品"，必须完成 API 标准化、模块串联和前端全面重设计。

## What Changes

### 后端 API 标准化
- **BREAKING**: 所有 API 路由统一为 `/api/v1/` 前缀（原 `/api/` 路由废弃）
- **BREAKING**: `POST /generate`、`POST /generate/drawing`、`POST /generate/organic` 三个入口统一为 `POST /api/v1/jobs`，通过 `input_type` 字段区分
- **BREAKING**: SSE 事件流从"嵌入式响应"改为"独立订阅"：`GET /api/v1/jobs/{id}/events`
- 统一错误响应格式：`{ "error": { "code", "message", "details" } }`
- 数据持久化：内存 dict 替换为 SQLite ORM（已有代码激活）
- 存储抽象接口：`JobRepository` + `FileStorage` Protocol，预留 PostgreSQL/S3 迁移

### 后端功能串联
- PrintabilityChecker 接入所有生成管道（精密 + 有机），新增 `printability_checked` SSE 事件
- 图纸路径 HITL 确认流：拆分为 analyze + confirm 两步
- IntentParser 替换 keyword 匹配（`_match_template`），保留 keyword fallback
- 有机管道 3MF 导出（`trimesh.export("model.3mf")`）
- 用户修正数据收集（HITL 确认时记录 diff → `user_corrections` 表）

### 前端全面重设计
- 三栏工作台布局：左面板(240px) + 中央3D预览(flex) + 右面板(300px)
- 亮暗双模式主题（Ant Design 6 `theme.algorithm` 切换）
- 顶部 Tab 导航取代侧边栏 Menu
- 左面板随管道阶段自动切换内容（步骤式向导）
- 新增 DrawingSpecForm（HITL 图纸确认结构化表单）
- 新增零件库页面（历史列表 + 详情 + 重生成）
- 新增 PipelineLog（SSE 事件实时日志组件）
- PrintReport 重构：对接真实 PrintabilityChecker 数据
- Viewer3D 暗色主题适配
- 实时参数预览：debounce 500ms → 后端渲染 → 3D 热更新

## Capabilities

### New Capabilities
- `api-standardization`: 后端 API 统一为 /api/v1/ + Job 生命周期 + 错误规范 + SSE 独立订阅
- `data-persistence`: SQLite 持久化实装 + 存储抽象接口（JobRepository/FileStorage Protocol）
- `pipeline-integration`: 已完成模块串入主管道（PrintabilityChecker、IntentParser、HITL 图纸确认、3MF 导出、修正数据收集）
- `workbench-ui`: 三栏工作台布局 + 亮暗主题 + 步骤式向导 + 面板自动切换
- `parts-library`: 零件库页面（历史列表 + 详情 + 重生成 + 筛选搜索）
- `realtime-preview`: 参数调整实时 3D 预览（debounce + 后端渲染 + 热更新）

### Modified Capabilities
（无已有 specs 需要修改）

## Impact

### 后端
- `backend/api/*.py` — 路由重构（v1 前缀 + 统一入口）
- `backend/api/errors.py` — 新建（统一错误处理）
- `backend/db/` — 激活已有 ORM（models + repository）
- `backend/pipeline/` — SSE 独立端点改造
- `backend/core/printability.py` — 调用点新增（generate.py + organic.py）
- `backend/core/intent_parser.py` — 替换 _match_template 调用

### 前端
- `frontend/src/layouts/` — 全新 WorkbenchLayout + TopNav + ThemeProvider
- `frontend/src/pages/` — Precision/Organic/Library 三大页面重建
- `frontend/src/components/` — 新增 DrawingSpecForm、PipelineLog、JobCard、InputPanel
- `frontend/src/services/api.ts` — 对齐 /api/v1/ 端点
- `frontend/src/App.tsx` — 路由重构

### 依赖
- 无新增外部依赖（所有技术栈已在用）
- Alembic 迁移配置新增
