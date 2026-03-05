# V3 Generate Pipeline Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 V2 管线 `generate_step_v2()` 集成进 V3 FastAPI 后端，补全前端生成全生命周期（输入 → 生成 → 预览 → 下载）。

**Architecture:** 后端通过 `asyncio.to_thread()` + `asyncio.Queue` 桥接将 V2 同步管线映射为 SSE 事件流。生成产物存储在 `outputs/{job_id}/`，STEP 自动转 GLB 供前端 Three.js 预览。前端补全 SSE 事件解析、配置传递和下载功能。

**Tech Stack:** Python 3.12, FastAPI, asyncio, CadQuery, Three.js (GLTFLoader), Ant Design

**OpenSpec Change:** `openspec/changes/v3-generate-pipeline-integration/`

---

## Task 1: `[backend]` PipelineBridge — 回调到 SSE 事件的桥接层

**Files:**
- Create: `backend/pipeline/sse_bridge.py`
- Test: `tests/test_sse_bridge.py`

**Step 1: Write the failing test**

```python
# tests/test_sse_bridge.py
"""Tests for PipelineBridge — maps V2 pipeline callbacks to asyncio.Queue events."""

from __future__ import annotations

import asyncio

import pytest

from backend.pipeline.sse_bridge import PipelineBridge


@pytest.fixture()
def bridge():
    return PipelineBridge(job_id="test-job")


class TestPipelineBridge:
    def test_on_spec_ready_puts_event(self, bridge: PipelineBridge) -> None:
        """on_spec_ready callback should put an intent_parsed event into queue."""
        # Simulate callback from worker thread
        bridge.on_spec_ready(
            spec={"part_type": "rotational", "overall_dimensions": {"diameter": 100}},
            reasoning="detected rotational part",
        )
        # Queue should have one event
        event = bridge.queue.get_nowait()
        assert event["event"] == "intent_parsed"
        assert event["job_id"] == "test-job"
        assert "spec" in event["data"]

    def test_on_progress_puts_event(self, bridge: PipelineBridge) -> None:
        """on_progress callback maps pipeline stages to SSE events."""
        bridge.on_progress("geometry", {"is_valid": True, "volume": 1234.5})
        event = bridge.queue.get_nowait()
        assert event["event"] == "generating"
        assert event["data"]["stage"] == "geometry"

    def test_on_progress_refinement(self, bridge: PipelineBridge) -> None:
        """refinement_round stage maps to 'refining' SSE event."""
        bridge.on_progress("refinement_round", {"round": 2, "total": 3, "status": "refined"})
        event = bridge.queue.get_nowait()
        assert event["event"] == "refining"

    def test_complete_puts_terminal_event(self, bridge: PipelineBridge) -> None:
        """complete() should put a completed event."""
        bridge.complete(model_url="/outputs/test-job/model.glb", step_path="/outputs/test-job/model.step")
        event = bridge.queue.get_nowait()
        assert event["event"] == "completed"
        assert event["data"]["model_url"] == "/outputs/test-job/model.glb"

    def test_fail_puts_error_event(self, bridge: PipelineBridge) -> None:
        """fail() should put a failed event."""
        bridge.fail("LLM API timeout")
        event = bridge.queue.get_nowait()
        assert event["event"] == "failed"
        assert "LLM API timeout" in event["data"]["message"]

    def test_queue_ordering(self, bridge: PipelineBridge) -> None:
        """Events should be ordered by insertion time."""
        bridge.on_progress("geometry", {"is_valid": True})
        bridge.on_progress("refinement_round", {"round": 1, "total": 3, "status": "refined"})
        bridge.complete(model_url="/out/model.glb")
        events = []
        while not bridge.queue.empty():
            events.append(bridge.queue.get_nowait())
        assert [e["event"] for e in events] == ["generating", "refining", "completed"]
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_sse_bridge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.pipeline.sse_bridge'`

**Step 3: Write minimal implementation**

