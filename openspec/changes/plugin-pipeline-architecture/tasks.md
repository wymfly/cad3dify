## 1. 核心数据模型

- [ ] 1.1 创建 `backend/graph/descriptor.py`：`NodeDescriptor` dataclass（name, display_name, requires, produces, input_types, config_model, strategies, default_strategy, is_entry, supports_hitl, non_fatal, description, estimated_duration, fn）+ `NodeResult` dataclass
- [ ] 1.2 创建 `backend/graph/descriptor.py`：`NodeStrategy` ABC（execute, check_available）
- [ ] 1.3 创建 `backend/graph/configs/base.py`：`BaseNodeConfig(BaseModel)` 含 `enabled: bool = True`、`strategy: str`
- [ ] 1.4 创建 `backend/graph/context.py`：`AssetEntry` dataclass + `AssetRegistry`（put, get, has, to_dict, from_dict）
- [ ] 1.5 创建 `backend/graph/context.py`：`NodeContext`（from_state, to_state_diff, get_asset, put_asset, has_asset, get_data, put_data, get_strategy, dispatch, dispatch_progress）
- [ ] 1.6 创建 `backend/graph/state.py`：`PipelineState` TypedDict（job_id, input_type, assets, data, pipeline_config, status, error, failure_reason, node_trace）替代 `CadJobState`
- [ ] 1.7 编写 `tests/test_descriptor.py`：NodeDescriptor 构造、默认值、NodeStrategy ABC
- [ ] 1.8 编写 `tests/test_context.py`：AssetRegistry round-trip、NodeContext.from_state / to_state_diff、get_strategy 分发

## 2. 注册表与发现

- [ ] 2.1 创建 `backend/graph/registry.py`：`NodeRegistry` 类（register, get, all, find_producers, find_consumers）+ 模块级 `registry` 单例
- [ ] 2.2 创建 `backend/graph/registry.py`：`@register_node` 装饰器，解析参数构造 `NodeDescriptor` 并调用 `registry.register()`
- [ ] 2.3 创建 `backend/graph/discovery.py`：`discover_nodes()` 扫描 `backend/graph/nodes/` 下所有 `.py` 文件并 import
- [ ] 2.4 编写 `tests/test_registry.py`：注册、重名拒绝、find_producers/find_consumers 查询、discover_nodes 集成

## 3. 依赖解析器

- [ ] 3.1 创建 `backend/graph/resolver.py`：`ResolvedPipeline` dataclass（ordered_nodes, edges, asset_producers, interrupt_before, validate）
- [ ] 3.2 创建 `backend/graph/resolver.py`：`DependencyResolver.resolve()` — 过滤（enabled + input_type）→ 依赖检查 → 冲突检测 → Kahn 拓扑排序
- [ ] 3.3 实现 OR 依赖解析：`requires=[["a", "b"]]` 语法，OR 组只需一个 producer 满足
- [ ] 3.4 实现依赖不满足报错：错误信息包含缺失 asset、可能的 producer 节点名
- [ ] 3.5 实现冲突检测：同一 asset 多 producer（input_type 过滤后）→ 报错
- [ ] 3.6 编写 `tests/test_resolver.py`：覆盖 text/drawing/organic 三条路径解析、OR 依赖满足/不满足、冲突检测、HITL 收集、环检测

## 4. PipelineBuilder（动态图生成）

- [ ] 4.1 重写 `backend/graph/builder.py`：`PipelineBuilder.build(resolved)` → 注册节点 + 连接边
- [ ] 4.2 实现 `_wrap_node(desc)`：构造 NodeContext → 调用原函数 → 返回 state diff + @timed_node 包装
- [ ] 4.3 实现条件边生成：input_type 路由（create_job 后分叉）、confirm 后分叉
- [ ] 4.4 重写 `get_compiled_graph(pipeline_config, input_type)`：解析配置 → resolve → build → compile(checkpointer, interrupt_before)
- [ ] 4.5 编写 `tests/test_builder.py`：编译成功、节点数匹配、边拓扑正确、HITL interrupt 正确

## 5. 预设与配置

- [ ] 5.1 创建 `backend/graph/presets.py`：`PIPELINE_PRESETS`（fast, balanced, full_print）+ `parse_pipeline_config()` 函数
- [ ] 5.2 创建 `backend/graph/compat.py`：旧 `PipelineConfig` / `CadJobState` → 新格式迁移函数
- [ ] 5.3 编写 `tests/test_presets.py`：预设解析、旧格式兼容转换

## 6. 现有节点迁移 — 前半程

