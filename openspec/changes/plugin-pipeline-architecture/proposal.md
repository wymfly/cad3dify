## Why

当前 LangGraph 管线是硬编码拓扑——添加一个新节点需要改 builder.py、routing.py、state.py 三处，精密路径和有机路径的后处理逻辑各自独立（`postprocess_organic_node` 350 行巨型函数 vs 精密路径 3 个独立节点），导致新增共享阶段（摆放寻优、切片、晶格填充）必须两边都改。`pipeline_config` 虽然有完整的预设/tooltip 设计但在图执行中完全未使用。随着端到端 3D 打印管线的推进（Gemini 节点分析报告识别了 9 个节点），架构必须支撑频繁的节点增删和精细化配置。

## What Changes

- **新增 NodeRegistry + `@register_node` 装饰器**：节点通过声明式元数据（requires/produces/strategies/config_model）自注册，无需手写 builder 拓扑
- **新增 DependencyResolver**：基于 requires/produces 的 DAG 自动拓扑排序，支持 AND/OR 依赖语法，冲突检测
- **BREAKING** 新增 `PipelineState` 替代 `CadJobState`：用 `assets: dict` + `data: dict` 替代 25+ 个散装字段
- **新增 NodeContext**：LangGraph State 的视图层，节点只通过 `get_asset()`/`put_asset()`/`get_data()`/`put_data()` 交互
- **新增 NodeStrategy 接口**：每个节点支持多种实现策略（算法 vs AI 模型），通过配置选择
- **BREAKING** 拆分 `postprocess_organic_node` 为 `mesh_repair` + `mesh_scale` + `boolean_cuts` + `export_formats` 四个独立节点
- **重写 PipelineBuilder**：从 ResolvedPipeline 动态生成 LangGraph StateGraph，替代当前手写拓扑
- **新增管线配置 API**：`GET /pipeline/nodes`、`POST /pipeline/validate`、`GET /pipeline/presets`
- **新增前端管线配置 UI**：可视化 DAG 编辑器 + 节点详情面板 + 实时校验 + 运行时监控

## Capabilities

### New Capabilities

- `node-registry`: 节点声明、注册、发现机制（NodeDescriptor + NodeRegistry + @register_node + discover_nodes）
- `dependency-resolver`: 基于 requires/produces 的 DAG 拓扑排序、依赖校验、冲突检测
- `pipeline-state`: 新的 PipelineState 数据模型（assets/data/node_trace）+ NodeContext 视图层 + AssetRegistry
- `node-strategy`: 多策略接口（NodeStrategy ABC）+ 策略注册 + 可用性检测 + 配置分发
- `pipeline-builder`: 从 ResolvedPipeline 动态编译 LangGraph StateGraph（替代手写 builder）
- `pipeline-config-api`: 管线元数据 API（节点列表、校验、预设）
- `pipeline-config-ui`: 前端可视化 DAG 管线编辑器 + 节点配置面板 + 运行时监控

### Modified Capabilities

- `langgraph-job-orchestration`: 图的构建方式从手写拓扑变为动态生成；State 从 CadJobState 变为 PipelineState
- `hitl-confirmation`: confirm_with_user 节点迁移为 `supports_hitl=True` 声明式标记
- `graph-event-streaming`: SSE 事件机制不变，但 node.completed 事件中增加 node_trace 数据

## Impact

- **后端核心重构**: `backend/graph/` 目录大部分文件重写或新增（builder.py, state.py, 新增 registry.py / resolver.py / context.py / descriptor.py 等）
- **节点文件拆分**: `nodes/organic.py` 的 `postprocess_organic_node` 拆为 4 个独立文件
- **所有现有节点迁移**: 每个节点需改为 `@register_node` + `NodeContext` 签名
- **API 层**: 新增 3 个端点，`POST /jobs` 的 pipeline_config 格式变更（提供兼容层）
- **前端**: 新增 PipelineConfigurator 组件（DAG 编辑器 + 节点面板），改造 PrecisionWorkbench 集成
- **测试**: 所有 graph 相关测试需重写，新增 registry / resolver / builder 单元测试
- **依赖**: 无新增外部依赖（全部基于现有 LangGraph + Pydantic）
