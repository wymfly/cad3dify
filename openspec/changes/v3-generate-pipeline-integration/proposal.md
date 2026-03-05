## Why

V3 前端 UI 和后端 API 框架已搭建完成（Phase 1-6），但模型生成核心流程仍为占位实现——`backend/api/generate.py` 的三个端点（text/drawing/confirm）均返回固定 SSE 事件，未调用 V2 管线的 `generate_step_v2()` 函数。用户无法通过 V3 界面完成从输入到 3D 模型预览/下载的完整操作。现在 V2 管线代码完整可用，需要将其集成进 V3 后端，并补全前端交互，实现完整的生成全生命周期。

## What Changes

### 后端集成

- 在 `generate.py` 的 drawing 端点中调用 V2 管线 `generate_step_v2()`，将图片保存为临时文件后传入管线
- 利用 V2 管线的 `on_spec_ready` 和 `on_progress` 回调钩子将各阶段状态映射为 SSE 事件（`intent_parsed`→`generating`→`refining`→`completed`）
- 在 confirm 端点中基于确认参数调用参数化模板或 LLM 生成管线
- 生成完成后自动调用 `FormatExporter` 将 STEP 转为 GLB，供前端 Three.js 预览
- 将生成产物（STEP/GLB）存入 `outputs/` 目录，通过静态文件服务或专用端点提供下载
- 在 sandbox 中执行 LLM 生成的 CadQuery 代码，确保安全隔离

### 前端补全

- `GenerateWorkflow.tsx` 的 `handleSSEEvent()` 解析 `completed` 事件中的 `model_url` 字段，传递给 `Viewer3D` 组件
- `startDrawingGenerate()` 发送图片时携带 `PipelineConfigBar` 的配置参数
- `startTextGenerate()` 发送文本时携带管线配置
- 完成后显示下载按钮（STEP/STL/3MF），调用 `/api/export` 端点
- 参数确认表单从 IntentParser 返回的解析结果动态生成（替代当前硬编码的 `PLACEHOLDER_PARAMS`）

### 异步适配

- V2 管线 `generate_step_v2()` 是同步阻塞函数（含 LLM 调用 + CadQuery 执行），需包装为 `asyncio.to_thread()` 或 `run_in_executor()` 以避免阻塞 FastAPI 事件循环

## Capabilities

### New Capabilities

- `generate-pipeline`: 后端生成管线集成——从用户输入到 STEP/GLB 产物的完整执行链路，包括 V2 管线调用、进度回调、产物管理
- `generate-frontend`: 前端生成流程补全——SSE 事件解析、3D 预览加载、配置参数传递、下载功能

### Modified Capabilities

（无已有 spec 需要修改）

## Impact

- **代码**: `backend/api/generate.py`（核心改动）、`backend/pipeline/`（适配层）、`frontend/src/pages/Generate/`（4-5 个 TSX 文件）
- **API**: `/api/generate` 和 `/api/generate/drawing` 的 SSE 响应增加 `model_url` 等字段；`/api/generate/{job_id}/confirm` 开始执行实际生成
- **依赖**: 需要后端运行环境安装 CadQuery + LangChain + 对应 LLM SDK
- **文件系统**: `outputs/` 目录存储 STEP 和 GLB 产物文件
- **性能**: 生成过程耗时 30s~5min（取决于 LLM + CadQuery 执行），需 async 包装避免阻塞
