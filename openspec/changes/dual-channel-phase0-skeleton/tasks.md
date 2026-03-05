## 1. 策略派发扩展

- [ ] 1.1 `NodeDescriptor` 新增 `fallback_chain: list[str]` 字段，默认空列表
- [ ] 1.2 `@register_node` 新增 `fallback_chain` 参数，注册时校验所有 name 存在于 `strategies`
- [ ] 1.3 `NodeContext.get_strategy()` 扩展：识别 `strategy="auto"` 时遍历 `fallback_chain`，返回首个 `check_available()=True` 的策略实例（纯选择，不调用 `execute()`）；`check_available()=False` 时记录原因为 `"unavailable (check returned False)"`
- [ ] 1.4 `NodeContext` 新增 `execute_with_fallback()` 实例方法（**无参数**，通过 `self` 访问策略和配置）：auto 模式下**独立遍历** `fallback_chain`（不调用 get_strategy），对每个策略执行 `check_available()` + `execute()`，首个成功即返回；`execute()` 抛异常时记录异常消息后继续下一个；非 auto 模式直接调用 `get_strategy().execute(self)`
- [ ] 1.5 fallback trace 信息写入 `NodeContext` 内部状态（`_fallback_trace`），由 `_wrap_node()` 在构造 trace entry 时**合并**（而非独立追加），确保每个节点在 `node_trace` 中只有一条完整记录
- [ ] 1.6 为策略派发扩展编写单元测试：auto 选择 / auto execute fallback / auto 全部失败（含失败原因列表）/ 无 fallback_chain 报错 / 显式选择不受影响 / execute_with_fallback 非 auto 模式 / trace 合并验证

## 2. NeuralStrategy 基类与配置

- [ ] 2.1 `NodeStrategy` 基类新增 `__init__(self, config=None)` 默认实现（预防子类不接受 config 导致 TypeError）
- [ ] 2.2 创建 `backend/graph/strategies/__init__.py` 和 `backend/graph/strategies/neural.py`
- [ ] 2.3 实现 `NeuralStrategy(NodeStrategy)` 基类：构造函数调用 `super().__init__(config)`，重写 `check_available()` 加入 HTTP 健康检查（GET {endpoint}/health），sync HTTP + 5s 超时
- [ ] 2.4 健康检查缓存实现为**类级/模块级**（以 `(endpoint, health_check_path)` 为 key），使用可注入的 `_clock` 函数（默认 `time.monotonic`）以支持测试 mock TTL
- [ ] 2.5 实现 `NeuralStrategyConfig(BaseNodeConfig)` Pydantic 模型：`neural_enabled=False`, `neural_endpoint=None`, `neural_timeout=60`, `health_check_path="/health"`
- [ ] 2.6 实现三态逻辑：disabled（未配置或 `neural_enabled=False`）→ False，available（健康检查通过）→ True，degraded（健康检查失败）→ False
- [ ] 2.7 修改 `NodeContext.get_strategy()` 实例化调用：从 `strategies[name]()` 改为 `strategies[name](config=self.config)`
- [ ] 2.8 为 NeuralStrategy 编写单元测试：mock HTTP 健康检查的三态场景 + 缓存 TTL 测试（通过 mock `_clock`）+ 构造函数注入验证 + 不同 endpoint 缓存隔离

## 3. AssetStore 持久化层

- [ ] 3.1 创建 `backend/graph/asset_store.py`，定义 `AssetStore` Protocol（save → opaque URI string, load → bytes；文档注明 URI 仅由同一 store 实例产生和消费）
- [ ] 3.2 实现 `LocalAssetStore`：基于 pathlib，workspace 来源优先级为 `显式参数 > CADPILOT_WORKSPACE 环境变量 > cwd`，文件存储在 `{workspace}/jobs/{job_id}/{name}.{fmt}`，同名文件覆盖写入
- [ ] 3.3 `LocalAssetStore.save()/load()` 中添加路径规范化（`resolve()`）+ workspace 边界检查，防止路径遍历攻击
- [ ] 3.4 `NodeContext` 新增可选 `asset_store: AssetStore | None` 字段 + `save_asset(name, data, fmt, metadata)` 方法（调用 AssetStore.save + put_asset，返回 URI）
- [ ] 3.5 `NodeContext.from_state()` 通过 `pipeline_config` 初始化 `AssetStore`（默认 `LocalAssetStore`）
- [ ] 3.6 为 AssetStore 编写单元测试：save/load 正常路径 + 不存在 URI 报错 + 目录自动创建 + 覆盖写入 + 环境变量 workspace + 路径遍历拒绝 + NodeContext 集成（save_asset 返回 URI + put_asset 注册元数据）

## 4. 拦截器迁移

- [ ] 4.1 在 `PipelineBuilder.build()` 中实现拦截器显式声明插入：`_add_routing_edges()` 之后查询 `InterceptorRegistry`，按注册的 `after="convert_preview"` 插入点直接添加拦截链的边（不依赖"查找现有边"），如 DependencyResolver 生成了 convert_preview→check_printability 直连边则移除
- [ ] 4.2 拦截器节点注册时明确 `non_fatal` 标记策略（默认 True，与 legacy builder 行为一致）
- [ ] 4.3 编写拦截器迁移测试：注册 mock 拦截器 → 验证新 builder 生成的图包含拦截节点 → 执行顺序正确 → 拦截器失败时行为符合 non_fatal 预期
- [ ] 4.4 运行现有测试套件 `USE_NEW_BUILDER=1`，确认全部通过

## 5. Builder 统一

- [ ] 5.1 `builder.py` 核心代码移动到 `builder_legacy.py`
- [ ] 5.2 `builder.py` 改为 re-export wrapper + `@deprecated` 标记 + deprecation warning（保持所有现有 import 路径不断裂）
- [ ] 5.3 更新 `tests/` 中直接 import `builder` 的路径（逐个检查，确保 import 稳定）
- [ ] 5.4 `__init__.py` 中 `USE_NEW_BUILDER` 默认值改造：`os.environ.get("USE_NEW_BUILDER", "1") == "1"`（当前是 `os.environ.get("USE_NEW_BUILDER") == "1"`，无环境变量时返回 None 走 legacy 分支）
- [ ] 5.5 运行完整测试套件（`USE_NEW_BUILDER=1` 和 `USE_NEW_BUILDER=0`），确认双模式均通过；**显式验证** legacy 节点（如 `analyze_intent_node`）在新 builder 的 `PipelineState` 下正常工作

## 6. 验证与集成

- [ ] 6.1 在 `tests/` 目录下创建验证用 demo 节点 `_test_dual_channel`（不注册到生产管线）：含 algorithm + mock_neural 双策略 + fallback_chain
- [ ] 6.2 编写端到端测试：demo 节点在 auto 模式下 algorithm 成功 → 不 fallback；algorithm 失败 → fallback 到 mock_neural（使用 `execute_with_fallback()`）
- [ ] 6.3 编写端到端测试：demo 节点 neural_enabled=False 时 auto 模式只使用 algorithm
- [ ] 6.4 编写端到端测试：organic 路径在新 builder (`USE_NEW_BUILDER=1`) 下完整流程正确运行
- [ ] 6.5 运行 `uv run pytest tests/ -v` 全量测试，确认零 failure
- [ ] 6.6 运行 `cd frontend && npx tsc --noEmit` 确认前端无类型错误（虽然本提案不改前端，作为回归检查）