```python
# backend/pipeline/sse_bridge.py
"""Bridge between V2 pipeline callbacks and asyncio.Queue for SSE streaming.

Design: D2 from design.md — asyncio.Queue as thread-safe channel.
The pipeline runs in a worker thread (via asyncio.to_thread), callbacks
put events into the Queue. The SSE generator in the main async loop
awaits queue.get() and yields SSE events.

NOTE: We use queue.Queue (thread-safe stdlib) not asyncio.Queue,
because callbacks run in a worker thread context. The async SSE
generator wraps get() with asyncio.to_thread().
"""

from __future__ import annotations

import queue
from typing import Any


# Map V2 pipeline stage names to SSE event types
_STAGE_TO_EVENT: dict[str, str] = {
    "geometry": "generating",
    "candidate": "generating",
    "refinement_round": "refining",
    "cross_section": "refining",
}


class PipelineBridge:
    """Bridges V2 pipeline callbacks → queue events for SSE streaming."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue()

    def on_spec_ready(self, spec: Any, reasoning: str | None = None) -> None:
        """Called when DrawingAnalyzer produces a DrawingSpec."""
        spec_data = spec.model_dump() if hasattr(spec, "model_dump") else spec
        self._put({
            "event": "intent_parsed",
            "job_id": self.job_id,
            "data": {
                "spec": spec_data,
                "reasoning": reasoning,
                "message": "图纸分析完成",
            },
        })

    def on_progress(self, stage: str, data: dict[str, Any]) -> None:
        """Called by V2 pipeline on_progress callback."""
        event_type = _STAGE_TO_EVENT.get(stage, "generating")
        message = self._stage_message(stage, data)
        self._put({
            "event": event_type,
            "job_id": self.job_id,
            "data": {"stage": stage, "message": message, **data},
        })

    def complete(
        self,
        model_url: str | None = None,
        step_path: str | None = None,
    ) -> None:
        """Signal pipeline completion."""
        self._put({
            "event": "completed",
            "job_id": self.job_id,
            "data": {
                "model_url": model_url,
                "step_path": step_path,
                "message": "生成完成",
            },
        })

    def fail(self, message: str) -> None:
        """Signal pipeline failure."""
        self._put({
            "event": "failed",
            "job_id": self.job_id,
            "data": {"message": message},
        })

    def _put(self, event: dict[str, Any]) -> None:
        self.queue.put_nowait(event)

    @staticmethod
    def _stage_message(stage: str, data: dict[str, Any]) -> str:
        if stage == "geometry":
            valid = data.get("is_valid", False)
            return "几何验证通过" if valid else "几何验证未通过，继续优化"
        if stage == "refinement_round":
            r, t = data.get("round", "?"), data.get("total", "?")
            status = data.get("status", "")
            return f"模型优化 {r}/{t} — {status}"
        if stage == "candidate":
            idx, total = data.get("index", "?"), data.get("total", "?")
            return f"候选评估 {idx}/{total}"
        return f"处理中: {stage}"
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_sse_bridge.py -v`
Expected: PASS (6/6)

**Step 5: Commit**

```bash
git add backend/pipeline/sse_bridge.py tests/test_sse_bridge.py
git commit -m "feat: add PipelineBridge for V2 callback → SSE event mapping"
```

---

## Task 2: `[backend]` 产物目录管理 + StaticFiles 挂载

**Files:**
- Create: `backend/infra/outputs.py`
- Modify: `backend/main.py:23-41`
- Test: `tests/test_outputs.py`

**Step 1: Write the failing test**

