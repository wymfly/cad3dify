## 1. SpecCompiler 核心

- [ ] 1.1 创建 `backend/core/spec_compiler.py`：`CompileResult` 数据类 + `SpecCompiler` 类骨架（`compile()` 方法签名）
- [ ] 1.2 实现 `SpecCompiler.compile()` 模板路径：调用 `TemplateEngine.render()` + `SafeExecutor` 生成 STEP
- [ ] 1.3 实现 `SpecCompiler.compile()` LLM fallback 路径：调用 `generate_step_from_text()` 生成 STEP
- [ ] 1.4 实现模板路由评分：`_rank_templates(candidates, known_params)` 按参数覆盖率排序
- [ ] 1.5 编写 `tests/test_spec_compiler.py`：覆盖模板命中、模板 miss → LLM fallback、双失败、评分排序

## 2. generation 节点重构

- [ ] 2.1 重构 `generate_step_text_node`：替换 `_run_template_generation` 为 `SpecCompiler.compile()`
- [ ] 2.2 清理 `generation.py` 中遗留的 `_run_template_generation` 包装函数和 mock Job 对象
- [ ] 2.3 更新 `generate_step_text_node` 的 SSE 事件：区分 `stage="template"` 和 `stage="llm_fallback"`
- [ ] 2.4 编写/更新 `tests/test_graph_nodes_generation.py`：覆盖模板路径和 LLM fallback 路径

## 3. 模板语义路由

- [ ] 3.1 重构 `analyze_intent_node` 中的模板匹配：替换 `_match_template(text)` 为 `TemplateEngine.find_matches(part_type)` + `_rank_templates()`
- [ ] 3.2 集成 `EngineeringStandards.recommend_params()`：在 `analyze_intent_node` 中调用并写入 `state.recommendations`
- [ ] 3.3 在 `state.py` 中添加 `recommendations: list[dict] | None` 字段
- [ ] 3.4 更新 `job.intent_analyzed` SSE 事件 payload 包含 `recommendations`
- [ ] 3.5 编写 `tests/test_template_routing.py`：覆盖 part_type 路由、评分排序、无匹配回退

## 4. 后加工推荐引擎

- [ ] 4.1 创建 `backend/core/recommendation_engine.py`：基于 printability issues 生成推荐列表
- [ ] 4.2 在 `check_printability_node` 中调用推荐引擎，写入 `state.recommendations`（合并分析阶段的推荐）
- [ ] 4.3 在 `finalize_node` 中将 `recommendations` 写入 Job result JSON
- [ ] 4.4 更新 `job.printability_checked` SSE 事件 payload 包含 `recommendations`
- [ ] 4.5 编写 `tests/test_recommendation_engine.py`：覆盖 thin_wall、overhang、无 issue 三种场景

## 5. 拦截器注册表

- [ ] 5.1 创建 `backend/graph/interceptors.py`：`InterceptorRegistry` 类（`register()` + `apply()` 方法）
- [ ] 5.2 在 `_build_workflow()` 中调用 `InterceptorRegistry.apply(workflow)` 插入已注册节点
- [ ] 5.3 编写 `tests/test_interceptor_registry.py`：覆盖无拦截器、单拦截器、多拦截器链

## 6. 集成验证

- [ ] 6.1 运行全量 `uv run pytest tests/ -v` 确认所有测试通过
- [ ] 6.2 运行 `cd frontend && npx tsc --noEmit` 确认 TypeScript 无错误
- [ ] 6.3 删除 `vision_cad_pipeline.py` 中不再被引用的 `_match_template()` 和 `_run_template_generation()`（若已无调用方）
