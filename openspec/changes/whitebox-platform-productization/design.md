## Context

CAD3Dify 已完成双引擎架构（精密建模 CadQuery + 有机概念 Tripo3D/Hunyuan3D）的核心模块开发。24+ API 端点、75+ 核心模块、17 个参数化 YAML 模板、完整的 Three.js 3D 渲染前端。

关键问题：模块已编码但未串联。PrintabilityChecker（522 行）、IntentParser（256 行）、OCR 引擎（71 行）、SQLAlchemy ORM 模型——全部完整实现但未接入主管道。后端 API 缺乏统一规范（分散端点、不一致错误格式）。前端是原型级 Ant Design 侧边栏布局，无暗色模式、无零件库。

目标用户：B2B 工业客户（3D 打印车间），交互按新手标准设计。

详细设计参见 brainstorming 产出：`docs/plans/2026-02-28-whitebox-platform-productization-design.md`

## Goals / Non-Goals

**Goals:**
- 后端 API 统一为 RESTful `/api/v1/` + SSE 独立订阅，错误格式一致
- 6 个已完成模块串入主管道（PrintabilityChecker、HITL 图纸确认、IntentParser、持久化、实时预览、3MF）
- 前端从侧边栏布局全面重设计为三栏工作台 + 亮暗主题
- 零件库（历史 + 详情 + 重生成）
- 数据持久化（SQLite ORM 激活，内存 dict 移除）
- 存储抽象接口预留 PostgreSQL/S3 迁移

**Non-Goals:**
- 用户认证/多租户系统（当前单机 = 单客户）
- DfAM 3D 热力图着色（per-face 着色，开发量大，后续迭代）
- VLM 微调/数据飞轮训练（依赖数据积累，长期规划）
- 多语言国际化（当前仅中文）
- 移动端原生适配（仅做响应式兼容）

## Decisions

### D1: API 路由统一方案

统一为 `/api/v1/` 前缀。三个生成入口（`/generate`、`/generate/drawing`、`/generate/organic`）合并为 `POST /api/v1/jobs`，通过 `input_type: "text" | "drawing" | "organic"` 区分。

**替代方案**：保留分散端点 + 仅加前缀。
**否决理由**：Job 是核心资源，统一 CRUD 入口更 RESTful，前端代码更简洁。

### D2: SSE 事件流改为独立订阅

`GET /api/v1/jobs/{id}/events` 独立 SSE 连接，而非嵌入 POST 响应。

**替代方案**：保持 POST 返回 SSE。
**否决理由**：独立订阅允许断线重连、页面刷新后重新订阅、多客户端同时订阅同一 Job。

### D3: 数据持久化 — SQLite 先行 + 接口抽象

激活已有 `backend/db/` ORM 代码。通过 `JobRepository` / `FileStorage` Protocol 抽象，环境变量 `DATABASE_URL` 切换后端。

**替代方案**：直接用 PostgreSQL。
**否决理由**：单机部署场景 SQLite 更简单，Protocol 接口保证迁移透明。

### D4: 前端布局 — 三栏工作台

左面板(240px, 可折叠) + 中央3D预览(flex:1) + 右面板(300px, 可折叠)。顶部 Tab 导航取代侧边栏 Menu。

**替代方案A**：保持当前侧边栏 + 内容区。
**替代方案B**：上下分区（3D 上方，参数下方）。
**否决理由**：三栏最大化 3D 预览空间，同时保持参数和报告始终可见。专业 CAD 工具的标准范式。

### D5: 亮暗主题 — Ant Design 6 原生方案

`ConfigProvider` + `theme.algorithm` 切换（`defaultAlgorithm` / `darkAlgorithm`）。通过 React Context + localStorage 持久化用户偏好。

**替代方案**：CSS 变量手动实现。
**否决理由**：antd 原生方案零外部依赖，所有组件自动适配，仅需处理 Three.js 背景色同步。

### D6: 左面板内容自动切换

管道阶段变化时左面板内容自动替换（输入→HITL 表单→进度条→下载），用户无需手动导航。

**替代方案**：Tab 或 Accordion 手动切换。
**否决理由**：步骤式向导更符合"新手友好"定位，用户无需知道下一步做什么。

### D7: HITL 图纸确认 — 结构化表单

将 DrawingSpec JSON 渲染为可编辑表单（零件类型、基体参数、特征列表），左侧表单 + 右侧原图对照。修改记录存入 `user_corrections` 表。

**替代方案**：纯文本确认（仅显示/隐藏 JSON）。
**否决理由**：结构化表单新手可读、专家可改，且修正数据直接服务数据飞轮。

### D8: 实时预览 — Debounce 500ms

前端参数变化 → 500ms debounce → `POST /api/v1/preview/parametric` → GLB → Viewer3D 热更新。后端 5s 硬超时，超时返回"预览不可用"。

**替代方案**：手动点击"预览"按钮。
**否决理由**：自动预览交互更流畅，debounce 已经足够节省资源。

## Risks / Trade-offs

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| API BREAKING 变更导致前端全面改动 | 高 | 前后端同步重构，同一 Layer 完成 |
| CadQuery 实时预览超时（复杂零件） | 中 | 5s 硬超时 + "预览不可用" 降级 |
| SQLite 并发写入（多 worker 部署） | 中 | 当前单 worker 无问题；Protocol 接口预留 PostgreSQL 迁移 |
| 三栏布局在小屏幕上拥挤 | 低 | 面板可折叠 + <768px 降级为抽屉 |
| IntentParser LLM 调用不稳定 | 低 | 保留 keyword 匹配 fallback |
| SSE 独立订阅增加连接数 | 低 | 单 Job 仅一个 SSE 连接，sse-starlette 处理良好 |

## Migration Plan

1. **Layer 1（后端 API）**：路由重构 + 错误统一 + 持久化切换。完成后旧端点移除。
2. **Layer 2（后端功能）**：在新 API 上串联模块。每个模块串联后独立测试。
3. **Layer 3（前端框架）**：WorkbenchLayout + ThemeProvider + 路由重构。对齐新 API。
4. **Layer 4（前端功能）**：逐页面重建。每页面完成后 E2E 验证。

回滚策略：git tag 标记每个 Layer 完成点。Layer 间无交叉依赖，可独立回滚。

## Open Questions

- 零件库 3D 缩略图生成方式：后端预渲染 PNG vs 前端 Three.js 实时渲染小尺寸 Canvas？
- SSE 断线重连策略：`EventSource` 原生重连 vs 自定义 `fetch` + 手动重连？