```python
# tests/test_outputs.py
"""Tests for output file management."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.infra.outputs import ensure_job_dir, get_model_url, get_step_path, OUTPUTS_DIR


class TestOutputsModule:
    def test_ensure_job_dir_creates_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("backend.infra.outputs.OUTPUTS_DIR", tmp_path / "outputs")
        job_dir = ensure_job_dir("job-123")
        assert job_dir.exists()
        assert job_dir.name == "job-123"

    def test_ensure_job_dir_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("backend.infra.outputs.OUTPUTS_DIR", tmp_path / "outputs")
        dir1 = ensure_job_dir("job-x")
        dir2 = ensure_job_dir("job-x")
        assert dir1 == dir2

    def test_get_model_url(self) -> None:
        url = get_model_url("abc-123", "glb")
        assert url == "/outputs/abc-123/model.glb"

    def test_get_model_url_step(self) -> None:
        url = get_model_url("abc-123", "step")
        assert url == "/outputs/abc-123/model.step"

    def test_get_step_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("backend.infra.outputs.OUTPUTS_DIR", tmp_path / "outputs")
        ensure_job_dir("job-1")
        path = get_step_path("job-1")
        assert str(path).endswith("job-1/model.step")
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_outputs.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/infra/outputs.py
"""Output file management for generate jobs.

Design: D4 from design.md — outputs/{job_id}/ directory per job,
served via StaticFiles mount.
"""

from __future__ import annotations

from pathlib import Path

OUTPUTS_DIR = Path("outputs").resolve()


def ensure_job_dir(job_id: str) -> Path:
    """Create and return outputs/{job_id}/ directory."""
    job_dir = OUTPUTS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def get_model_url(job_id: str, fmt: str = "glb") -> str:
    """Return the HTTP URL path for a model file."""
    return f"/outputs/{job_id}/model.{fmt}"


def get_step_path(job_id: str) -> Path:
    """Return the filesystem path for the STEP file."""
    return OUTPUTS_DIR / job_id / "model.step"
```

Then modify `backend/main.py` to mount StaticFiles:

```python
# Add to backend/main.py after existing router registrations:
from pathlib import Path
from starlette.staticfiles import StaticFiles

outputs_dir = Path("outputs")
outputs_dir.mkdir(exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_outputs.py -v`
Expected: PASS (5/5)

**Step 5: Commit**

```bash
git add backend/infra/outputs.py backend/main.py tests/test_outputs.py
git commit -m "feat: add output directory management and StaticFiles mount"
```

---

## Task 3: `[backend]` Drawing 模式集成 — 调用 V2 管线

**Files:**
- Modify: `backend/api/generate.py:99-149` (重写 `generate_drawing` 端点)
- Test: `tests/test_generate_api.py` (修改 `TestGenerateDrawingMode`)

**Step 1: Write the failing test**

在 `tests/test_generate_api.py` 的 `TestGenerateDrawingMode` 类中添加：

```python
def test_drawing_mode_with_pipeline_returns_model_url(self, client: TestClient, monkeypatch) -> None:
    """When V2 pipeline succeeds, completed event should contain model_url."""
    # Mock generate_step_v2 to simulate success
    import backend.api.generate as gen_mod

    def mock_generate(image_filepath, output_filepath, config=None, on_spec_ready=None, on_progress=None):
        # Create a fake STEP file
        Path(output_filepath).write_text("fake step")
        if on_spec_ready:
            on_spec_ready({"part_type": "rotational"}, "test reasoning")
        if on_progress:
            on_progress("geometry", {"is_valid": True, "volume": 100})

    monkeypatch.setattr(gen_mod, "_run_v2_pipeline", mock_generate)

    # Also mock GLB conversion
    monkeypatch.setattr(gen_mod, "_convert_step_to_glb", lambda step_path, glb_path: Path(glb_path).write_text("fake glb"))

    resp = client.post(
        "/api/generate/drawing",
        files={"image": ("test.png", b"fakepng", "image/png")},
    )
    events = parse_sse_events(resp.text)
    completed_events = [e for e in events if e.get("status") == "completed"]
    assert len(completed_events) == 1
    assert "model_url" in completed_events[0]
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_generate_api.py::TestGenerateDrawingMode::test_drawing_mode_with_pipeline_returns_model_url -v`
Expected: FAIL

**Step 3: Rewrite the generate_drawing endpoint**

重写 `backend/api/generate.py` 的 `generate_drawing()` 函数：

