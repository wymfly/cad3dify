## Context

V3 Phase 1-6 建立了完整的前后端框架：FastAPI 后端 + React 前端，SSE 事件协议、Job 生命周期管理、3D Viewer、导出端点等均已就位。但核心生成逻辑仍为占位——`generate.py` 的三个端点返回固定 SSE 事件，不调用任何实际管线。

V2 管线 `generate_step_v2()` 是一个同步函数，接受图片路径和输出路径，经过 DrawingAnalyzer → ModelingStrategist → CodeGenerator → SmartRefiner 四阶段产出 STEP 文件。它提供两个回调钩子：`on_spec_ready(spec, reasoning)` 和 `on_progress(stage, data)`，天然适合映射为 SSE 事件。

前端 Viewer3D 使用 Three.js GLTFLoader，需要 GLB 格式的 URL。后端已有 `FormatExporter` 可将 STEP 转为 glTF/GLB。

## Goals / Non-Goals

**Goals:**

- 在 V3 前端实现完整的"输入 → 生成 → 预览 → 下载"全生命周期
- Drawing 模式：上传工程图 → 调用 V2 管线 → 实时进度 → 3D 预览
- Text 模式：文字描述 → 参数确认 → 参数化模板/LLM 生成 → 3D 预览
- 管线配置（fast/balanced/precise）从前端传递到后端并生效
- 生成完成后可下载 STEP/STL/3MF 文件

**Non-Goals:**

- 不修改 V2 管线核心逻辑（DrawingAnalyzer、CodeGenerator、SmartRefiner）
- 不实现 IntentParser 的实际 NLP 解析（text 模式暂用简化匹配）
- 不实现多用户并发隔离（当前内存 Job store 足够 MVP）
- 不删除 V2 Streamlit UI 代码（暂保留但不使用）
- 不实现 PrintabilityChecker（Phase 4 范围）

## Decisions

### D1: V2 管线异步包装方式

**选择**: `asyncio.to_thread()` 包装同步 `generate_step_v2()`

**替代方案**:
- `run_in_executor(ThreadPoolExecutor)`: 更细粒度控制线程池，但 `to_thread` 已足够且更简洁
- 重写为 async: 成本过高，V2 管线内部大量同步 I/O（LLM SDK、CadQuery）

**理由**: `generate_step_v2()` 是 CPU+IO 密集型长时任务（30s~5min），`to_thread` 将其移到线程池，不阻塞 FastAPI 事件循环。回调钩子在工作线程中执行，通过 `asyncio.Queue` 将事件传递回 SSE 生成器。

### D2: 进度回调 → SSE 事件桥接

**选择**: `asyncio.Queue` 作为线程间通信通道

```
工作线程 (generate_step_v2)          主线程 (SSE generator)
  on_progress(stage, data) ──put──→  Queue ──get──→ yield _sse(event)
  on_spec_ready(spec) ────put──→     Queue ──get──→ yield _sse("intent_parsed")
  完成/异常 ──────────put──→         Queue ──get──→ yield _sse("completed"/"failed")
```

**理由**: Queue 是线程安全的，且 `asyncio.Queue` 支持 `await queue.get()` 不阻塞事件循环。管线回调可以通过普通的 `queue.put_nowait()` 从同步上下文发送事件。

### D3: STEP → GLB 转换时机

**选择**: 生成完成后立即转换，GLB URL 随 `completed` 事件返回

**替代方案**:
- 前端请求时按需转换: 增加延迟，用户体验差
- 预生成所有格式: 浪费存储，STL/3MF 用户可能不需要

**理由**: GLB 是预览必需品，随完成事件返回可实现零延迟预览加载。其他格式按需导出（用户点下载时调用 `/api/export`）。

### D4: 产物文件管理

**选择**: `outputs/{job_id}/` 目录结构，通过 `StaticFiles` 挂载提供 HTTP 访问

```
outputs/
  {job_id}/
    model.step
    model.glb
```

**替代方案**:
- 临时文件 + 专用下载端点: 清理逻辑复杂
- MinIO 对象存储: 过重，MVP 不需要

**理由**: 目录按 job_id 隔离，前端通过 `/outputs/{job_id}/model.glb` 直接访问。后续可加定时清理。

### D5: Text 模式的简化实现

**选择**: 暂不集成完整 IntentParser，text 模式使用简化的参数提取 + 参数化模板匹配

**理由**: Phase 3 已实现参数化模板系统。Text 输入通过关键词匹配或 LLM 简单提取，找到匹配模板 → 填充参数 → 生成 CadQuery 代码 → 执行。这比完整 IntentParser 更快可用。

### D6: 前端管线配置传递

**选择**: `PipelineConfigBar` 的配置通过 Generate 页面 state 注入到 API 请求的 `pipeline_config` 字段

**理由**: `PipelineConfigBar` 已存储配置，只需向上提升 state，在 `startTextGenerate` 和 `startDrawingGenerate` 调用时携带配置 JSON。

## Risks / Trade-offs

- **[长时阻塞]** V2 管线执行可达 5 分钟 → 使用 `asyncio.to_thread`，线程池默认并发数限制自然防护。超时由 `PipelineConfig.execution_timeout` 控制。
- **[LLM 依赖]** 运行环境需 DashScope API Key + CadQuery 安装 → 启动时检查依赖，缺失时返回明确错误信息而非挂起。
- **[文件积累]** `outputs/` 目录会持续增长 → 暂不实现自动清理，后续可加 TTL 策略。MVP 阶段手动管理。
- **[并发安全]** 内存 Job store 不支持多进程 → 当前单进程部署足够。生产环境需切换到 Redis/DB。
- **[SSE 断连]** 长时间生成期间 SSE 连接可能中断 → 前端可通过 `GET /generate/{job_id}` 轮询恢复状态。
