## ADDED Requirements

### Requirement: Drawing 模式调用 V2 管线

当用户上传工程图纸时，系统 SHALL 调用 `generate_step_v2()` 函数执行完整的 V2 管线（DrawingAnalyzer → ModelingStrategist → CodeGenerator → SmartRefiner），产出 STEP 文件。

#### Scenario: 成功生成 STEP 文件
- **WHEN** 用户通过 `POST /api/generate/drawing` 上传一张工程图纸
- **THEN** 系统将图片保存为临时文件，调用 `generate_step_v2(image_path, output_path, config=pipeline_config)`，生成 STEP 文件存储在 `outputs/{job_id}/model.step`

#### Scenario: 管线执行失败
- **WHEN** V2 管线在执行过程中抛出异常（LLM 调用失败、CadQuery 编译错误等）
- **THEN** 系统 SHALL 发送 `failed` SSE 事件，包含错误消息，Job 状态更新为 FAILED

#### Scenario: 管线执行超时
- **WHEN** V2 管线执行超过 `PipelineConfig.execution_timeout` 秒
- **THEN** 系统 SHALL 终止执行，发送 `failed` SSE 事件，消息包含超时信息

### Requirement: 异步执行不阻塞事件循环

V2 管线执行 SHALL 在独立线程中运行，不阻塞 FastAPI 的 async 事件循环。

#### Scenario: 并发请求不阻塞
- **WHEN** 一个生成任务正在执行，另一个用户发送新的生成请求
- **THEN** 新请求 SHALL 正常被接受和处理，不因前一个任务阻塞

### Requirement: 进度回调映射为 SSE 事件

系统 SHALL 将 V2 管线的 `on_spec_ready` 和 `on_progress` 回调映射为 SSE 事件流，使前端能够实时展示生成进度。

#### Scenario: DrawingSpec 解析完成
- **WHEN** V2 管线的 `on_spec_ready(spec, reasoning)` 回调被触发
- **THEN** 系统 SHALL 发送 `intent_parsed` SSE 事件，包含解析出的零件类型和关键尺寸

#### Scenario: 各阶段进度更新
- **WHEN** V2 管线的 `on_progress(stage, data)` 回调在不同阶段被触发（analyzing/strategizing/generating/refining）
- **THEN** 系统 SHALL 发送对应的 SSE 事件（`generating` 或 `refining`），包含阶段描述

### Requirement: STEP 自动转换为 GLB

生成完成后，系统 SHALL 自动将 STEP 文件转换为 GLB 格式，用于前端 3D 预览。

#### Scenario: 转换成功
- **WHEN** STEP 文件生成成功
- **THEN** 系统 SHALL 调用 `FormatExporter` 将 STEP 转为 GLB，存储在 `outputs/{job_id}/model.glb`，并在 `completed` SSE 事件中包含 `model_url` 字段

#### Scenario: 转换失败不影响 STEP 产物
- **WHEN** STEP → GLB 转换失败（如不支持的几何体）
- **THEN** Job 仍 SHALL 标记为 COMPLETED，`completed` 事件中 `model_url` 为 null，STEP 文件仍可下载

### Requirement: 产物文件通过 HTTP 提供访问

系统 SHALL 将 `outputs/` 目录挂载为静态文件服务，使前端可以通过 URL 访问 GLB 和 STEP 文件。

#### Scenario: 前端加载 GLB 预览
- **WHEN** 前端使用 `completed` 事件中的 `model_url` 加载模型
- **THEN** 系统 SHALL 通过 HTTP 返回 GLB 文件，Content-Type 为 `model/gltf-binary`

### Requirement: 管线配置传递

系统 SHALL 接受前端传递的 `pipeline_config` 参数，并将其转换为 `PipelineConfig` 对象传递给 V2 管线。

#### Scenario: 使用 fast 预设
- **WHEN** 用户选择 fast 预设，请求中 `pipeline_config` 包含 `{"preset": "fast"}`
- **THEN** 系统 SHALL 使用 `PRESETS["fast"]` 配置调用管线（`num_refinements=1`，`enable_multi_view=false`）

#### Scenario: 无配置时使用默认
- **WHEN** 请求中 `pipeline_config` 为空对象
- **THEN** 系统 SHALL 使用默认配置（balanced 预设）

### Requirement: Text 模式参数确认后生成

当用户通过 text 模式输入并确认参数后，系统 SHALL 使用确认的参数执行生成。

#### Scenario: 参数确认触发模板生成
- **WHEN** 用户在 text 模式确认参数后调用 `POST /api/generate/{job_id}/confirm`
- **THEN** 系统 SHALL 使用确认参数查找匹配的参数化模板，渲染 CadQuery 代码，在 sandbox 中执行生成 STEP 文件

#### Scenario: 无匹配模板时 fallback 到 LLM
- **WHEN** 确认参数后无法匹配到参数化模板
- **THEN** 系统 SHALL fallback 到 LLM 代码生成（类似 drawing 模式的 CodeGenerator），生成 CadQuery 代码并执行