- 保存上传图片到临时文件
- 解析 `pipeline_config` → `PipelineConfig` 对象
- 创建 `PipelineBridge` 实例
- 使用 `asyncio.to_thread()` 在线程中调用 `generate_step_v2()`
- SSE 生成器从 `bridge.queue` 消费事件并 yield
- 完成后调用 `FormatExporter.to_gltf_for_preview()` 转 GLB
- 异常/超时走 `bridge.fail()`

关键代码框架：

```python
@router.post("/generate/drawing")
async def generate_drawing(
    image: UploadFile = File(...),
    pipeline_config: str = Form("{}"),
) -> EventSourceResponse:
    # 1. Parse config
    config = _parse_pipeline_config(pipeline_config)

    # 2. Save uploaded image to temp file
    job_id = str(uuid.uuid4())
    job = create_job(job_id, input_type="drawing")
    job_dir = ensure_job_dir(job_id)
    image_path = str(job_dir / f"input{_ext(image.filename)}")
    with open(image_path, "wb") as f:
        f.write(await image.read())

    # 3. Create bridge
    bridge = PipelineBridge(job_id)
    step_path = str(get_step_path(job_id))

    async def event_stream():
        yield _sse("job_created", {"job_id": job_id, "status": "created"})

        # 4. Run pipeline in thread
        try:
            await asyncio.to_thread(
                _run_v2_pipeline,
                image_path, step_path, config,
                bridge.on_spec_ready, bridge.on_progress,
            )
            # 5. Convert STEP → GLB
            glb_path = str(job_dir / "model.glb")
            _convert_step_to_glb(step_path, glb_path)
            model_url = get_model_url(job_id, "glb")
            bridge.complete(model_url=model_url, step_path=step_path)
        except Exception as exc:
            bridge.fail(str(exc))
            update_job(job_id, status=JobStatus.FAILED, error=str(exc))

        # 6. Drain queue → SSE
        while not bridge.queue.empty():
            evt = bridge.queue.get_nowait()
            update_job(job_id, status=JobStatus(evt["data"].get("status", evt["event"])))
            yield _sse(evt["event"], {"job_id": job_id, "status": evt["event"], **evt["data"]})

    return EventSourceResponse(event_stream())
```

`_run_v2_pipeline` 和 `_convert_step_to_glb` 是模块级辅助函数，便于 mock 测试。

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_generate_api.py -v`
Expected: All existing tests PASS + new test PASS

**Step 5: Commit**

```bash
git add backend/api/generate.py tests/test_generate_api.py
git commit -m "feat: integrate V2 pipeline into drawing mode endpoint"
```

---

## Task 4: `[backend]` Text 模式集成 — 参数化模板 + Confirm

**Files:**
- Modify: `backend/api/generate.py:65-96` (重写 `generate_text` 端点)
- Modify: `backend/api/generate.py:157-207` (重写 `confirm_params` 端点)
- Test: `tests/test_generate_api.py` (修改 `TestGenerateTextMode` 和 `TestConfirmParams`)

**Step 1: Write the failing test**

```python
# 添加到 TestGenerateTextMode
def test_text_mode_returns_parsed_params(self, client: TestClient) -> None:
    """intent_parsed event should contain params array for ParamForm."""
    resp = client.post(
        "/api/generate",
        json={"text": "做一个法兰盘，外径100mm"},
    )
    events = parse_sse_events(resp.text)
    parsed = [e for e in events if e.get("status") == "intent_parsed"]
    assert len(parsed) >= 1
    # Should have params for the frontend to display
    assert "params" in parsed[0] or "params" in parsed[0].get("data", {})


