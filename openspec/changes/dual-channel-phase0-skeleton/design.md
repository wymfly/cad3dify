## Context

CADPilot 的 LangGraph 管线已有完整的策略机制骨架：`NodeDescriptor.strategies` 注册策略类、`NodeContext.get_strategy()` 实例化策略、`BaseNodeConfig.strategy` 让用户选择。但当前仅支持静态单策略选择，无法实现「算法优先 → Neural fallback」的 auto 模式。

后续 9 个后半段节点（mesh_healer、boolean_assemble、slice_to_gcode 等）均需要双通道支持。此外，`builder_new.py`（基于 `DependencyResolver` 的动态图构建）缺少拦截器支持，无法安全替换 legacy builder 成为默认。

详细设计见：`docs/plans/end-to-end-architecture/2026-03-02-dual-channel-pipeline-design.md` §零（代码现状基线）+ §一（架构层）。

**现有代码关键接入点**：

| 文件 | 现有机制 | 本次扩展 |
|------|---------|---------|
| `descriptor.py` | `strategies: dict[str, type[NodeStrategy]]`, `default_strategy` | 新增 `fallback_chain: list[str]` |
| `context.py` | `get_strategy()` 静态查找 + 实例化 | 扩展 auto fallback 逻辑 |
| `configs/base.py` | `BaseNodeConfig(enabled, strategy)` | 新增 `NeuralStrategyConfig` 子类 |
| `descriptor.py` | `NodeStrategy` ABC | 新增 `NeuralStrategy` 子类 |
| `context.py` | `AssetRegistry` / `AssetEntry` | 新增 `AssetStore` Protocol 与之集成 |
| `builder_new.py` | `PipelineBuilder` 无拦截器 | 移植 `InterceptorRegistry.apply()` |

## Goals / Non-Goals

**Goals:**

- 扩展策略机制支持 `auto` 模式：按 `fallback_chain` 顺序尝试策略，首个成功即返回
- 提供 `NeuralStrategy` 基类，内置 HTTP 健康检查，实现三态设计（disabled/available/degraded）
- 新增 `AssetStore` Protocol + `LocalAssetStore`，与现有 `AssetRegistry` 集成，为后续 MinIO 升级预留
- 新 builder 补齐拦截器支持后，安全切换为默认
- 通过一个验证用 demo 节点证明双通道 auto fallback 端到端工作

**Non-Goals:**

- 不实现任何具体业务节点（mesh_healer 等归后续提案）
- 不部署或集成任何真实 Neural 模型服务
- 不修改前端 UI
- 不实现 MinioAssetStore（仅预留接口）
- 不修改现有 front-half 节点（analyze_intent、generate_step_text 等）

## Decisions

### D1: auto fallback 分两层实现（选择 + 执行）

**选择**：将 auto fallback 拆成两个清晰的职责：

1. `get_strategy()` — **选择层**：`strategy="auto"` 时，遍历 `fallback_chain`，返回第一个 `check_available()=True` 的策略实例。不调用 `execute()`。仅供查询/日志/UI 展示使用。
2. `execute_with_fallback()` — **执行层**：新增 `NodeContext` 实例方法（无参，通过 `self` 访问策略和配置）。`strategy="auto"` 时，**内部独立遍历** `fallback_chain`（不调用 `get_strategy()`），对每个策略执行 `check_available()` + `execute()`。首个 `execute()` 成功即返回结果。如果 `execute()` 抛异常，记录异常信息后继续尝试下一个。非 auto 模式直接调用 `get_strategy().execute(self)`。

**关键设计点**：`execute_with_fallback()` 独立遍历而非复用 `get_strategy()`，避免 `get_strategy()` 只能返回"第一个可用策略"导致无法继续下一个的问题。两者遍历 `fallback_chain` 的逻辑相同但独立，`get_strategy()` 在 auto 模式下的返回值仅表示"会优先尝试的策略"，不影响 `execute_with_fallback()` 的完整 fallback 链。

