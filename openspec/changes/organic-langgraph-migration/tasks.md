## 1. CadJobState 扩展 + 路由更新 `[backend]`

- [ ] 1.1 在 `backend/graph/state.py` 中扩展 CadJobState：新增 `organic_spec`、`organic_provider`、`organic_quality_mode`、`organic_reference_image`、`organic_constraints`、`raw_mesh_path`、`mesh_stats`、`organic_warnings`（使用 `Annotated[list[str], operator.add]` 防止节点返回时覆盖已有警告）、`organic_result` 字段；`organic_spec` 映射到 `STATE_TO_ORM_MAPPING`（复用 `result` JSON 列的 organic 子键，无需 Alembic 迁移）
- [ ] 1.2 ~~移至 3.4~~ 见 group 3（路由变更必须与 builder 映射同步，避免无效中间状态）
- [ ] 1.3 在 `backend/api/v1/jobs.py` 中扩展 `CreateJobRequest`：新增 `reference_image: str | None = None`、`constraints: dict[str, Any] | None = None`（含 bounding_box、engineering_cuts）字段；保持 `ConfirmRequest.confirmed_params: dict[str, float]` 不变（text/drawing 数值参数需要 Pydantic 类型强转），organic 确认改用已有的 `confirmed_spec: dict[str, Any]` 字段传递字符串覆盖值（prompt_en、provider、quality_mode、bounding_box）；`create_job_endpoint` 中为 organic 模式添加 `input_text or reference_image` 非空校验（保持与旧端点校验一致）；将 organic 字段映射到初始 state（`organic_provider`、`organic_quality_mode`、`organic_reference_image`、`organic_constraints`）
- [ ] 1.4 在 `backend/api/v1/jobs.py` 的 `confirm_job_endpoint` 中添加 organic 分支：当 `input_type=organic` 时，从 `confirmed_spec` 字段构建 resume_value，将用户编辑的 prompt_en/bounding_box/quality_mode/provider 合并到 state 对应字段（`organic_spec`、`organic_quality_mode`、`organic_provider`）

## 2. 后端节点实现 `[backend]`

依赖：1

- [ ] 2.1 创建 `backend/graph/nodes/organic.py`：实现 `analyze_organic_node`——调用 OrganicSpecBuilder.build()，60s 超时，成功后 dispatch `job.organic_spec_ready` 事件，设置 status=awaiting_confirmation；**关键**：必须在返回前调用 `_safe_update_job(job_id, status="awaiting_confirmation", organic_spec=spec_dict)` 将 organic_spec 写入 DB（参照 analyze_intent_node 写入 intent 的模式），否则用户刷新页面时 GET /api/v1/jobs/{id} 无法返回 spec 数据导致确认 UI 空白
- [ ] 2.2 实现 `generate_organic_mesh_node`——创建 MeshProvider，读取 reference_image（如有），调用 provider.generate()，幂等检查，dispatch `job.generating` 事件；传入 `on_progress` 回调在生成过程中每 15-30s dispatch keepalive 事件（防止 3-5 分钟 SSE 连接超时断开）；**注意 sync/async 桥接**：若 provider.generate() 运行在同步上下文（如 asyncio.to_thread），回调不能直接调用 `adispatch_custom_event`（async），需使用 `langchain_core.callbacks.dispatch_custom_event`（同步版本）或通过 `loop.call_soon_threadsafe()` 桥接
- [ ] 2.3 实现 `postprocess_organic_node`——通过 `asyncio.to_thread` 包装 CPU-bound 操作（pymeshlab/trimesh/manifold3d），顺序执行 load/repair/scale/boolean/validate/export/printability，每步 dispatch `job.post_processing` 事件，布尔失败优雅降级，导出 GLB/STL/3MF，运行可打印性检查

## 3. 图拓扑更新 `[backend]`

依赖：2

- [ ] 3.1 在 `backend/graph/builder.py` 中删除 `stub_organic` 节点，注册 `analyze_organic`、`generate_organic_mesh`、`postprocess_organic` 三个新节点
- [ ] 3.2 更新边定义：`create_job` → `analyze_organic`（organic 路由）、`confirm_with_user` → `generate_organic_mesh`（organic 路由）、`generate_organic_mesh` → `postprocess_organic`、`postprocess_organic` → `finalize`；**注意**：条件边字典必须显式添加 `"organic": "generate_organic_mesh"` 映射
- [ ] 3.3 从 `backend/graph/nodes/analysis.py` 中删除 `stub_organic_node` 函数及其 import
- [ ] 3.4 在 `backend/graph/routing.py` 中修改 `route_after_confirm`：organic 不再返回 `"finalize"`，改为返回 `"organic"`（必须与 3.2 同步实施，确保 builder 映射先于路由变更生效）

