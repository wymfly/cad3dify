## 1. LCEL Chain 基础设施

- [ ] 1.1 创建 `backend/graph/chains/__init__.py` 模块结构和 re-export
- [ ] 1.2 实现 `backend/graph/chains/fix_chain.py`: `def build_fix_chain() -> Runnable`（同步工厂） — 将 `SmartFixChain` 转为 LCEL Runnable（`prompt | llm.with_retry() | parser`），复用 `smart_refiner._parse_code()`
- [ ] 1.3 为 `build_fix_chain()` 编写测试：mock LLM 返回 Python 代码块 → 验证解析结果，mock 返回空文本 → 验证返回 None
- [ ] 1.4 实现 `backend/graph/chains/compare_chain.py`: `def build_compare_chain(structured=False) -> Runnable`（同步工厂） — 将 `SmartCompareChain` 转为 LCEL Runnable，含两张图的 `ImagePromptTemplate`，复用 `smart_refiner._extract_comparison()`；structured=True 模式使用 `parse_vl_feedback()` 判断 PASS（JSON `feedback.passed` 字段，非长度启发式）
- [ ] 1.5 为 `build_compare_chain()` 编写测试：mock VL 返回 "PASS" → 验证 result=None，mock 返回 "pass"（小写）→ 验证 result=None（大小写不敏感），mock 返回差异描述 → 验证 result=差异文本，验证 structured=True 使用 `parse_vl_feedback()` 且 JSON `{"verdict":"PASS","issues":[]}` → result=None
- [ ] 1.6 实现 `backend/graph/chains/code_gen_chain.py`: `def build_code_gen_chain() -> Runnable`（同步工厂） — 将 `CodeGeneratorChain` 转为 LCEL Runnable，复用 `code_generator._parse_code()`
- [ ] 1.7 为 `build_code_gen_chain()` 编写测试：mock LLM 返回带 \`\`\`python 包裹的代码 → 验证解析，验证 prompt 中包含 modeling_context 变量
- [ ] 1.8 实现 `backend/graph/chains/vision_chain.py`: `def build_vision_analysis_chain() -> Runnable`（同步工厂） — 将 `DrawingAnalyzerChain` 转为 LCEL Runnable，含 `ImagePromptTemplate`，复用 `drawing_analyzer._parse_drawing_spec()`
- [ ] 1.9 为 `build_vision_analysis_chain()` 编写测试：mock VL 返回含 DrawingSpec JSON 的文本 → 验证解析为 DrawingSpec 对象，mock 返回无效 JSON → 验证 result=None
- [ ] 1.10 为所有 4 个 chain 添加 prompt 等价性快照测试：构造相同输入，分别通过 LCEL chain 和旧 SequentialChain 格式化 prompt，断言 prompt 文本完全一致
- [ ] 1.11 运行全部 chain 测试并提交：`uv run pytest tests/test_lcel_chains.py -v`

## 2. Refiner 子图

- [ ] 2.1 定义 `RefinerState` TypedDict（含 `comparison_result`, `rendered_image_path`, `prev_score`, `prev_code`, `prev_step_path` 字段）和状态映射函数（`map_job_to_refiner` / `map_refiner_to_job`，含 `DrawingSpec` → dict 显式转换，`max_rounds` 从 `pipeline_config.max_refinements` 获取），放在 `backend/graph/subgraphs/refiner.py`
- [ ] 2.2 实现 `static_diagnose` 节点：从 `drawing_spec: dict` 还原 `DrawingSpec(**state["drawing_spec"])` 后调用 `validate_code_params()` + `validate_bounding_box()` + 可选 `compare_topology()`（通过 `config.get("configurable", {}).get("pipeline_config", PipelineConfig()).topology_check` 控制），结果写入 `static_notes`
- [ ] 2.3 实现 `render_for_compare` 节点：渲染 STEP → PNG（支持多视角降级到单视角，通过 `pipeline_config.multi_view_render` 控制），更新 `state["rendered_image_path"]`
- [ ] 2.4 实现 `vl_compare` 节点：调用 `build_compare_chain(structured=pipeline_config.structured_feedback)` 进行 VL 对比，将对比结果写入 `state["comparison_result"]`，解析 verdict（pass/fail），派发 `job.refining` SSE 事件
- [ ] 2.5 实现 `coder_fix` 节点：调用 `build_fix_chain()` 修复代码，合并 `state["comparison_result"]` + `static_notes` 作为 fix_instructions，派发 `job.refining` SSE 事件
- [ ] 2.6 实现 `re_execute` 节点：先快照当前 `code` → `prev_code`、`step_path` → `prev_step_path`，再递增 `round += 1`，然后沙箱执行修复后的代码（`SafeExecutor`），评分后集成 `RollbackTracker` 基于 `prev_score` 检测分数退化（退化时从 `prev_code`/`prev_step_path` 恢复），更新 `prev_score`
- [ ] 2.7 实现 `build_refiner_subgraph()`: 组装 `static_diagnose → render_for_compare → vl_compare → route_verdict → [pass: END, fail+round<max: coder_fix → re_execute → render_for_compare (循环), fail+round>=max: END]` 子图拓扑。注意循环中包含 re-render 步骤
- [ ] 2.8 为子图编写集成测试：mock 所有 LLM chain，验证 1 轮 PASS 退出、3 轮 max_rounds 退出、rollback 场景、`comparison_result` 在 coder_fix 中可用
- [ ] 2.9 运行 refiner 子图测试并提交：`uv run pytest tests/test_refiner_subgraph.py -v`

## 3. 节点层迁移——analyze_vision_node

- [ ] 3.1 重写 `analyze_vision_node`: 移除 `asyncio.to_thread(_run_analyze_vision)`，改为直接 `chain = build_vision_analysis_chain(); result = await asyncio.wait_for(chain.ainvoke({"image_type": image.type, "image_data": image.data}), timeout=60.0)`（显式 ImageData → flat dict 适配，替代旧 `prep_inputs()`；保留 60s 轻量节点超时保护）
- [ ] 3.2 在节点中内联 OCR fusion 调用（`fuse_ocr_with_spec()`），保持 graceful degradation
- [ ] 3.3 保留 `_cost_optimizer` 结果缓存逻辑（cache hit 时跳过 LLM）
- [ ] 3.4 更新 `tests/test_drawing_analyzer.py`: mock 从 `DrawingAnalyzerChain.invoke` 改为 mock `build_vision_analysis_chain` 返回的 Runnable
- [ ] 3.5 运行 vision 节点测试：`uv run pytest tests/test_drawing_analyzer.py tests/test_graph_nodes.py -v -k vision`

## 4. 节点层迁移——generate_step_drawing_node

- [ ] 4.1 创建 `async def _orchestrate_drawing_generation(state, config) -> dict` helper 函数，从节点函数中抽取编排逻辑（节点函数只负责状态映射、SSE dispatch 和异常处理）
- [ ] 4.2 在 helper 中内联 Stage 1.5 逻辑：调用 `ModelingStrategist.select(spec)` + API whitelist injection（从 `pipeline.py` 迁移），注意 `ModelingContext` → `{"modeling_context": str}` 的显式转换（替代旧 `prep_inputs()`）
- [ ] 4.3 在 helper 中内联 Stage 2 单路生成：`chain = build_code_gen_chain(); result = await chain.ainvoke({"modeling_context": ctx.to_prompt_text()})` + `Template.safe_substitute()` + `SafeExecutor.execute()`
- [ ] 4.4 在 helper 中内联 Stage 2 Best-of-N 分两阶段：(1) LLM 并发 `codes = await asyncio.gather(*[chain.ainvoke(ctx) for _ in range(N)])`；(2) 串行执行+评分 `for code in codes: SafeExecutor(output_dir=tempdir).execute(code); score = _score_geometry(...)`
- [ ] 4.5 在 helper 中内联 Stage 3.5 几何验证：`validate_step_geometry()`
- [ ] 4.6 集成 refiner 子图调用：构造 `RefinerState`（通过 `map_job_to_refiner`），调用 `refiner_subgraph.ainvoke(state, config=config)` 透传 configurable，提取 refined code（通过 `map_refiner_to_job`）
- [ ] 4.7 在 helper 中内联 Stage 5 后置检查：`cross_section_analysis()`
- [ ] 4.8 重写 `generate_step_drawing_node`：调用 `_orchestrate_drawing_generation(state, config)`，包裹 `asyncio.wait_for(timeout=300.0)` 超时保护
- [ ] 4.9 更新 generation 节点测试：mock LCEL chain + subgraph，验证编排流程
- [ ] 4.10 运行 generation 节点测试：`uv run pytest tests/test_generation_nodes.py -v`

## 5. pipeline.py 清理

- [ ] 5.1 更新 `analyze_and_generate_step()` 函数：保留此入口供 CLI/benchmark 使用，内部仍调用旧 Chain 类（标记 `# TODO: migrate to LangGraph graph invocation`）
- [ ] 5.2 删除 `pipeline.py` 中的 `analyze_vision_spec()` 函数和 `_run_analyze_vision()` 包装函数（LangGraph 节点已不再调用）
- [ ] 5.3 删除 `pipeline.py` 中的 `generate_step_from_spec()` 函数和 `_run_generate_from_spec()` 包装函数（LangGraph 节点已不再调用）
- [ ] 5.4 验证 `analyze_and_generate_step()` 仍可独立运行（它直接调用旧 Chain 类，不经过已删除的 `analyze_vision_spec`/`generate_step_from_spec`——如需要则重写其内部实现）
- [ ] 5.5 清理 `pipeline.py` 顶部未使用的 import
- [ ] 5.6 运行全量测试确认无回归：`uv run pytest tests/ -v`

