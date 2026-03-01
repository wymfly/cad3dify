## Context

精密建模管道（text/drawing）已通过 LangGraph StateGraph 管理 Job 生命周期，使用 `CadJobState` TypedDict、HITL `interrupt_before`、`astream_events` SSE 事件流。创意雕塑（organic）管道仍使用独立的 FastAPI 异步生成器编排（`backend/api/v1/organic.py`），拥有独立的 `OrganicJobModel` 数据表和 `OrganicJob` 状态机。

详细设计见 brainstorming 产出：`docs/plans/2026-03-01-organic-langgraph-migration-design.md`。

## Goals / Non-Goals

**Goals:**
- 将 organic 管道嵌入现有 CadJobState 图，作为第三条路径（与 text/drawing 并列）
- 统一前端 API 调用（`/api/v1/jobs` input_type=organic），删除 `/api/v1/organic` 端点
- 为 organic 引入 HITL 参数确认流程
- SSE 事件统一为 `job.*` 命名空间
- DB 统一到 JobModel 表

**Non-Goals:**
- 不改变 MeshProvider（Tripo3D / Hunyuan3D）的内部实现
- 不改变 MeshPostProcessor 的处理逻辑
- 不改变 OrganicSpecBuilder 的 LLM 调用逻辑
- 不迁移旧的 organic job 历史数据（OrganicJobModel 保留只读）

## Decisions

### D1: 图内编排 vs 子图封装 → 图内编排

organic 作为 CadJobState 图的第三条路径，共用 `create_job`、`confirm_with_user`、`finalize` 节点。

**替代方案**: 子图封装（独立 OrganicState + SubGraph）。否决原因：`astream_events` 嵌套复杂、HITL 中断跨子图传播困难、状态映射层增加不必要复杂度。

### D2: 后处理拆分粒度 → 单节点内循环

5 个后处理子步骤（load/repair/scale/boolean/validate）+ 导出 + 可打印性检查合并为 `postprocess_organic_node` 一个节点。通过 `dispatch_custom_event` 循环发送子步骤 SSE 事件。

**替代方案**: 每个子步骤一个节点（7 个节点）。否决原因：子步骤间无分支逻辑，拆分只增加图复杂度和 checkpoint 开销。

### D3: organic 端点迁移策略 → 迁移到 jobs router 后删除 organic.py

`/api/v1/organic` 整体删除。在删除前迁移两个复用端点：
- `/api/v1/organic/providers` → `/api/v1/jobs/organic-providers`（provider 状态查询）
- `/api/v1/organic/upload` → `/api/v1/jobs/upload-reference`（参考图上传，MIME 白名单 png/jpeg/webp，仅返回 file_id，不触发图执行）

### D4: CadJobState 扩展策略 → 直接扩展 TypedDict

新增 8 个 organic 字段到 `CadJobState`。`total=False` 确保 text/drawing 路径不受影响（organic 字段默认 None）。

### D5: finalize_node 分支 → 按 input_type 写入 result

`finalize_node` 检查 `input_type`：organic 时从 `organic_result` 字段组装 `result` JSON（含 model_url、stl_url、threemf_url、mesh_stats）；text/drawing 保持现有逻辑。

### D6: Organic HITL 确认参数传递 → 使用 confirmed_spec 字段

Organic 确认参数（prompt_en, provider, quality_mode, bounding_box）为字符串/混合类型，不能使用 `confirmed_params: dict[str, float]`（会破坏 text/drawing 的 Pydantic 类型强转）。改用 `ConfirmRequest` 已有的 `confirmed_spec: dict[str, Any]` 字段传递。`confirm_job_endpoint` 根据 `input_type` 分流：text/drawing 读 `confirmed_params`，organic 读 `confirmed_spec`。

## Risks / Trade-offs

- **[CadJobState 膨胀]** → 新增 ~8 字段可控；若未来增加更多输入类型，可考虑迁移到嵌套 dict。当前阶段不需要。
- **[前端破坏性变更]** → `/api/v1/organic` 删除后前端必须同步更新。通过同一 PR 后端 + 前端一起交付来缓解。
- **[OrganicJobModel 数据迁移]** → 旧数据保留在原表只读查询，不做数据迁移。历史 organic job 不出现在统一 Job 列表中。可接受。
- **[生成阶段 SSE 超时]** → MeshProvider 可能耗时 3-5 分钟。通过 `on_progress` 回调每 15-30s dispatch keepalive 事件来防止 SSE 连接断开。Provider 内部自带轮询超时。
- **[后处理阻塞事件循环]** → CPU-bound 后处理操作（pymeshlab/trimesh/manifold3d）通过 `asyncio.to_thread` 包装，避免阻塞 async 事件循环。