# 添加到 TestConfirmParams
def test_confirm_triggers_template_generation(self, client: TestClient, monkeypatch, tmp_path) -> None:
    """confirm should use parametric template to generate STEP."""
    import backend.api.generate as gen_mod
    monkeypatch.setattr(gen_mod, "_run_template_generation", lambda params, step_path: Path(step_path).write_text("fake step"))
    monkeypatch.setattr(gen_mod, "_convert_step_to_glb", lambda step_path, glb_path: Path(glb_path).write_text("fake glb"))

    job_id = self._create_awaiting_job(client)
    resp = client.post(
        f"/api/generate/{job_id}/confirm",
        json={"confirmed_params": {"outer_diameter": 100, "thickness": 16}},
    )
    events = parse_sse_events(resp.text)
    completed = [e for e in events if e.get("status") == "completed"]
    assert len(completed) == 1
    assert "model_url" in completed[0]
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_generate_api.py::TestGenerateTextMode::test_text_mode_returns_parsed_params -v`
Expected: FAIL

**Step 3: Implement text mode + confirm integration**

`generate_text()` 重写要点:
- 从 `body.text` 中使用简化逻辑提取零件描述和参数
- 查找匹配的参数化模板（`get_templates()` + 关键词匹配）
- `intent_parsed` 事件携带模板的 `params` 数组（`ParamDefinition[]`）
- 如未匹配模板，返回通用参数列表

`confirm_params()` 重写要点:
- 查找 Job 关联的模板
- 使用 Jinja2 渲染模板 `code_template` + 确认参数
- 在 sandbox 中执行渲染后的代码生成 STEP
- STEP → GLB 转换
- 失败时 fallback 提示

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_generate_api.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/api/generate.py tests/test_generate_api.py
git commit -m "feat: integrate text mode with parametric template generation"
```

---

## Task 5: `[frontend]` SSE 事件解析补全 — model_url + params

**Files:**
- Modify: `frontend/src/pages/Generate/GenerateWorkflow.tsx:14-20,259-301`
- Modify: `frontend/src/pages/Generate/index.tsx:14-33,44-66,96-141`
- Modify: `frontend/src/types/generate.ts` (如需新类型)

**Step 1: 修改 WorkflowState 类型**

在 `GenerateWorkflow.tsx` 中扩展 `WorkflowState`:

```typescript
export interface WorkflowState {
  phase: WorkflowPhase;
  jobId: string | null;
  message: string;
  error: string | null;
  modelUrl: string | null;
  // 新增
  parsedParams: ParamDefinition[] | null;  // 从 intent_parsed 事件获取
  stepPath: string | null;                  // 从 completed 事件获取
  progress: { stage: string; detail: string } | null;  // 细粒度进度
}
```

**Step 2: 修改 handleSSEEvent**

```typescript
case 'intent_parsed':
  setState((prev) => ({
    ...prev,
    jobId,
    phase: 'confirming',
    message,
    parsedParams: (evt.params ?? evt.data?.params ?? null) as ParamDefinition[] | null,
  }));
  break;
case 'completed':
  setState((prev) => ({
    ...prev,
    jobId,
    phase: 'completed',
    message,
    modelUrl: (evt.model_url ?? evt.data?.model_url ?? null) as string | null,
    stepPath: (evt.step_path ?? evt.data?.step_path ?? null) as string | null,
  }));
  break;
```

**Step 3: 修改 Generate/index.tsx**

- 删除 `PLACEHOLDER_PARAMS` 常量
- `ParamForm` 的 `params` 改为从 `workflow.parsedParams` 获取
- `paramValues` 的初始值从 `parsedParams` 的 default 字段初始化
- Drawing 模式跳过参数确认步骤（phase 直接从 parsing → generating）

```typescript
// 动态参数初始化
useEffect(() => {
  if (workflow.parsedParams) {
    const defaults: Record<string, number | string | boolean> = {};
    for (const p of workflow.parsedParams) {
      if (p.default != null) defaults[p.name] = p.default;
    }
    setParamValues(defaults);
  }
}, [workflow.parsedParams]);

// ParamForm 使用动态参数
{workflow.phase === 'confirming' && workflow.parsedParams && (
  <ParamForm
    params={workflow.parsedParams}
    values={paramValues}
    onChange={handleParamChange}
    onConfirm={handleConfirm}
    onReset={() => { /* reset to parsedParams defaults */ }}
    title="参数确认"
  />
)}
```

**Step 4: 验证编译通过**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 5: Commit**

```bash
git add frontend/src/pages/Generate/GenerateWorkflow.tsx frontend/src/pages/Generate/index.tsx
git commit -m "feat: handle model_url and parsed params in SSE events"
```

