## 1. 后端 API 标准化（Layer 1） `[backend]`

Skills: `streaming-api-patterns`, `sqlalchemy-orm`

- [ ] 1.1 `[backend]` 创建 `/api/v1/` 路由蓝图：新建 `backend/api/v1/` 目录，创建 `router.py` 统一挂载所有 v1 路由，主 app 中注册 `/api/v1` 前缀
- [ ] 1.2 `[backend]` 实现统一错误处理：新建 `backend/api/v1/errors.py`，定义 `ErrorResponse` 模型（`code` + `message` + `details`）和全局异常处理器（422 VALIDATION_FAILED / 404 JOB_NOT_FOUND / 409 INVALID_JOB_STATE）
- [ ] 1.3 `[backend]` 实现统一 Job 创建端点 `POST /api/v1/jobs`：接收 `input_type: "text" | "drawing" | "organic"` 字段，分发到对应管道，返回 `{ job_id, status: "created" }`
- [ ] 1.4 `[backend]` 实现 Job CRUD 端点：`GET /api/v1/jobs`（分页列表）、`GET /api/v1/jobs/{id}`（详情）、`DELETE /api/v1/jobs/{id}`（软删除）、`POST /api/v1/jobs/{id}/regenerate`（重生成）
- [ ] 1.5 `[backend]` 实现 HITL 确认端点 `POST /api/v1/jobs/{id}/confirm`：校验 job 状态为 `awaiting_confirmation`，接收 `confirmed_spec` 或 `confirmed_params`，恢复管道执行
- [ ] 1.6 `[backend]` 实现独立 SSE 订阅端点 `GET /api/v1/jobs/{id}/events`：独立 SSE 连接，流式推送管道进度事件，`completed` 为终止事件
- [ ] 1.7 `[backend]` 移除旧端点：删除 `/api/generate`、`/api/generate/drawing`、`/api/generate/organic` 等未版本化路由，确保所有旧路由返回 404
- [ ] 1.8 `[test]` 编写 API 层单元测试：覆盖所有 v1 端点的正常/异常路径，包括错误格式验证

## 2. 数据持久化（Layer 1） `[backend]`

Skills: `sqlalchemy-orm`

- [ ] 2.1 `[backend]` 激活 SQLAlchemy ORM：确认 `backend/db/models.py` 中 Job/OrganicJob 模型完整，补全缺失字段（printability、user_corrections 关联）
- [ ] 2.2 `[backend]` 实现 `JobRepository` Protocol 接口：定义 `create` / `get` / `list` / `update` / `delete` / `get_corrections` 抽象方法
- [ ] 2.3 `[backend]` 实现 `SQLiteJobRepository`：基于 aiosqlite + SQLAlchemy async session 实现所有 Repository 方法
- [ ] 2.4 `[backend]` 实现 `FileStorage` Protocol 接口：定义 `save` / `get_url` / `delete` 方法，`LocalFileStorage` 实现存储到 `outputs/{job_id}/`
- [ ] 2.5 `[backend]` 配置 Alembic 迁移：确认 `alembic.ini` + `alembic/` 目录完整，更新迁移脚本（jobs + organic_jobs + user_corrections 表）
- [ ] 2.6 `[backend]` 替换内存存储：全局搜索 `job_store`/`jobs_dict` 等内存字典，替换为 `await repository.xxx()` 调用
- [ ] 2.7 `[backend]` 实现 `user_corrections` 表和查询端点 `GET /api/v1/jobs/{id}/corrections`
- [ ] 2.8 `[test]` 编写持久化层测试：Repository CRUD、并发安全、迁移正确性

## 3. 后端管道集成（Layer 2） `[backend]`

Skills: `streaming-api-patterns`

依赖：Group 1 + Group 2 完成