- [ ] 6.1 迁移 `create_job`：重写为 `@register_node(is_entry=True, produces=[...])`，使用 NodeContext
- [ ] 6.2 迁移 `analyze_intent`：`@register_node(requires=["text_input"], produces=["intent_spec"])`，原 pipeline_config 的 ocr_assist/two_pass/multi_vote 变为策略
- [ ] 6.3 迁移 `analyze_vision`：`@register_node(requires=["drawing_input"], produces=["drawing_spec"])`
- [ ] 6.4 迁移 `analyze_organic`：`@register_node(requires=["organic_input"], produces=["organic_spec"])`
- [ ] 6.5 迁移 `confirm_with_user`：`@register_node(supports_hitl=True, requires=[[...OR...]], produces=["confirmed_params"])`
- [ ] 6.6 迁移 `generate_step_text`：策略 template_first / llm_only，从 SpecCompiler 提取
- [ ] 6.7 迁移 `generate_step_drawing`：策略 v2_pipeline / llm_direct
- [ ] 6.8 迁移 `generate_organic_mesh`：策略 tripo3d / hunyuan3d / auto
- [ ] 6.9 运行全量测试，修复迁移引起的回归

## 7. 现有节点迁移 — 后半程 + postprocess_organic 拆分

- [ ] 7.1 迁移 `convert_preview`：`@register_node(requires=[["step_model"]], produces=["preview_glb"], non_fatal=True)`
- [ ] 7.2 拆分创建 `mesh_repair`：从 MeshPostProcessor 提取 load+repair 逻辑，策略 pymeshlab / trimesh_voxel / meshlib
- [ ] 7.3 拆分创建 `mesh_scale`：从 MeshPostProcessor 提取 scale 逻辑，requires=["watertight_mesh"]
- [ ] 7.4 拆分创建 `boolean_cuts`：从 MeshPostProcessor 提取 boolean 逻辑，策略 manifold3d
- [ ] 7.5 拆分创建 `export_formats`：从 postprocess_organic 提取 GLB/STL/3MF 导出，requires OR 多种 mesh
- [ ] 7.6 迁移 `check_printability`：OR 依赖 `[["step_model", "watertight_mesh"]]`，精密+有机共享
- [ ] 7.7 迁移 `analyze_dfam`：OR 依赖，精密+有机共享
- [ ] 7.8 迁移 `finalize`：从 `state["assets"]` 收集所有产物写 DB，不再硬编码字段名
- [ ] 7.9 运行全量测试，验证精密 + 有机两条路径完整通过

## 8. 后端 API

- [ ] 8.1 新增 `GET /api/v1/pipeline/nodes`：返回所有注册节点描述符（含策略可用性、配置 JSON Schema）
- [ ] 8.2 新增 `POST /api/v1/pipeline/validate`：接受 input_type + config，运行 DependencyResolver，返回校验结果
- [ ] 8.3 新增 `GET /api/v1/pipeline/presets`：返回所有预设配置
- [ ] 8.4 改造 `POST /api/v1/jobs`：pipeline_config 新格式支持 + 旧格式兼容层
- [ ] 8.5 改造 `GET /api/v1/jobs/{id}`：response 增加 pipeline_topology、node_trace
- [ ] 8.6 编写 `tests/test_pipeline_api.py`：节点列表、校验（成功/失败/冲突）、预设、兼容性

## 9. 前端 — PipelineConfigurator 组件

- [ ] 9.1 创建 `PipelineConfigurator` 容器组件：布局（预设栏 + DAG 区 + 详情面板 + 状态栏）
- [ ] 9.2 实现 `PipelineDAG` 组件：纵向流程图渲染节点卡片 + 连线，基于 `/pipeline/nodes` 数据
- [ ] 9.3 实现节点卡片：显示名称、策略、enabled 开关、状态图标（配置模式/监控模式）
- [ ] 9.4 实现 `NodeDetailPanel` 组件：策略卡片选择器 + 动态参数表单（从 JSON Schema 生成） + 输入/输出 + 说明
- [ ] 9.5 实现预设选择栏：预设按钮组 + 修改后自动切 custom
- [ ] 9.6 实现依赖校验状态栏：调用 `/pipeline/validate`，显示✓/⚠/✗ + 节点数 + 预计耗时
- [ ] 9.7 实现运行时监控模式：复用 DAG 组件，根据 SSE node.started/completed/failed 事件更新节点状态
- [ ] 9.8 集成到 PrecisionWorkbench / OrganicWorkbench 的任务创建流程
- [ ] 9.9 `cd frontend && npx tsc --noEmit && npm run lint` 通过

## 10. 清理与验证

- [ ] 10.1 删除旧 `CadJobState`（确认无引用后）、旧 `routing.py`、旧 `interceptors.py`
- [ ] 10.2 删除旧 `postprocess_organic_node`（已拆分为 4 个独立节点）
- [ ] 10.3 删除旧 `PipelineConfig` 模型（确认兼容层工作正常后）
- [ ] 10.4 运行 `uv run pytest tests/ -v` 全量测试通过
- [ ] 10.5 运行 `cd frontend && npx tsc --noEmit` TypeScript 无错误
- [ ] 10.6 端到端验证：text/drawing/organic 三条路径完整执行 + SSE 事件 + DB 持久化
