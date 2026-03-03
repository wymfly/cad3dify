# 遗留代码清理设计

## 目标

移除项目中 v1/v2/v3 历史版本标签和死代码，统一为纯 LangGraph 双管道架构（精密建模 + 创意雕塑），确保整个项目围绕两条管道运行。

## 决策

- **仅清理死代码**：`backend/core/` 中仍被 LangGraph 节点调用的旧链（DrawingAnalyzerChain、CodeGeneratorChain、SmartRefiner）暂时保留，后续单独做 LangGraph 化重构。
- **`backend/api/v1/`** 是正常 REST API 版本前缀，保留。
- **`benchmarks/v1/`** 是数据集命名，不是代码版本，保留。

## 删除清单

### A. 整包删除

| 目标 | 说明 |
|------|------|
| `cadpilot/` | 27 个 .py 文件 + knowledge/ 子包，纯兼容 shim，所有代码已在 backend/ 下 |
| `backend/v1/` | 3 个文件（CadCodeGeneratorChain、CadCodeRefinerChain），V1 最旧实现 |

### B. 构建器统一

| 操作 | 说明 |
|------|------|
| 删除 `backend/graph/builder_legacy.py` | 手写拓扑旧构建器 |
| 重命名 `backend/graph/builder_new.py` → `backend/graph/builder.py` | 统一为唯一构建器 |
| 简化 `backend/graph/__init__.py` | 移除 `USE_NEW_BUILDER` 双轨，直接导出新构建器 |
| 删除 `backend/graph/routing.py` 中 `route_after_organic_mesh` | builder_legacy 专用路由 |

### C. 旧入口删除

| 目标 | 说明 |
|------|------|
| `scripts/app.py` | Streamlit UI |
| `scripts/cli.py` | 旧 CLI 工具 |
| `start.sh` | Streamlit 启动脚本 |
| 重命名 `scripts/start-v3.sh` → `scripts/start.sh` | 去掉版本后缀 |

### D. deprecated 函数删除

- `backend/graph/nodes/organic.py` 中的 `generate_organic_mesh_node` 和 `postprocess_organic_node`

### E. 遗留测试删除

| 目标 | 说明 |
|------|------|
| `tests/test_import_compat.py` | 测试 cadpilot 包兼容 shim |
| `tests/test_v1_pipeline_integration.py` | 测试 V1 管道桥接 |

## 迁移清单

### F. Import 路径迁移（`from cadpilot.xxx` → `from backend.xxx`）

| 文件 | 旧路径 | 新路径 |
|------|--------|--------|
| `tests/test_knowledge_base.py` | `cadpilot.knowledge.examples` | `backend.knowledge.examples` |
| `tests/test_knowledge_expansion.py` | `cadpilot.knowledge.examples` | `backend.knowledge.examples` |
| `tests/test_modeling_strategist.py` | `cadpilot.v2.modeling_strategist` | `backend.core.modeling_strategist` |
| `tests/test_feature_model.py` | `cadpilot.v2.modeling_strategist` | `backend.core.modeling_strategist` |
| `tests/test_smart_refiner.py` | `cadpilot.v2.smart_refiner` | `backend.core.smart_refiner` |
| `tests/test_drawing_analyzer.py` | `cadpilot.v2.drawing_analyzer` | `backend.core.drawing_analyzer` |
| `tests/test_validators.py` | `cadpilot.v2.validators` | `backend.core.validators` |
| `tests/test_vector_retrieval.py` | `cadpilot.v2.modeling_strategist` | `backend.core.modeling_strategist` |
| `backend/graph/nodes/generation.py:38` | `cadpilot.knowledge.part_types` | `backend.knowledge.part_types` |

### G. pipeline.py V1 降级移除

- 删除 `from ..v1.cad_code_generator import CadCodeGeneratorChain`
- 删除 `from ..v1.cad_code_refiner import CadCodeRefinerChain`
- 删除 V1 降级路径代码（`generate_step_from_2d_cad_image` 函数及相关）

### H. 版本标签清理

- `pyproject.toml`：移除 `# V2 existing`、`# V3 new` 注释，移除 `streamlit` 依赖
- `CLAUDE.md`：更新项目结构描述，移除 V1/V2/V3 版本字样
- 日志字符串和注释中的版本引用

## 不动的部分

- `backend/api/v1/` — REST API 版本前缀
- `backend/core/` — DrawingAnalyzerChain 等仍被 LangGraph 节点调用
- `backend/pipeline/pipeline.py` — 仍被调用的核心逻辑（删除 V1 降级路径后保留）
- `benchmarks/v1/` — 数据集命名

## 验证标准

1. `uv run pytest tests/ -v` 全部通过
2. `cd frontend && npx tsc --noEmit` 无错误
3. `git grep -r "from cadpilot"` 返回 0 结果
4. `git grep -r "USE_NEW_BUILDER"` 返回 0 结果
5. `ls cadpilot/ backend/v1/` 不存在