---

## Task 6: `[frontend]` 管线配置传递

**Files:**
- Modify: `frontend/src/components/PipelineConfigBar/index.tsx:199-253`
- Modify: `frontend/src/pages/Generate/index.tsx`
- Modify: `frontend/src/pages/Generate/GenerateWorkflow.tsx`

**Step 1: 提升 PipelineConfigBar 状态**

`PipelineConfigBar` 接受 `value`/`onChange` props（受控模式）:

```typescript
// PipelineConfigBar/index.tsx
interface PipelineConfigBarProps {
  value?: PipelineConfig;
  onChange?: (config: PipelineConfig) => void;
}
```

**Step 2: Generate/index.tsx 持有配置状态**

```typescript
const [pipelineConfig, setPipelineConfig] = useState<PipelineConfig>(DEFAULT_CONFIG);

// 传递给 PipelineConfigBar
<PipelineConfigBar value={pipelineConfig} onChange={setPipelineConfig} />
```

**Step 3: 修改 startTextGenerate 和 startDrawingGenerate**

在 `useGenerateWorkflow` hook 中，`startTextGenerate` 和 `startDrawingGenerate` 接受额外 `pipelineConfig` 参数：

```typescript
// startTextGenerate
body: JSON.stringify({ text, pipeline_config: pipelineConfig }),

// startDrawingGenerate
formData.append('pipeline_config', JSON.stringify(pipelineConfig));
```

**Step 4: 修正 drawing 模式 API URL**

`startDrawingGenerate()` 当前发送到 `POST /api/generate`，应改为 `POST /api/generate/drawing`:

```typescript
const resp = await fetch('/api/generate/drawing', {  // 修正 URL
  method: 'POST',
  body: formData,
});
```

**Step 5: 验证编译**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 6: Commit**

```bash
git add frontend/src/components/PipelineConfigBar/index.tsx frontend/src/pages/Generate/index.tsx frontend/src/pages/Generate/GenerateWorkflow.tsx
git commit -m "feat: pass pipeline config from frontend to API endpoints"
```

---

## Task 7: `[frontend]` 下载功能

**Files:**
- Modify: `frontend/src/pages/Generate/index.tsx` 或 create `frontend/src/pages/Generate/DownloadButtons.tsx`
- Modify: `backend/api/export.py:27-53` (支持 job_id)

**Step 1: 修改 export 端点支持 job_id**

```python
# backend/api/export.py — 添加 job_id 参数
@router.post("/export")
async def export_model(
    step_path: str = "",
    job_id: str = "",
    config: ExportConfig | None = None,
) -> FileResponse:
    config = config or ExportConfig()

    if job_id:
        resolved = get_step_path(job_id)
    else:
        resolved = Path(step_path).resolve()
        if not resolved.is_relative_to(_ALLOWED_DIR):
            raise HTTPException(status_code=403, detail="Access denied")

    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"STEP file not found")
    # ... rest unchanged
```

**Step 2: 创建前端下载按钮组件**

