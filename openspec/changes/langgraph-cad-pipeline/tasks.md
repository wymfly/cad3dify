## 1. 依赖安装与项目配置

- [ ] 1.1 在 `pyproject.toml` 添加 `langgraph>=0.3.0,<1.0` 和 `langgraph-checkpoint-sqlite>=2.0.0,<3.0`
- [ ] 1.2 运行 `uv add langgraph langgraph-checkpoint-sqlite` 并提交 `uv.lock`
- [ ] 1.3 验证 `uv run python -c "import langgraph; from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver"` 无错误

## 2. CadJobState 与 Graph 状态定义

- [ ] 2.1 创建 `backend/graph/__init__.py`（空文件）
- [ ] 2.2 创建 `backend/graph/state.py`：定义 `CadJobState` TypedDict（字段：job_id, input_type, input_text, image_path, intent, matched_template, drawing_spec, confirmed_params, confirmed_spec, disclaimer_accepted, step_path, model_url, printability, status, error）

## 3. 能力函数重命名（pipeline 层）

- [ ] 3.1 将 `backend/pipeline/pipeline.py` 重命名为 `backend/pipeline/vision_cad_pipeline.py`
- [ ] 3.2 在 `vision_cad_pipeline.py` 中将 `analyze_drawing()` 重命名为 `analyze_vision_spec()`，保留旧名 alias 一个版本
- [ ] 3.3 将 `generate_from_drawing_spec()` 重命名为 `generate_step_from_spec()`，保留旧名 alias
- [ ] 3.4 将 `generate_step_v2()` 重命名为 `analyze_and_generate_step()`，保留旧名 alias
- [ ] 3.5 将 `_convert_step_to_glb()` 重命名为 `convert_step_to_preview()`，保留旧名 alias
- [ ] 3.6 将 `_run_printability_check()` 重命名为 `check_printability()`，保留旧名 alias
- [ ] 3.7 更新所有 import 引用新函数名（搜索全项目）
- [ ] 3.8 运行 `uv run pytest tests/ -v` 确认现有 1192 个测试仍通过

## 4. Graph 节点实现

- [ ] 4.1 创建 `backend/graph/nodes/__init__.py`
- [ ] 4.2 创建 `backend/graph/nodes/lifecycle.py`：实现 `create_job_node`（创建 DB Job，dispatch `job.created` 事件）
- [ ] 4.3 在 `lifecycle.py` 实现 `confirm_with_user_node`（调用 `interrupt()`，dispatch `job.awaiting_confirmation` 事件）
- [ ] 4.4 在 `lifecycle.py` 实现 `finalize_node`（更新 DB 为 COMPLETED/FAILED，dispatch `job.completed` 或 `job.failed`）
- [ ] 4.5 创建 `backend/graph/nodes/analysis.py`：实现 `analyze_intent_node`（LCEL chain with_retry + asyncio.wait_for 60s，dispatch `job.intent_analyzed`）
- [ ] 4.6 在 `analysis.py` 实现 `analyze_vision_node`（asyncio.to_thread 包装 `analyze_vision_spec()`，dispatch `job.vision_analyzing` 和 `job.spec_ready`）
- [ ] 4.7 在 `analysis.py` 实现 `stub_organic_node`（直接 dispatch `job.awaiting_confirmation`，不做 LLM 分析）
- [ ] 4.8 创建 `backend/graph/nodes/generation.py`：实现 `generate_step_text_node`（TemplateEngine + Sandbox，dispatch `job.generating`，幂等检查）
- [ ] 4.9 在 `generation.py` 实现 `generate_step_drawing_node`（asyncio.to_thread 包装 `generate_step_from_spec()`，dispatch `job.generating`，幂等检查：`if state["step_path"] and Path(state["step_path"]).exists(): return {}`）
- [ ] 4.10 创建 `backend/graph/nodes/postprocess.py`：实现 `convert_preview_node`（asyncio.to_thread 包装 `convert_step_to_preview()`，dispatch `job.preview_ready`）
- [ ] 4.11 在 `postprocess.py` 实现 `check_printability_node`（asyncio.to_thread 包装 `check_printability()`，dispatch `job.printability_ready`）

## 5. Graph 路由与构建

