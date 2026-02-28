## Why

当前 CAD 生成管道存在三个关键缺陷：LLM 调用无超时导致 SSE 流永久挂起、全局 `_event_queues` 字典无生命周期管理造成内存泄漏、HITL 确认通过 HTTP 状态机拼接导致上下文丢失且无法断点续跑。引入 LangGraph 统一编排是一次性解决这三个问题的最直接路径，同时消除 V2/V3 历史命名混乱。

## What Changes

- **新增** `backend/graph/` 模块：LangGraph `StateGraph` 接管全部 Job 生命周期（创建 → 分析 → HITL → 生成 → 后处理 → 完成）
- **新增** LangGraph `interrupt()` / `Command(resume=...)` 原生 HITL 机制，替换现有 HTTP 状态机
- **新增** `AsyncSqliteSaver` checkpointing，复用现有 `cad3dify.db`，支持断点续跑
- **新增** LCEL `.with_retry()` + `asyncio.wait_for()` 为所有 LLM 节点提供框架级超时/重试/fallback
- **修改** `backend/api/v1/jobs.py`：POST 端点改为调用 `graph.astream_events()`，删除手写 SSE 生成器
- **修改** `backend/pipeline/pipeline.py`：函数重命名为能力描述性名称（`analyze_vision_spec`、`generate_step_from_spec` 等），逻辑不变
- **删除** `backend/api/v1/events.py` 中的 `_event_queues` 全局字典及相关函数
- **删除** `backend/pipeline/sse_bridge.py`（PipelineBridge 回调机制被 `adispatch_custom_event` 替代）
- **规范化** SSE 事件命名为 `job.<stage>` 格式（`job.created`、`job.generating`、`job.completed` 等）
- **BREAKING** `GET /api/v1/jobs/{id}/events` 端点事件格式从扁平 key 升级为 `{event, job_id, stage, message, data, ts}` 信封

## Capabilities

### New Capabilities

- `langgraph-job-orchestration`：LangGraph StateGraph 管理 CAD Job 完整生命周期，包含条件路由、节点级错误处理、AsyncSqliteSaver checkpointing 和断点续跑
- `llm-resilience`：LCEL with_retry + asyncio.wait_for 为意图解析和图纸分析 LLM 节点提供超时（60s）、重试（3次）、fallback 模型三层保障
- `graph-event-streaming`：通过 `adispatch_custom_event` + `graph.astream_events()` 实现拉式事件流，替代推式全局 Queue，生命周期与 Graph Run 绑定

### Modified Capabilities

- `hitl-confirmation`：HITL 从"HTTP POST 恢复状态"改为 LangGraph `interrupt()` / `Command(resume=...)` 模式，语义更强，支持 checkpoint 恢复

## Impact

- **新依赖**：`langgraph>=0.3.0`、`langgraph-checkpoint-sqlite>=2.0.0`
- **API 兼容**：`POST /api/v1/jobs`、`POST /api/v1/jobs/upload`、`POST /api/v1/jobs/{id}/confirm` 接口签名不变，响应格式（SSE）不变，事件名称升级（需前端适配）
- **DB**：现有 `cad3dify.db` 增加 LangGraph checkpoint 表（`checkpoints`、`checkpoint_blobs`），不影响现有 Job 表
- **测试**：现有 1192 个测试需适配新事件名称；新增 Graph 节点单元测试和 HITL 集成测试