## 6. 旧 Chain 类标记 deprecated

- [ ] 6.1 在 `DrawingAnalyzerChain`、`CodeGeneratorChain`、`SmartCompareChain`、`SmartFixChain` 类上添加 `@deprecated("使用 backend.graph.chains 中的 build_*_chain() 替代")` 装饰器
- [ ] 6.2 更新 `tests/test_smart_refiner.py`: mock 从 `SmartCompareChain.invoke` / `SmartFixChain.invoke` 改为 mock LCEL chain
- [ ] 6.3 运行全量测试并提交：`uv run pytest tests/ -v`

## 7. Resilience 测试补充

- [ ] 7.1 为每个 LCEL chain 编写 retry 测试：mock LLM 前 2 次抛出 RateLimitError，第 3 次成功 → 验证 `.with_retry()` 透明重试
- [ ] 7.2 为 generation 节点编写 timeout 测试：mock chain.ainvoke 耗时 > 300s → 验证 `asyncio.wait_for` 触发 TimeoutError → 节点返回 `{"status": "failed", "failure_reason": "timeout"}`
- [ ] 7.3 为轻量节点编写 timeout 测试：mock chain.ainvoke 耗时 > 60s → 验证 `asyncio.wait_for` 触发 60s 超时
- [ ] 7.4 运行 resilience 测试：`uv run pytest tests/test_llm_resilience.py -v`

## 8. 验证与文档

- [ ] 8.1 Grep 验证无 `asyncio.to_thread` 调用 vision/generation 同步函数：`git grep "to_thread.*_run_analyze\|to_thread.*_run_generate"` 应返回 0 结果
- [ ] 8.2 Grep 验证 LangGraph 节点不直接 import SequentialChain：`git grep "from.*SequentialChain\|import.*SequentialChain" backend/graph/` 应返回 0 结果
- [ ] 8.3 Grep 验证所有 chain builder 工厂函数为同步（非 async）：`git grep "async def build_.*_chain" backend/graph/chains/` 应返回 0 结果
- [ ] 8.4 TypeScript 编译检查：`cd frontend && npx tsc --noEmit`（确保前端不受影响）
- [ ] 8.5 更新 CLAUDE.md 架构描述：反映 LCEL chain + refiner subgraph 新模式
- [ ] 8.6 全量测试最终确认：`uv run pytest tests/ -v` — 所有测试通过