节点函数调用 `result = await ctx.execute_with_fallback()` 替代原来的 `strategy = ctx.get_strategy(); result = await strategy.execute(ctx)` 两步调用。

**不可用原因记录**：`check_available()` 返回 `bool`，不改变此签名。在 auto 遍历中，`check_available()=False` 记录为 `"unavailable (check returned False)"`；`execute()` 抛异常时记录异常消息。所有尝试记录汇总后写入 `node_trace`。

**trace 注入点**：fallback 信息由 `execute_with_fallback()` 写入 `ctx._trace_entries`（通过 `ctx.add_trace()`）。`_wrap_node()` 的 trace 与 `ctx._trace_entries` **合并**而非独立追加，确保同一节点在 `node_trace` 中只有一条完整记录。

**备选 A**：在 `get_strategy()` 内部调用 `execute()` — 违反方法名语义（"获取" vs "执行"），被否决。

**备选 B**：在 `_wrap_node()` 中实现 fallback 循环 — 侵入 builder 层，节点失去策略控制权，被否决。

**备选 C**：`execute_with_fallback(ctx)` 带 ctx 参数 — 方法在 NodeContext 上，`self` 即是 `ctx`，额外参数是自引用，被否决。

**理由**：两层分离保持了 `get_strategy()` 的纯选择语义，`execute_with_fallback()` 明确表达"执行+fallback"意图。独立遍历保证了两者的职责清晰且不互相依赖。

### D2: NeuralStrategy 继承 NodeStrategy，健康检查集成到 check_available()

**选择**：`NeuralStrategy` 作为 `NodeStrategy` 子类，重写 `check_available()` 加入 HTTP 健康检查。

**备选**：独立 `ServiceDiscovery` 类管理所有 Neural endpoint。

**理由**：`NodeStrategy.check_available()` 已存在且语义匹配。Neural 策略自身最了解自己的健康状态，不需要全局 ServiceDiscovery 协调。每个 `NeuralStrategy` 实例持有自己的 endpoint config，通过构造函数注入。

### D3: NeuralStrategy 通过构造函数注入配置

**选择**：`NodeContext.get_strategy()` 在实例化策略时注入 config：`strategies[name](config=self.config)`。`NeuralStrategy.__init__(config)` 保存 config 引用，`check_available()` 通过 `self.config` 访问 endpoint 配置。**不改变 `NodeStrategy.check_available(self)` 的基类签名**——`NeuralStrategy` 重写时从 `self.config` 读取。

**备选 A**：改 `check_available(config)` 签名 — 破坏 Liskov 替换原则和现有调用方 `instance.check_available()`，被否决。

**备选 B**：通过环境变量传 endpoint — 不支持 per-node 不同 endpoint，被否决。

**理由**：构造函数注入是最安全的依赖传递方式，不改变 `check_available()` 的调用签名。`NodeContext.get_strategy()` 当前代码是 `strategies[name]()`（无参构造），改为 `strategies[name](config=self.config)` 即可。

**兼容性说明**：当前生产代码中**尚无任何 `NodeStrategy` 子类**（策略机制骨架已搭建但未被消费）。为预防未来子类不接受 config 参数导致 `TypeError`，`NodeStrategy` 基类新增 `__init__(self, config=None)` 默认实现。这是预防性措施，不是修复现有兼容性问题。

### D4: AssetStore 与 AssetRegistry 职责分离

**选择**：`AssetStore` 负责持久化（save 文件 → 返回 URI，load URI → 返回 bytes），`AssetRegistry` 负责元数据追踪（key/path/format/producer）。`NodeContext` 同时持有两者。

**备选**：合并为一个类。

**理由**：现有 `AssetRegistry` 已稳定运行，改动最小化。`AssetStore` 是纯 I/O 抽象，后续替换为 MinIO 只需换实现，不影响 AssetRegistry。