```typescript
// frontend/src/pages/Generate/DownloadButtons.tsx
import { Button, Space, Dropdown } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';

interface DownloadButtonsProps {
  jobId: string;
  stepPath: string | null;
}

export default function DownloadButtons({ jobId }: DownloadButtonsProps) {
  const handleDownload = async (format: string) => {
    const resp = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, config: { format } }),
    });
    if (!resp.ok) { message.error('下载失败'); return; }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `model.${format === 'gltf' ? 'glb' : format}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Space>
      <Button icon={<DownloadOutlined />} onClick={() => handleDownload('step')}>STEP</Button>
      <Button onClick={() => handleDownload('stl')}>STL</Button>
      <Button onClick={() => handleDownload('3mf')}>3MF</Button>
    </Space>
  );
}
```

**Step 3: 在 Generate/index.tsx 的 completed 状态中展示**

```typescript
{workflow.phase === 'completed' && workflow.jobId && (
  <DownloadButtons jobId={workflow.jobId} stepPath={workflow.stepPath} />
)}
```

**Step 4: 验证编译**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 5: Commit**

```bash
git add frontend/src/pages/Generate/DownloadButtons.tsx frontend/src/pages/Generate/index.tsx backend/api/export.py
git commit -m "feat: add download buttons for STEP/STL/3MF export"
```

---

## Task 8: `[backend]` 后端集成测试 — 完整 SSE 流

**Files:**
- Modify: `tests/test_generate_api.py`

**Step 1: 写集成测试**

```python
class TestDrawingModeIntegration:
    """Integration test: drawing upload → mocked pipeline → SSE with model_url."""

    def test_full_drawing_flow(self, client: TestClient, monkeypatch, tmp_path) -> None:
        """End-to-end: upload → pipeline → completed with model_url."""
        import backend.api.generate as gen_mod

        def mock_pipeline(image_path, output_path, config=None, on_spec_ready=None, on_progress=None):
            Path(output_path).write_text("mock step content")
            if on_spec_ready:
                on_spec_ready({"part_type": "plate"}, "test")
            if on_progress:
                on_progress("geometry", {"is_valid": True, "volume": 500})
                on_progress("refinement_round", {"round": 1, "total": 3, "status": "refined"})

        monkeypatch.setattr(gen_mod, "_run_v2_pipeline", mock_pipeline)
        monkeypatch.setattr(gen_mod, "_convert_step_to_glb", lambda s, g: Path(g).write_text("mock glb"))

        resp = client.post(
            "/api/generate/drawing",
            files={"image": ("drawing.png", b"\x89PNG\r\n", "image/png")},
            data={"pipeline_config": '{"preset": "fast"}'},
        )
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        event_types = [e.get("status") for e in events]
        assert "created" in event_types
        assert "completed" in event_types

        completed = [e for e in events if e.get("status") == "completed"][0]
        assert completed.get("model_url") is not None
        assert "/outputs/" in completed["model_url"]
        assert completed["model_url"].endswith(".glb")

    def test_pipeline_failure_returns_failed_event(self, client: TestClient, monkeypatch) -> None:
        """When pipeline throws, SSE should contain failed event."""
        import backend.api.generate as gen_mod

        def mock_pipeline_fail(*args, **kwargs):
            raise RuntimeError("LLM API unavailable")

        monkeypatch.setattr(gen_mod, "_run_v2_pipeline", mock_pipeline_fail)

        resp = client.post(
            "/api/generate/drawing",
            files={"image": ("test.png", b"fakepng", "image/png")},
        )
        events = parse_sse_events(resp.text)
        failed = [e for e in events if e.get("status") == "failed"]
        assert len(failed) >= 1
        assert "LLM API" in failed[0].get("message", "")
```

**Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/test_generate_api.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_generate_api.py
git commit -m "test: add integration tests for drawing mode pipeline"
```

---

## 依赖图 + 执行顺序

```
Task 1 (PipelineBridge) ──┐
                          ├──→ Task 3 (Drawing mode) ──→ Task 8 (Integration tests)
Task 2 (Outputs + Mount) ─┘                                    │
                                                                ↓
Task 4 (Text mode + Confirm) ──────────────────────────→ [后端完成]
                                                                │
Task 5 (SSE events frontend) ──┐                               │
                               ├──→ Task 7 (Download) ──→ [前端完成]
Task 6 (Config passing) ──────┘
```

**推荐执行顺序（考虑依赖）:**
1. Task 1 + Task 2 (并行，无依赖)
2. Task 3 (依赖 Task 1 + 2)
3. Task 4 (依赖 Task 1 + 2，可与 Task 3 后串行)
4. Task 5 + Task 6 (前端并行，不依赖后端完成)
5. Task 7 (依赖 Task 5 + 6 + 后端 export 修改)
6. Task 8 (依赖 Task 3 + 4，可与前端并行)

**域标签统计:** `[backend]` x5, `[frontend]` x3 — 2 个域标签，不满足 Agent Team 条件（需 3+），使用 subagent-driven-development。
