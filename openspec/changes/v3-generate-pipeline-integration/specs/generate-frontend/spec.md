## ADDED Requirements

### Requirement: SSE 事件携带模型 URL

前端 SHALL 从 `completed` SSE 事件中提取 `model_url` 字段，并传递给 `Viewer3D` 组件进行 3D 预览渲染。

#### Scenario: 生成完成后自动加载 3D 模型
- **WHEN** 前端收到 `completed` SSE 事件且 `model_url` 不为 null
- **THEN** `WorkflowState.modelUrl` SHALL 被设置为该 URL，`Viewer3D` 自动加载并展示 GLB 模型

#### Scenario: 无模型 URL 时显示提示
- **WHEN** 前端收到 `completed` SSE 事件但 `model_url` 为 null
- **THEN** 前端 SHALL 显示"生成完成但预览不可用"的提示，仍可通过下载按钮获取 STEP 文件

### Requirement: 管线配置传递到 API

`PipelineConfigBar` 的配置 SHALL 通过 Generate 页面传递到 API 请求中。

#### Scenario: Drawing 模式携带配置
- **WHEN** 用户选择 fast 预设后上传图纸
- **THEN** `startDrawingGenerate()` 发送的 FormData SHALL 包含 `pipeline_config` 字段，值为配置 JSON

#### Scenario: Text 模式携带配置
- **WHEN** 用户选择 precise 预设后输入文字描述
- **THEN** `startTextGenerate()` 发送的请求 body SHALL 包含 `pipeline_config` 字段

### Requirement: 下载功能

生成完成后，前端 SHALL 提供下载按钮，允许用户下载 STEP/STL/3MF 格式的模型文件。

#### Scenario: 下载 STEP 文件
- **WHEN** 用户点击"下载 STEP"按钮
- **THEN** 前端 SHALL 调用 `/api/export` 端点获取 STEP 文件并触发浏览器下载

#### Scenario: 下载 STL 文件
- **WHEN** 用户点击"下载 STL"按钮
- **THEN** 前端 SHALL 调用 `/api/export` 端点（config.format="stl"），获取 STL 文件并触发下载

### Requirement: 参数确认表单动态生成

参数确认表单 SHALL 基于后端解析结果动态生成，而非使用硬编码的 `PLACEHOLDER_PARAMS`。

#### Scenario: Text 模式解析出参数列表
- **WHEN** 后端 `intent_parsed` 事件返回 `params` 数组
- **THEN** 前端 SHALL 根据返回的参数定义（name、display_name、unit、range_min、range_max、default）动态生成 `ParamForm`

#### Scenario: Drawing 模式跳过参数确认
- **WHEN** 用户使用 drawing 模式（上传图纸）
- **THEN** 前端 SHALL 跳过参数确认步骤，直接进入生成阶段（drawing 模式由 V2 管线自主完成所有阶段）

### Requirement: 进度信息实时显示

前端 SHALL 在 `GenerateWorkflow` 组件中实时展示管线各阶段的进度信息。

#### Scenario: 显示当前阶段描述
- **WHEN** 收到 `generating` 或 `refining` SSE 事件
- **THEN** `GenerateWorkflow` SHALL 更新进度条和阶段描述文字，展示当前阶段名称

#### Scenario: 显示细粒度进度
- **WHEN** SSE 事件包含 `progress` 字段（如 refining 第 2/3 轮）
- **THEN** 前端 SHALL 在阶段描述中展示细粒度进度信息（如"模型优化 2/3"）

### Requirement: 错误信息友好展示

当生成失败时，前端 SHALL 展示用户可理解的错误信息。

#### Scenario: LLM 调用失败
- **WHEN** 后端因 LLM API 错误发送 `failed` 事件
- **THEN** 前端 SHALL 在 Alert 组件中展示错误消息，并提供"重新生成"按钮

#### Scenario: 超时失败
- **WHEN** 后端因管线超时发送 `failed` 事件
- **THEN** 前端 SHALL 提示"生成超时，请尝试使用 fast 预设或简化输入"