## 4. finalize_node 扩展 `[backend]`

依赖：1

- [ ] 4.1 修改 `backend/graph/nodes/lifecycle.py` 中 `finalize_node`：当 `input_type=organic` 时，从 `organic_result` 字段组装 `result` JSON（含 model_url、stl_url、threemf_url、mesh_stats、warnings、printability），写入 DB Job 表；同时确保 `job.completed` SSE 事件 payload 也包含这些 organic 字段供前端直接消费

## 5. 单元测试 `[backend]` `[test]`

依赖：2, 3, 4

- [ ] 5.1 编写 `tests/test_organic_nodes.py`：mock OrganicSpecBuilder 测试 `analyze_organic_node`（成功、超时、fallback）
- [ ] 5.2 测试 `generate_organic_mesh_node`（成功、幂等跳过、Provider 失败、reference_image 加载）
- [ ] 5.3 测试 `postprocess_organic_node`（全流程成功、布尔失败降级、draft 跳过布尔、3MF 导出失败）
- [ ] 5.4 测试 `route_after_confirm` 返回 `"organic"` 路由
- [ ] 5.5 测试 `finalize_node` organic 模式的 result 组装
- [ ] 5.6 测试 organic confirm 合并语义：通过 `confirmed_spec` 编辑 prompt_en/bounding_box/quality_mode/provider 后，验证 state 正确更新且 suggested_bounding_box 不被覆盖
- [ ] 5.7 迁移或删除 `tests/test_organic_api.py`：该文件硬依赖 `/api/v1/organic*` 端点，需更新为基于 `/api/v1/jobs` 的 organic 测试或删除冗余用例

## 6. 后端清理 `[backend]`

依赖：3, 5

- [ ] 6.1 迁移 `/api/v1/organic/providers` 端点到 `/api/v1/jobs/organic-providers`，供前端获取可用 provider 列表
- [ ] 6.2 迁移 `/api/v1/organic/upload` 端点到 `/api/v1/jobs/upload-reference`（参考图上传，MIME 白名单 png/jpeg/webp），与图纸上传端点区分
- [ ] 6.3 删除 `backend/api/v1/organic.py`（整个文件）
- [ ] 6.4 从 `backend/api/v1/router.py` 中移除 organic_router 的挂载（注意：挂载点在 router.py 而非 main.py）
- [ ] 6.5 验证 `/api/v1/organic` 端点已不可访问（返回 404）

## 7. 前端改造 `[frontend]`

依赖：3

- [ ] 7.1 修改 `OrganicWorkflow.tsx`：`useOrganicWorkflow` hook 改为调用 `POST /api/v1/jobs`（input_type=organic），SSE 事件监听从 `event: "organic"` 改为监听 `job.*` 事件
- [ ] 7.2 新增 organic spec 确认界面：展示 prompt_en、shape_category、bounding_box、engineering_cuts、quality_mode、provider，用户可编辑后点击确认调用 `POST /api/v1/jobs/{id}/confirm`
- [ ] 7.3 适配后处理子步骤 SSE 事件：事件名从 `post_processing` 改为 `job.post_processing`，保持 step/step_status 数据结构不变
- [ ] 7.4 适配 completed 事件：从 `job.completed` payload 中提取 organic_result（model_url、stl_url、threemf_url、mesh_stats、warnings、printability）
- [ ] 7.5 验证 TypeScript 编译零错误：`npx tsc --noEmit && npm run lint`

## 8. 集成验证 `[backend]` `[frontend]` `[test]`

依赖：5, 6, 7

- [ ] 8.1 运行全量后端测试：`uv run pytest tests/ -v` 全部通过
- [ ] 8.2 端到端冒烟测试：text/drawing/organic 三种 input_type 均通过 `/api/v1/jobs` 完成全流程
- [ ] 8.3 验证 HITL 中断/恢复：organic 模式下 spec 确认 → 恢复生成 → 完成
- [ ] 8.4 验证精密建模回归：text 和 drawing 管道功能不受 organic 迁移影响