- [ ] 5.1 创建 `backend/graph/routing.py`：实现 `route_by_input_type(state)` 返回 `"text"` | `"drawing"` | `"organic"`
- [ ] 5.2 在 `routing.py` 实现 `route_after_confirm(state)` 返回 `"text"` | `"drawing"`（organic 走 drawing 路径）
- [ ] 5.3 创建 `backend/graph/builder.py`：定义 `CadJobStateGraph` StateGraph，添加所有节点，添加条件边（route_by_input_type → analysis nodes）
- [ ] 5.4 在 `builder.py` 实现 `get_compiled_graph(db_path: str) -> CompiledStateGraph`：使用 `AsyncSqliteSaver.from_conn_string(db_path)` 作为 checkpointer，`interrupt_before=["confirm_with_user_node"]`
- [ ] 5.5 在 `backend/graph/__init__.py` 导出 `get_compiled_graph`

## 6. LLM 超时/重试工具

- [ ] 6.1 创建 `backend/graph/llm_utils.py`：实现 `build_intent_chain(primary_llm, fallback_llm) -> Runnable`（LCEL with_retry + with_fallbacks）
- [ ] 6.2 在 `llm_utils.py` 实现 `build_vision_chain(primary_llm) -> Runnable`（无 fallback，但保留 retry）
- [ ] 6.3 为两个 chain 添加单元测试（mock LLM，验证 retry 次数和 fallback 触发）

## 7. API 层切换

- [ ] 7.1 在 `backend/main.py`（或 lifespan）初始化 `cad_graph = await get_compiled_graph(DB_PATH)`，作为应用级单例
- [ ] 7.2 修改 `backend/api/v1/jobs.py` 中的 POST `/api/v1/jobs` 端点：替换手写 SSE 生成器为 `cad_graph.astream_events(initial_state, config, version="v2")` + `on_custom_event` 过滤
- [ ] 7.3 修改 POST `/api/v1/jobs/upload` 端点：同样替换为 Graph astream_events
- [ ] 7.4 修改 POST `/api/v1/jobs/{id}/confirm` 端点：替换为 `cad_graph.astream_events(Command(resume=body.model_dump()), config, version="v2")`
- [ ] 7.5 保留 GET `/api/v1/jobs/{id}/events` 端点（heartbeat 轮询，过渡期不删除）

## 8. 废弃代码清理

- [ ] 8.1 删除 `backend/api/v1/events.py` 中的 `_event_queues` 全局字典及 `emit_event`、`cleanup_queue` 函数
- [ ] 8.2 删除 `backend/pipeline/sse_bridge.py`（PipelineBridge 和相关回调已被 adispatch_custom_event 替代）
- [ ] 8.3 删除 `backend/api/v1/jobs.py` 中已废弃的手写 SSE 生成器函数（`_text_sse_generator` 等）
- [ ] 8.4 搜索并删除全项目中 `_event_queues`、`PipelineBridge`、`emit_event`、`cleanup_queue` 的所有引用

## 9. 测试更新与新增

- [ ] 9.1 更新现有测试中使用旧 SSE 事件名（`job_created`、`intent_parsed` 等）的断言，改为新名（`job.created`、`job.intent_analyzed` 等）
- [ ] 9.2 新增 `tests/test_graph_nodes.py`：为每个 Graph 节点编写单元测试（mock 外部依赖，验证 State 更新和 dispatch 事件）
- [ ] 9.3 新增 `tests/test_graph_builder.py`：编译 Graph，用 `graph.invoke()` 模式（非 astream_events）测试完整 text 路径和 drawing 路径
- [ ] 9.4 新增 HITL 集成测试：验证 `interrupt()` 暂停后 `Command(resume=...)` 能正确恢复执行
- [ ] 9.5 新增 LLM 超时测试：mock chain 模拟 asyncio.TimeoutError，验证节点返回 `{"status": "failed"}` 而非挂起
- [ ] 9.6 运行 `uv run pytest tests/ -v` 确认全部测试通过（≥1192 个）

## 10. 验收检查

- [ ] 10.1 验证 `uv run pytest tests/ -v` 全部通过
- [ ] 10.2 手动测试 POST /api/v1/jobs（text）：首个 SSE 事件为 `job.created`
- [ ] 10.3 手动测试 POST /api/v1/jobs/upload（drawing）：含 `job.vision_analyzing` → `job.spec_ready`
- [ ] 10.4 手动测试 POST /api/v1/jobs/{id}/confirm：返回 `job.generating` → `job.completed`
- [ ] 10.5 验证 LLM 节点超时 60s 后发 `job.failed` 而非挂起
- [ ] 10.6 验证进程重启后通过 `thread_id` 能从 AsyncSqliteSaver 恢复 Job 状态
- [ ] 10.7 确认 `_event_queues` 全局 dict 不再存在于代码库（`grep -r "_event_queues" backend/` 无输出）