- [ ] 3.1 `[backend]` IntentParser 替换 keyword 匹配：在 text 类型 job 创建时调用 IntentParser，异常/低置信度时 fallback 到 `_match_template`
- [ ] 3.2 `[backend]` PrintabilityChecker 接入精密管道：CadQuery 生成 STEP 后自动运行 PrintabilityChecker，结果写入 job 的 `printability` 字段，发送 `printability_checked` SSE 事件
- [ ] 3.3 `[backend]` PrintabilityChecker 接入有机管道：MeshPostProcessor 完成后运行 PrintabilityChecker，异常时 `printability: null` + 警告，不阻塞管道
- [ ] 3.4 `[backend]` HITL 图纸确认流实现：DrawingAnalyzer 完成后发送 `drawing_spec_ready` SSE 事件，job 状态设为 `awaiting_confirmation`；confirm 端点恢复 `generate_from_drawing_spec(confirmed_spec)`
- [ ] 3.5 `[backend]` 用户修正数据收集：confirm 时比较 `original_spec` 和 `confirmed_spec` 的字段级差异，插入 `user_corrections` 表
- [ ] 3.6 `[backend]` 有机管道 3MF 导出：MeshPostProcessor 完成后额外导出 `model.3mf`（trimesh export），`completed` 事件包含 `threemf_url`
- [ ] 3.7 `[backend]` 实时参数预览端点：将现有 `POST /api/preview/parametric` 迁移到 `POST /api/v1/preview/parametric`，添加 5s 硬超时 + LRU 缓存（50 条目）
- [ ] 3.8 `[test]` 编写管道集成测试：覆盖 IntentParser 路由、PrintabilityChecker 串联、HITL 确认流、3MF 导出、预览超时

## 4. 前端框架重建（Layer 3） `[frontend]`

Skills: `frontend-design`, `ui-ux-pro-max`, `ant-design`

依赖：Group 1（API 端点就绪）

- [ ] 4.1 `[frontend]` 创建 ThemeProvider：基于 Ant Design 6 `ConfigProvider` + `theme.algorithm`，React Context 管理亮暗状态，localStorage 持久化
- [ ] 4.2 `[frontend]` 创建 WorkbenchLayout 组件：三栏布局（左240px + 中flex:1 + 右300px），面板折叠按钮，折叠状态 localStorage 持久化
- [ ] 4.3 `[frontend]` 创建 TopNav 组件：Logo + Tab 导航（精密建模/创意雕塑/零件库）+ 主题切换按钮（☀/☾）+ 设置入口
- [ ] 4.4 `[frontend]` 重构路由系统：`/` → 重定向 `/precision`，`/precision`、`/organic`、`/library`、`/library/:jobId`，React Router 对齐新布局
- [ ] 4.5 `[frontend]` 重构 API 服务层：`frontend/src/services/api.ts` 所有请求改用 `/api/v1/` 前缀，统一错误解析对齐新 ErrorResponse 格式
- [ ] 4.6 `[frontend]` 实现 SSE 订阅 Hook：`useJobEvents(jobId)` 订阅 `GET /api/v1/jobs/{id}/events`，解析事件更新 job 状态
- [ ] 4.7 `[frontend]` 小屏适配：viewport < 768px 时左右面板降级为底部 Drawer
- [ ] 4.8 `[frontend]` Viewer3D 暗色适配：暗色模式时背景改为 `#0a0a0a`，环境光降低，确保模型在两种主题下清晰可见

## 5. 精密建模工作台（Layer 4） `[frontend]`

Skills: `frontend-design`, `ui-ux-pro-max`, `ant-design`

依赖：Group 4 完成

- [ ] 5.1 `[frontend]` 创建 InputPanel 组件：文本输入 + 图纸上传 + 模板选择三合一，作为空闲状态左面板内容
- [ ] 5.2 `[frontend]` 创建 DrawingSpecForm 组件：将 DrawingSpec JSON 渲染为可编辑结构化表单（零件类型、基体参数、特征列表），底部"确认并生成"按钮
- [ ] 5.3 `[frontend]` 改造 ParamForm 组件：适配新布局，Slider/InputNumber/Switch 带推荐值标注，底部"确认并生成"按钮
- [ ] 5.4 `[frontend]` 创建 PipelineProgress 组件：显示所有管道阶段及状态（pending/running/success/failed）+ 耗时
- [ ] 5.5 `[frontend]` 创建 PipelineLog 组件：右面板 SSE 事件实时滚动日志
- [ ] 5.6 `[frontend]` 重构 PrintReport 组件：对接真实 PrintabilityChecker 数据，展示可打印性评级 + 材料费用 + 工时估算
- [ ] 5.7 `[frontend]` 重构 DownloadPanel 组件：根据管道类型提供格式选择（STEP/GLB/STL/3MF），支持"保存到零件库"
- [ ] 5.8 `[frontend]` 实现左面板自动切换逻辑：根据 job 状态（idle → awaiting_confirmation → generating → refining → completed）自动切换面板内容
- [ ] 5.9 `[frontend]` 实现右面板联动逻辑：空闲显示推荐/历史，HITL 显示原图，生成中显示日志，完成显示 DfAM 报告

