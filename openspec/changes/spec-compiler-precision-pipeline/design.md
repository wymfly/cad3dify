## Context

精密路径（text → STEP, drawing → STEP）的代码生成逻辑目前散布在三处：

1. `vision_cad_pipeline.py::_match_template()` — 硬编码关键字匹配模板
2. `vision_cad_pipeline.py::_run_template_generation()` — 模板渲染 + 代码执行，需要伪造 Job 对象
3. `generation.py::_run_generate_from_spec()` — 图纸路径走 V2 全管道

text-path 在模板 miss 时直接 `raise RuntimeError`，无 LLM fallback。`EngineeringStandards.recommend_params()` 已实现但未被任何节点调用。`recommendations` 字段在 Job 模型中已定义但始终为空。管道节点注册在 `builder.py` 中硬编码，无法动态插入后处理步骤。

## Goals / Non-Goals

**Goals:**

- 统一代码编译调度：SpecCompiler 封装「模板匹配 → 渲染 → 执行」和「LLM 代码生成 → 执行」两条路径
- text-path 模板 miss 时自动降级到 Coder LLM，不再 hard-fail
- 模板匹配从关键字匹配升级为 part_type 语义路由
- 在 analyze 阶段集成 EngineeringStandards 推荐，填充 recommendations
- 管道支持通过注册表插入后处理拦截器

**Non-Goals:**

- 不引入新的 LLM 模型或外部服务（复用已有 Qwen-Coder-Plus）
- 不改变前端 API 接口契约（recommendations 从空变有值是兼容变更）
- 不修改 drawing-path 的 V2 管道核心逻辑（ModelingStrategist + SmartRefiner）
- 不实现 DrawingSpec `overall_dimensions` 的键名规范化（推迟到 M4 随 DfAM 一起做，避免破坏现有 VL 模型输出格式）
- 不实现真正的运行时动态加载拦截器（先做注册表数据结构 + 构建时插入）

## Decisions

### D1: SpecCompiler 作为纯函数调度器，不持有状态

**选择**: SpecCompiler 是无状态函数集合（`compile_from_template` + `compile_from_llm`），不是单例/有状态类。

**备选方案**:
- (A) 有状态单例，缓存 TemplateEngine 实例 — 增加复杂度，TemplateEngine 初始化很快（YAML 文件几十个）
- (B) 抽象 Strategy 模式 — 过度设计，当前只有两条路径

**理由**: 节点函数已是无状态的，SpecCompiler 保持同样模式。TemplateEngine 在 `from_directory()` 中已有缓存空间，不需要在调度层再缓存。

### D2: LLM fallback 复用现有 V2 管道的 CodeGeneratorChain

**选择**: 模板 miss 时调用 `backend.pipeline.pipeline.generate_step_from_text()`，复用 V2 管道中的 CodeGeneratorChain + SafeExecutor。

**备选方案**:
- (A) 重新实现一个轻量 LLM → CadQuery 生成器 — 重复工作
- (B) 调用外部 API（如 OpenAI Codex）— 引入新依赖

**理由**: V2 管道的 `CodeGeneratorChain` 已经过验证（包含 few-shot 示例、策略选择、SmartRefiner 迭代），直接复用是最低风险方案。fallback 路径与 drawing-path 共享相同的后端逻辑。

### D3: 模板路由使用 part_type + 评分排序

**选择**: 用 `TemplateEngine.find_matches(part_type)` 获取候选列表，按参数覆盖率排序（用户已知参数与模板参数的匹配度）。

**备选方案**:
- (A) LLM 语义匹配 — 延迟高、成本高，不适合热路径
- (B) 保持关键字匹配 — 现状问题明显（"生成一个圆柱体"匹配不到 `cylinder_simple`）

**理由**: part_type 由 IntentParser 从 LLM 提取，可靠度高。评分排序确保参数匹配度最高的模板优先。

### D4: InterceptorRegistry 使用构建时注入，非运行时热插拔

**选择**: 拦截器在 `_build_workflow()` 时通过注册表查表插入节点和边，不支持运行时动态修改图拓扑。

**备选方案**:
- (A) 运行时动态插入 — LangGraph StateGraph 编译后不可修改
- (B) 中间件模式 — 不适合 DAG 图结构

**理由**: LangGraph 的 `StateGraph.compile()` 是一次性的，编译后图拓扑不可变。注册表在构建时注入是唯一可行方案。

### D5: 后加工推荐在 postprocess 阶段生成

**选择**: `check_printability_node` 执行后，在同一节点中调用推荐引擎生成建议，写入 state.recommendations。

**备选方案**:
- (A) 独立 recommendations 节点 — 增加图复杂度
- (B) 在 finalize 阶段生成 — 来不及在 SSE 中推送给前端

**理由**: 推荐基于可打印性分析结果，在 printability 检查完成后立即生成最合理。不增加额外节点保持图拓扑简洁。

## Risks / Trade-offs

- **[Risk] LLM fallback 延迟**: text-path 走 LLM 比模板慢 10-30x → **Mitigation**: SSE 事件明确告知用户正在使用 LLM 生成（非模板快速路径），前端显示预计等待时间
- **[Risk] LLM 生成代码质量不稳定**: V2 管道仍依赖 SmartRefiner 迭代修复 → **Mitigation**: 保持 SmartRefiner 3 轮迭代机制，加上 PrintabilityChecker 兜底
- **[Risk] InterceptorRegistry 过早抽象**: 当前只有 Watermark 一个潜在拦截器 → **Mitigation**: 最小实现（列表 + 插入位置），不设计插件 API
- **[Trade-off] SpecCompiler 与现有 pipeline.py 的职责重叠**: SpecCompiler 封装了部分 pipeline.py 的逻辑 → **Mitigation**: SpecCompiler 调用 pipeline.py 函数而非复制代码，保持单一职责
