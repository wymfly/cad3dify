## 1. 后端基础设施

- [ ] 1.1 创建 `asyncio.Queue` 桥接模块 `backend/pipeline/sse_bridge.py`：实现 `PipelineBridge` 类，将 V2 管线的 `on_spec_ready` 和 `on_progress` 回调转为 `asyncio.Queue` 事件
- [ ] 1.2 创建产物目录管理模块 `backend/infra/outputs.py`：实现 `ensure_job_dir(job_id)` 和 `get_model_url(job_id, format)` 工具函数，管理 `outputs/{job_id}/` 目录
- [ ] 1.3 在 FastAPI app 中挂载 `outputs/` 为 `StaticFiles`，使前端可通过 `/outputs/{job_id}/model.glb` 访问产物文件

## 2. Drawing 模式后端集成

- [ ] 2.1 重写 `generate_drawing()` 端点：保存上传图片到临时文件，解析 `pipeline_config` 为 `PipelineConfig` 对象
- [ ] 2.2 实现 drawing 模式的 SSE 事件流生成器：使用 `asyncio.to_thread()` 在线程中调用 `generate_step_v2()`，通过 `PipelineBridge` 的 Queue 将进度回调转为 SSE 事件
- [ ] 2.3 生成完成后调用 `FormatExporter` 将 STEP 转为 GLB，`completed` 事件中包含 `model_url` 字段
- [ ] 2.4 处理管线异常和超时：捕获异常发送 `failed` 事件，使用 `PipelineConfig.execution_timeout` 控制超时

## 3. Text 模式后端集成

- [ ] 3.1 重写 `generate_text()` 端点：从文字描述中提取参数（简化实现，使用关键词匹配或 LLM 单轮提取），返回 `intent_parsed` 事件携带 `params` 数组
- [ ] 3.2 重写 `confirm_params()` 端点：使用确认参数查找匹配的参数化模板，渲染 CadQuery 代码，在 sandbox 中执行生成 STEP 文件
- [ ] 3.3 Text 模式的 fallback 路径：无匹配模板时使用 LLM CodeGenerator 生成 CadQuery 代码

## 4. 前端 SSE 事件处理补全

- [ ] 4.1 修改 `handleSSEEvent()` 解析 `completed` 事件中的 `model_url` 字段，设置到 `WorkflowState.modelUrl`
- [ ] 4.2 修改 `handleSSEEvent()` 解析 `intent_parsed` 事件中的 `params` 数组，存入 workflow state 供 ParamForm 使用
- [ ] 4.3 替换 `Generate/index.tsx` 中的 `PLACEHOLDER_PARAMS`，改为从 workflow state 中的解析结果动态生成

## 5. 前端管线配置传递

- [ ] 5.1 将 `PipelineConfigBar` 的配置 state 提升到 `Generate/index.tsx`，通过 props 或 context 传递
- [ ] 5.2 修改 `startTextGenerate()` 在请求 body 中携带 `pipeline_config`
- [ ] 5.3 修改 `startDrawingGenerate()` 在 FormData 中携带 `pipeline_config` 字段
- [ ] 5.4 修正 `startDrawingGenerate()` 的 API URL：当前指向 `POST /api/generate` 但 drawing 模式应使用 `POST /api/generate/drawing`

## 6. 前端下载功能

- [ ] 6.1 在 `GenerateWorkflow` 或 `Generate/index.tsx` 完成状态下显示下载按钮组（STEP/STL/3MF），调用 `/api/export` 端点
- [ ] 6.2 修改 `/api/export` 端点支持 `job_id` 参数（当前只接受 `step_path`），自动定位 `outputs/{job_id}/model.step`

## 7. 测试

- [ ] 7.1 后端单元测试：`PipelineBridge` 的 Queue 事件转换逻辑
- [ ] 7.2 后端集成测试：`generate_drawing` 端点（mock V2 管线）的 SSE 事件流完整性
- [ ] 7.3 后端集成测试：`confirm_params` 端点使用参数化模板生成的完整流程
- [ ] 7.4 前端单元测试：`handleSSEEvent` 对 `model_url` 和 `params` 的解析
