## 1. CadJobState 扩展 + 路由更新 `[backend]`

- [ ] 1.1 在 `backend/graph/state.py` 中扩展 CadJobState：新增 `organic_spec`、`organic_provider`、`organic_quality_mode`、`organic_reference_image`、`raw_mesh_path`、`mesh_stats`、`organic_warnings`、`organic_result` 字段，更新 `STATE_TO_ORM_MAPPING`
- [ ] 1.2 在 `backend/graph/routing.py` 中修改 `route_after_confirm`：organic 不再返回 `"finalize"`，改为返回 `"organic"`
- [ ] 1.3 在 `backend/api/v1/jobs.py` 中扩展 `CreateJobRequest`：新增 `reference_image: str | None = None` 字段；`create_job_endpoint` 中将 organic 字段映射到初始 state（`organic_provider`、`organic_quality_mode`、`organic_reference_image`）

## 2. 后端节点实现 `[backend]`

依赖：1

- [ ] 2.1 创建 `backend/graph/nodes/organic.py`：实现 `analyze_organic_node`——调用 OrganicSpecBuilder.build()，60s 超时，成功后 dispatch `job.organic_spec_ready` 事件，设置 status=awaiting_confirmation
- [ ] 2.2 实现 `generate_organic_mesh_node`——创建 MeshProvider，读取 reference_image（如有），调用 provider.generate()，幂等检查，dispatch `job.generating` 事件
- [ ] 2.3 实现 `postprocess_organic_node`——顺序执行 load/repair/scale/boolean/validate/export/printability，每步 dispatch `job.post_processing` 事件，布尔失败优雅降级，导出 GLB/STL/3MF，运行可打印性检查

## 3. 图拓扑更新 `[backend]`

依赖：2

- [ ] 3.1 在 `backend/graph/builder.py` 中删除 `stub_organic` 节点，注册 `analyze_organic`、`generate_organic_mesh`、`postprocess_organic` 三个新节点
- [ ] 3.2 更新边定义：`create_job` → `analyze_organic`（organic 路由）、`confirm_with_user` → `generate_organic_mesh`（organic 路由）、`generate_organic_mesh` → `postprocess_organic`、`postprocess_organic` → `finalize`
- [ ] 3.3 从 `backend/graph/nodes/analysis.py` 中删除 `stub_organic_node` 函数及其 import

## 4. finalize_node 扩展 `[backend]`

依赖：1

- [ ] 4.1 修改 `backend/graph/nodes/lifecycle.py` 中 `finalize_node`：当 `input_type=organic` 时，从 `organic_result` 字段组装 `result` JSON（含 model_url、stl_url、threemf_url、mesh_stats），写入 DB Job 表

## 5. 单元测试 `[backend]` `[test]`

依赖：2, 3, 4

- [ ] 5.1 编写 `tests/test_organic_nodes.py`：mock OrganicSpecBuilder 测试 `analyze_organic_node`（成功、超时、fallback）
- [ ] 5.2 测试 `generate_organic_mesh_node`（成功、幂等跳过、Provider 失败、reference_image 加载）
- [ ] 5.3 测试 `postprocess_organic_node`（全流程成功、布尔失败降级、draft 跳过布尔、3MF 导出失败）
- [ ] 5.4 测试 `route_after_confirm` 返回 `"organic"` 路由
- [ ] 5.5 测试 `finalize_node` organic 模式的 result 组装

## 6. 后端清理 `[backend]`

依赖：3, 5

- [ ] 6.1 删除 `backend/api/v1/organic.py`（整个文件）
- [ ] 6.2 从 `backend/main.py` 中移除 organic_router 的挂载
- [ ] 6.3 验证 `/api/v1/organic` 端点已不可访问（返回 404）

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
