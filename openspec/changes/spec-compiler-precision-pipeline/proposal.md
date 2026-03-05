## Why

精密路径（text/drawing → STEP）的代码生成逻辑散布在 `vision_cad_pipeline.py`、`generation.py`、`analysis.py` 三处，模板匹配用硬编码关键字、模板 miss 时直接 hard-fail、DrawingSpec 字段不规范、推荐引擎空转。需要一个统一调度入口（SpecCompiler）收敛这些散落逻辑，并补齐 LLM fallback、语义路由、后加工推荐等缺失能力，使精密路径达到生产可用。

## What Changes

- 引入 `SpecCompiler` 统一调度器：接收 IntentSpec/DrawingSpec + 用户确认参数，执行「模板优先 → LLM fallback」策略，输出 CadQuery 代码 + STEP 文件
- text-path 模板 miss 时自动降级到 Coder LLM 生成，替代当前 hard-fail
- 模板匹配从关键字匹配升级为 part_type 语义路由（`TemplateEngine.find_matches` + 评分排序）
- DrawingSpec `overall_dimensions` 规范化为标准键名 schema（长/宽/高/直径统一命名）
- 引入拦截器注册表（`InterceptorRegistry`），支持在管道中动态插入 Watermark/ThermalAnalysis 等后处理步骤
- 填充 `recommendations` 字段：基于 `EngineeringStandards` + `PrintabilityChecker` 结果生成后加工建议

## Capabilities

### New Capabilities
- `spec-compiler`: 统一代码编译调度器 — 封装模板渲染 + LLM fallback + 代码执行的完整流程
- `interceptor-registry`: 管道拦截器注册表 — 允许通过配置动态插入后处理节点
- `post-processing-recommendations`: 后加工推荐引擎 — 基于可打印性分析结果推荐 NX/Magics/Oqton 操作

### Modified Capabilities
- `langgraph-job-orchestration`: generation 节点改为通过 SpecCompiler 调度，路由逻辑变更

## Impact

- **核心变更**: `backend/core/spec_compiler.py`（新建）、`backend/graph/nodes/generation.py`（重构）、`backend/graph/nodes/analysis.py`（模板路由增强）
- **数据模型**: `backend/knowledge/part_types.py` DrawingSpec 字段规范化、`backend/graph/state.py` 新增 recommendations
- **管道拓扑**: `backend/graph/builder.py` 拦截器注册表支持动态节点
- **依赖**: 无新外部依赖，复用已有 `TemplateEngine`、`EngineeringStandards`、`SafeExecutor`
- **API**: 无 **BREAKING** 变更，Job 响应中 `recommendations` 字段从空数组变为填充值