### D5: 拦截器迁移采用显式声明 + 后处理模式

**选择**：在 `PipelineBuilder.build()` 中，拦截器通过**显式声明插入点**（`after_node`/`before_node`）注入，而非通过"查找并删除现有边"。具体步骤：

1. `InterceptorRegistry.apply(workflow)` 注册拦截节点到 StateGraph
2. 拦截器插入点由 `InterceptorRegistry` 的注册信息声明（`after="convert_preview"`），`PipelineBuilder` 在 `_add_routing_edges()` 之后直接添加拦截链的边：`convert_preview` → interceptor1 → ... → `check_printability`
3. `_add_routing_edges()` 生成的 `convert_preview` 的后续边中，如果有 `check_printability` 的直连（取决于 `requires/produces` 匹配），则移除；如果没有直连（新 builder 的依赖解析可能不生成此边），则无需移除——拦截链本身就是连接两者的唯一路径

**关键约束**：新 builder 的 `DependencyResolver` 根据 `requires/produces` 生成边。`convert_preview` produces `["preview_glb"]`，`check_printability` requires `[["step_model", "watertight_mesh"]]`——两者之间**可能没有直连边**。因此拦截器插入**不能依赖"找到并删除现有边"的假设**，而是主动添加拦截链的边。当前仅支持 `after="convert_preview"` 一个插入点（与 legacy builder 一致）。

**备选 A**：通过"查找边+删除边+插入链"实现 — 新 builder 的依赖解析可能不产生预期的边，假设不成立，被否决。

**备选 B**：将拦截器作为 `requires/produces` 依赖注册到 `NodeRegistry` — 增加 `DependencyResolver` 复杂度，被否决。

**理由**：显式声明插入点最为稳健，不依赖 DependencyResolver 的边生成结果，也不侵入拓扑排序逻辑。

### D6: Builder 切换采用渐进式

**选择**：Phase 0 完成后将 `USE_NEW_BUILDER` 默认值改为 `1`，但保留环境变量开关。legacy builder 标记 `@deprecated` 但不删除。

**备选**：直接删除 legacy builder。

**理由**：渐进式切换允许回滚。legacy builder 在新 builder 被充分验证前作为安全网。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|---------|
| auto fallback 掩盖算法策略的真实错误 | fallback 时记录 warning 日志 + 在 `node_trace` 中标记 `fallback_triggered: true` + 记录每个策略的失败原因 |
| NeuralStrategy 健康检查引入网络延迟 | 健康检查结果缓存 30s（**类级/模块级缓存**，以 `(endpoint, health_check_path)` 为 key，避免实例级缓存因每次 new 而失效），sync HTTP + 短超时(5s) |
| 拦截器迁移可能遗漏 edge case | 运行完整现有测试套件 + 新增拦截器专项测试，USE_NEW_BUILDER=1 和 =0 都跑；拦截器节点需明确 `non_fatal` 标记策略 |
| Builder 切换导致有机体管线回归 | 切换前在 CI 中运行 organic 完整流程 E2E 测试 |
| AssetStore 抽象过早 | LocalAssetStore 实现极简（wrapper around pathlib），不引入额外复杂度 |
| AssetStore 路径遍历风险 | `LocalAssetStore.save()/load()` 中对 `job_id`/`name` 做路径规范化（`resolve()`），验证结果在 workspace 边界内 |
| `default_strategy` 语义不一致 | `BaseNodeConfig.strategy` 默认 `"default"`，但无节点定义 `"default"` 策略 key；本 change 不修复，后续节点实现时统一（每个节点的 `strategies` 必须包含与 config 默认值匹配的 key） |
| `AssetStore` URI scheme 与实现耦合 | Protocol 规定 `save()` 返回的 URI 是 opaque string，`load()` 只接受同一 store 实例产生的 URI，不同实现间 URI 不可互换 |