## 6. 创意雕塑工作台（Layer 4） `[frontend]`

Skills: `frontend-design`, `ui-ux-pro-max`, `ant-design`

依赖：Group 4 完成；可与 Group 5 并行

- [ ] 6.1 `[frontend]` 创建有机 InputPanel：文本描述 + 参考图上传 + 质量模式选择
- [ ] 6.2 `[frontend]` 复用 ConstraintForm 组件：适配新布局，尺寸限制 + 工程切削设置
- [ ] 6.3 `[frontend]` 复用 PipelineProgress/PipelineLog：适配有机管道阶段（生成 → 后处理 5 步骤）
- [ ] 6.4 `[frontend]` 实现有机工作台面板切换逻辑：对齐精密工作台的自动切换模式（输入 → 约束 → 生成中 → 完成）
- [ ] 6.5 `[frontend]` 有机工作台右面板联动：空闲显示风格灵感/最近生成，生成中显示 SSE 日志，完成显示 DfAM 报告 + 网格统计

## 7. 零件库（Layer 4） `[frontend]`

Skills: `frontend-design`, `ui-ux-pro-max`, `ant-design`

依赖：Group 4 完成；可与 Group 5/6 并行

- [ ] 7.1 `[frontend]` 创建 JobCard 组件：3D 缩略图 + 零件名 + 生成时间 + 可打印状态标签
- [ ] 7.2 `[frontend]` 创建 LibraryPage 页面：卡片网格布局 + 分页（每页 20 条）+ 空状态展示
- [ ] 7.3 `[frontend]` 实现搜索和筛选：按零件类型、可打印状态、输入类型筛选 + 关键词搜索，AND 逻辑组合
- [ ] 7.4 `[frontend]` 创建零件详情页面 `/library/:jobId`：完整 3D 预览 + DfAM 报告 + 参数元数据 + 下载/重生成按钮
- [ ] 7.5 `[frontend]` 实现重生成功能：调用 `POST /api/v1/jobs/{id}/regenerate`，携带原始参数跳转到对应工作台

## 8. 实时参数预览（Layer 4） `[frontend]`

Skills: `frontend-design`

依赖：Group 4 + Task 3.7 完成

- [ ] 8.1 `[frontend]` 创建 `useParametricPreview` Hook：debounce 500ms 调用预览 API，管理 loading/error/data 状态
- [ ] 8.2 `[frontend]` Viewer3D 集成热更新：接收 preview GLB → 替换当前模型（保持相机位姿），请求中显示 subtle loading overlay
- [ ] 8.3 `[frontend]` 超时降级 UI：预览超时/失败时显示"预览不可用"叠加层，保留上次成功的模型
- [ ] 8.4 `[frontend]` 预览可用性指示：ParamForm 根据模板是否支持预览，显示"实时预览"徽章或"预览不可用" + 手动按钮

## 9. 端到端验证 `[test:e2e]`

Skills: `qa-testing-strategy`, `e2e-testing-automation`

依赖：Group 1-8 全部完成

- [ ] 9.1 `[test:e2e]` 精密建模全流程 E2E：文本输入 → IntentParser → 模板匹配 → 参数确认 → 预览 → 生成 → DfAM 报告 → 下载 → 零件库查看
- [ ] 9.2 `[test:e2e]` 图纸路径全流程 E2E：图纸上传 → DrawingAnalyzer → HITL 表单确认（含修改）→ 生成 → DfAM 报告 → user_corrections 记录验证
- [ ] 9.3 `[test:e2e]` 创意雕塑全流程 E2E：描述输入 → 约束设置 → 生成 → 后处理 → 3MF 导出 → DfAM 报告 → 下载
- [ ] 9.4 `[test:e2e]` 亮暗主题切换测试：切换主题 → 所有页面/组件/3D 渲染正确适配 → 刷新后保持
- [ ] 9.5 `[test:e2e]` 数据持久化测试：创建 job → 重启后端 → 查询 job 数据完整 → 零件库正确展示
- [ ] 9.6 `[test:e2e]` 旧 API 废弃验证：所有旧端点（`/api/generate` 等）返回 404
