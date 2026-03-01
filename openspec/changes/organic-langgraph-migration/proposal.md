## Why

创意雕塑（organic）管道使用独立 FastAPI 异步生成器编排，与精密建模（text/drawing）的 LangGraph StateGraph 架构割裂。导致两套 API 端点、两套数据模型、两套 SSE 事件格式并存，且 organic 管道缺乏 HITL 确认、框架级超时/重试等能力。统一到 LangGraph 可消除代码重复、简化前端调用逻辑、为 organic 引入参数确认流程。

## What Changes

- **BREAKING**: 删除 `/api/v1/organic` 独立端点，organic 统一走 `/api/v1/jobs`（`input_type="organic"`）
- 将 `stub_organic_node` 替换为 `analyze_organic_node`（调用 OrganicSpecBuilder）
- 新增 `generate_organic_mesh_node`（调用 MeshProvider）和 `postprocess_organic_node`（修复/缩放/布尔/导出/可打印性）
- organic 经过 `confirm_with_user` HITL 中断，前端新增 spec 确认界面
- SSE 事件统一为 `job.*` 命名空间（`job.organic_spec_ready`、`job.post_processing`、`job.generating`）
- DB 统一：organic Job 写入 `JobModel` 表，`OrganicJobModel` 保留只读
- 前端 `useOrganicWorkflow` hook 改为调用 `/api/v1/jobs` 端点

## Capabilities

### New Capabilities
- `organic-graph-nodes`: organic 管道的 3 个 LangGraph 节点（analyze、generate_mesh、postprocess），含后处理子步骤 SSE 事件
- `organic-hitl-confirmation`: organic 管道的 HITL 参数确认流程（spec 预览 + 用户编辑 + 确认恢复）

### Modified Capabilities
- `langgraph-job-orchestration`: CadJobState 扩展 organic 字段，图拓扑新增 organic 路径，路由逻辑扩展
- `graph-event-streaming`: 新增 organic 专有事件（`job.organic_spec_ready`、`job.post_processing`）
- `hitl-confirmation`: confirm_with_user 节点需处理 organic 模式的确认数据

## Impact

- **后端**：`backend/graph/`（state、builder、routing、nodes）、`backend/api/v1/jobs.py`、`backend/api/v1/organic.py`（删除）
- **前端**：`frontend/src/pages/OrganicGenerate/OrganicWorkflow.tsx`、`OrganicWorkflowContext.tsx`
- **数据库**：`OrganicJobModel` 不再写入新数据，旧数据查询保留
- **依赖**：无新增 Python/npm 依赖
