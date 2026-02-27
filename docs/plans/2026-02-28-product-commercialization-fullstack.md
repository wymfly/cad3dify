# Product Commercialization Full-Stack Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 cad3dify V3 从原型推向产品化——串联断裂管道（PrintabilityChecker、OCR、IntentParser）、添加 HITL 确认流、引入 SQLite 持久化、构建零件库和实时预览。

**Architecture:** P0 管道串联优先（D1）→ P1 智能层 → P2 数据基础设施。图纸管道拆分为 Stage 1 和 Stage 1.5-4 两段（D8），SSE 流分段。SQLite + aiosqlite 持久化（D2），PaddleOCR 本地推理（D3）。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 + aiosqlite, Alembic, PaddleOCR (PP-OCRv5), CadQuery 2.4, React 18, TypeScript, Ant Design, Three.js

**OpenSpec Reference:** `openspec/changes/product-commercialization-fullstack/`

---

## Domain Labels & Skill Routing

| 标签 | Skills | 适用任务 |
|------|--------|---------|
| `[backend]` | `sqlalchemy-orm`, `streaming-api-patterns` | 1.1-1.6, 2.1-2.4/2.7, 3.1, 4.1-4.4, 5.1-5.3, 6.1-6.7, 7.1-7.3, 8.1-8.4 |
| `[frontend]` | `ant-design`, `frontend-design`, `ui-ux-pro-max` | 1.7, 2.5-2.6, 3.2, 7.4-7.7, 8.5 |
| `[test]` | `qa-testing-strategy`, `test-automation-framework` | 1.3/1.8, 2.8, 4.3/4.5, 5.4, 6.8-6.9, 7.8, 8.6 |

## Parallelization Map

```
P0 Phase (Groups 1-3):
  Group 1 (Printability) ──┐
  Group 2 (HITL)          ├── 并行（无依赖）
  Group 3 (3MF)           ──┘

P1 Phase (Groups 4-5):
  Group 4 (PaddleOCR) ────┐
  Group 5 (IntentParser)  ├── 并行（无依赖）
                          ┘

P2 Phase (Groups 6-8):
  Group 6 (SQLite)  ──── 先行
  Group 7 (Parts Library) ─┐── 依赖 Group 6
  Group 8 (Preview)       ─┘── 独立于 Group 7
```

## Verification Commands

```bash
# Python tests
uv run pytest tests/ -v

# Linting
uv run ruff check .
uv run ruff format .

# TypeScript
cd frontend && npx tsc --noEmit && npm run lint

# Full integration (backend running)
uv run pytest tests/ -v -k "integration"
```

---

## Phase P0: 管道串联（Groups 1-3）

---

### Task 1: Geometry Extractor — STEP 路径 `[backend]`

**Files:**
- Create: `backend/core/geometry_extractor.py`
- Test: `tests/test_geometry_extractor.py`

**Step 1: Write failing test for STEP extraction**

```python
# tests/test_geometry_extractor.py
import pytest
from unittest.mock import MagicMock, patch

def test_extract_from_step_returns_geometry_info():
    """STEP file extraction returns all required geometry_info fields."""
    from backend.core.geometry_extractor import extract_geometry_from_step

    # Mock CadQuery/OCP — our conftest stubs handle this
    with patch("backend.core.geometry_extractor.cq") as mock_cq:
        # Setup mock workplane with a simple box
        mock_shape = MagicMock()
        mock_shape.BoundingBox.return_value = MagicMock(
            xlen=50.0, ylen=30.0, zlen=20.0
        )
        mock_shape.Volume.return_value = 30000.0  # mm³ = 30 cm³
        mock_wp = MagicMock()
        mock_wp.val.return_value = mock_shape
        mock_cq.importers.importStep.return_value = mock_wp

        result = extract_geometry_from_step("/fake/model.step")

        assert "bounding_box" in result
        assert result["bounding_box"] == {"x": 50.0, "y": 30.0, "z": 20.0}
        assert "volume_cm3" in result
        assert result["volume_cm3"] == pytest.approx(30.0, rel=0.01)
        assert "min_wall_thickness" in result or result.get("min_wall_thickness") is None
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_geometry_extractor.py::test_extract_from_step_returns_geometry_info -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.geometry_extractor'`

**Step 3: Write minimal implementation**

```python
# backend/core/geometry_extractor.py
"""Geometry information extractor for printability analysis.

Provides two paths:
- STEP files: CadQuery/OCP geometric queries (precise B-Rep)
- Mesh files: trimesh analysis (approximate)

Both return a standardized geometry_info dict consumed by PrintabilityChecker.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def extract_geometry_from_step(step_path: str) -> dict[str, Any]:
    """Extract geometry_info from a STEP file using CadQuery/OCP.

    Returns dict with keys:
        bounding_box: {x, y, z} in mm
        min_wall_thickness: float in mm (may be None if analysis fails)
        max_overhang_angle: float in degrees (may be None)
        volume_cm3: float
        min_hole_diameter: float in mm (may be None)
    """
    import cadquery as cq

    wp = cq.importers.importStep(step_path)
    shape = wp.val()
    bb = shape.BoundingBox()
    volume_mm3 = shape.Volume()

    geometry_info: dict[str, Any] = {
        "bounding_box": {
            "x": round(bb.xlen, 2),
            "y": round(bb.ylen, 2),
            "z": round(bb.zlen, 2),
        },
        "volume_cm3": round(volume_mm3 / 1000.0, 4),
        "min_wall_thickness": None,  # TODO: OCP shell analysis
        "max_overhang_angle": None,  # TODO: face normal analysis
        "min_hole_diameter": None,   # TODO: hole detection
    }
    return geometry_info
```

**Step 4: Run test, verify it passes**

```bash
uv run pytest tests/test_geometry_extractor.py -v
```

**Step 5: Commit**

```bash
git add backend/core/geometry_extractor.py tests/test_geometry_extractor.py
git commit -m "feat: add geometry extractor for STEP files (P0.1 Task 1.1)"
```

---

### Task 2: Geometry Extractor — Mesh 路径 `[backend]`

**Files:**
- Modify: `backend/core/geometry_extractor.py`
- Modify: `tests/test_geometry_extractor.py`

**Step 1: Write failing test for mesh extraction**

```python
def test_extract_from_mesh_returns_geometry_info():
    """Mesh extraction returns geometry_info with wall_thickness=None."""
    from backend.core.geometry_extractor import extract_geometry_from_mesh

    with patch("backend.core.geometry_extractor.trimesh") as mock_trimesh:
        mock_mesh = MagicMock()
        mock_mesh.bounds = [[-25, -15, -10], [25, 15, 10]]  # 50x30x20
        mock_mesh.volume = 30000.0
        mock_mesh.is_watertight = True
        mock_trimesh.load.return_value = mock_mesh

        result = extract_geometry_from_mesh("/fake/model.glb")

        assert result["bounding_box"] == {"x": 50.0, "y": 30.0, "z": 20.0}
        assert result["volume_cm3"] == pytest.approx(30.0, rel=0.01)
        # Mesh wall thickness is computationally expensive — allow None
        assert result["min_wall_thickness"] is None
```

**Step 2: Implement mesh extraction**

```python
def extract_geometry_from_mesh(mesh_path: str) -> dict[str, Any]:
    """Extract geometry_info from a mesh file (GLB/STL) using trimesh.

    min_wall_thickness is None for mesh files (computationally expensive).
    """
    import trimesh

    mesh = trimesh.load(mesh_path)
    bounds = mesh.bounds  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
    extents = bounds[1] - bounds[0]

    geometry_info: dict[str, Any] = {
        "bounding_box": {
            "x": round(float(extents[0]), 2),
            "y": round(float(extents[1]), 2),
            "z": round(float(extents[2]), 2),
        },
        "volume_cm3": round(float(mesh.volume) / 1000.0, 4) if mesh.is_watertight else None,
        "min_wall_thickness": None,  # Too expensive for mesh
        "max_overhang_angle": _estimate_max_overhang(mesh),
        "min_hole_diameter": None,
    }
    return geometry_info


def _estimate_max_overhang(mesh: Any) -> Optional[float]:
    """Estimate max overhang angle from face normals."""
    try:
        import numpy as np
        normals = mesh.face_normals
        # Overhang angle = angle between face normal and -Z axis
        z_axis = np.array([0, 0, -1])
        cos_angles = np.dot(normals, z_axis)
        angles_deg = np.degrees(np.arccos(np.clip(cos_angles, -1, 1)))
        # Only consider downward-facing faces (angle < 90 from -Z)
        downward = angles_deg[angles_deg < 90]
        return round(float(np.max(downward)), 1) if len(downward) > 0 else 0.0
    except Exception:
        return None
```

**Step 3: Run tests, commit**

```bash
uv run pytest tests/test_geometry_extractor.py -v
git add backend/core/geometry_extractor.py tests/test_geometry_extractor.py
git commit -m "feat: add mesh geometry extraction with trimesh (P0.1 Task 1.2)"
```

---

### Task 3: Printability Pipeline Integration — Precision Path `[backend]`

**Files:**
- Modify: `backend/api/generate.py:358-458` (confirm_params → completed event)
- Modify: `backend/pipeline/sse_bridge.py:79-93` (complete method)
- Reference: `backend/core/printability.py:117-476`

**Step 1: Write failing test**

```python
# tests/test_generate_api.py — add new test
@pytest.mark.asyncio
async def test_completed_event_includes_printability(client, monkeypatch):
    """SSE completed event should include printability field."""
    # ... mock pipeline, geometry extractor, printability checker ...
    events = parse_sse_events(response.text)
    completed = [e for e in events if e.get("status") == "completed"][0]
    assert "printability" in completed
    assert completed["printability"]["printable"] is not None
    assert "material_estimate" in completed["printability"]
    assert "time_estimate" in completed["printability"]
```

**Step 2: Implement in API layer**

Add to `backend/api/generate.py` after STEP generation succeeds, before yielding `completed`:

```python
# After successful STEP generation, run printability check
from backend.core.geometry_extractor import extract_geometry_from_step
from backend.core.printability import PrintabilityChecker

printability_data = None
try:
    geometry_info = extract_geometry_from_step(step_path)
    checker = PrintabilityChecker()
    result = checker.check(geometry_info)
    mat = checker.estimate_material(geometry_info)
    time = checker.estimate_print_time(geometry_info)
    result.material_estimate = {
        "filament_weight_g": mat.filament_weight_g,
        "filament_length_m": mat.filament_length_m,
        "cost_estimate_cny": mat.cost_estimate_cny,
    }
    result.time_estimate = {
        "total_minutes": time.total_minutes,
        "layer_count": time.layer_count,
    }
    printability_data = result.model_dump()
except Exception as e:
    logger.warning(f"Printability check failed: {e}")
    printability_data = None

# Include in completed SSE event
yield _sse("completed", {
    "job_id": job_id,
    ...,
    "printability": printability_data,
})
```

**Step 3: Run tests, commit**

```bash
uv run pytest tests/test_generate_api.py -v -k "printability"
git add backend/api/generate.py tests/test_generate_api.py
git commit -m "feat: integrate PrintabilityChecker into precision path (P0.1 Task 1.4)"
```

---

### Task 4: Printability Pipeline Integration — Organic Path `[backend]`

**Files:**
- Modify: `backend/api/organic.py:270-280` (completed event)
- Test: `tests/test_organic_api.py`

Same pattern as Task 3 but using `extract_geometry_from_mesh()` on the GLB/STL output. Add to `backend/api/organic.py` before the completed event yield.

```python
# In organic.py, before completed event
from backend.core.geometry_extractor import extract_geometry_from_mesh
from backend.core.printability import PrintabilityChecker

printability_data = None
try:
    mesh_path = str(stl_path) if stl_path else str(glb_path)
    geometry_info = extract_geometry_from_mesh(mesh_path)
    checker = PrintabilityChecker()
    result = checker.check(geometry_info)
    mat = checker.estimate_material(geometry_info)
    time_est = checker.estimate_print_time(geometry_info)
    result.material_estimate = {...}
    result.time_estimate = {...}
    printability_data = result.model_dump()
except Exception as e:
    logger.warning(f"Organic printability check failed: {e}")

yield _sse_event(job_id, "completed", ..., printability=printability_data)
```

**Commit:**
```bash
git commit -m "feat: integrate PrintabilityChecker into organic path (P0.1 Task 1.5)"
```

---

### Task 5: Printability Error Tolerance `[backend]`

**Files:**
- Modify: `backend/api/generate.py`
- Modify: `backend/api/organic.py`

Already implemented via `try/except` in Tasks 3-4. Verify with test:

```python
def test_printability_failure_returns_null(client, monkeypatch):
    """Checker exception should not block generation result."""
    monkeypatch.setattr(
        "backend.core.geometry_extractor.extract_geometry_from_step",
        lambda _: (_ for _ in ()).throw(RuntimeError("OCP crash")),
    )
    # ... trigger generation ...
    completed = [e for e in events if e["status"] == "completed"][0]
    assert completed["printability"] is None
```

**Commit:**
```bash
git commit -m "feat: add printability error tolerance (P0.1 Task 1.6)"
```

---

### Task 6: Frontend PrintReport Real Data `[frontend]`

**Files:**
- Modify: `frontend/src/components/PrintReport/index.tsx`
- Modify: `frontend/src/pages/Generate/GenerateWorkflow.tsx:291-342` (SSE handler)
- Modify: `frontend/src/pages/OrganicGenerate/OrganicWorkflow.tsx:63-123` (SSE handler)

**Step 1: Parse printability from SSE completed event**

In `GenerateWorkflow.tsx` `handleSSEEvent()`:
```typescript
case 'completed': {
  const printability = evt.printability ?? null;
  setState(prev => ({
    ...prev,
    phase: 'completed',
    modelUrl: evt.model_url,
    stepPath: evt.step_path,
    printability,  // NEW: pass to state
  }));
  break;
}
```

Add `printability: PrintabilityResult | null` to `WorkflowState` in `frontend/src/types/generate.ts`.

**Step 2: Render PrintReport with material/time estimates**

Update `PrintReport` component to display:
- Material: weight (g), length (m), cost (CNY)
- Time: total minutes, layer count
- Use `Statistic` from antd for clean number display

**Step 3: TypeScript check + commit**

```bash
cd frontend && npx tsc --noEmit
git commit -m "feat: connect PrintReport to real SSE data (P0.1 Task 1.7)"
```

---

### Task 7: Drawing Path HITL — Job Model Changes `[backend]`

**Files:**
- Modify: `backend/models/job.py:20-30` (JobStatus enum)
- Modify: `backend/models/job.py:33-47` (Job model fields)
- Test: existing model tests

**Step 1: Add fields and status**

```python
# backend/models/job.py

class JobStatus(str, Enum):
    CREATED = "created"
    INTENT_PARSED = "intent_parsed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    AWAITING_DRAWING_CONFIRMATION = "awaiting_drawing_confirmation"  # NEW
    GENERATING = "generating"
    REFINING = "refining"
    COMPLETED = "completed"
    FAILED = "failed"
    VALIDATION_FAILED = "validation_failed"


class Job(BaseModel):
    # ... existing fields ...
    drawing_spec: Optional[dict[str, Any]] = None          # NEW: original AI-extracted
    drawing_spec_confirmed: Optional[dict[str, Any]] = None  # NEW: user-confirmed
    image_path: Optional[str] = None                       # NEW: original drawing path
```

**Commit:**
```bash
git commit -m "feat: add drawing_spec fields and AWAITING_DRAWING_CONFIRMATION status (P0.2 Task 2.1)"
```

---

### Task 8: Pipeline Split — analyze_drawing() + generate_from_drawing_spec() `[backend]`

**Files:**
- Modify: `backend/pipeline/pipeline.py:132-348`
- Modify: `backend/api/generate.py:234-350`
- Modify: `backend/pipeline/sse_bridge.py`
- Test: `tests/test_generate_api.py`

This is the largest single task. Break into sub-steps:

**Step 1: Extract `analyze_drawing()` from pipeline.py**

```python
# backend/pipeline/pipeline.py — NEW function

def analyze_drawing(
    image_filepath: str,
    on_progress: Callable | None = None,
    config: PipelineConfig | None = None,
) -> DrawingSpec:
    """Stage 1 only: VL drawing analysis → DrawingSpec.

    This is the first half of the HITL pipeline split (D8).
    Returns the DrawingSpec for user review before proceeding.
    """
    config = config or PRESETS["balanced"]
    image_data = ImageData.load_from_file(image_filepath)

    # DrawingAnalyzerChain is a LangChain SequentialChain — use .invoke()
    analyzer = DrawingAnalyzerChain(
        model_type=config.vl_model,
        temperature=config.vl_temperature,
    )
    result = analyzer.invoke({"image": image_data})
    spec: DrawingSpec = result["drawing_spec"]

    if on_progress:
        on_progress("spec_extracted", {"spec": spec.model_dump()})

    return spec
```

**Step 2: Extract `generate_from_drawing_spec()`**

```python
def generate_from_drawing_spec(
    image_filepath: str,
    drawing_spec: DrawingSpec,
    output_filepath: str,
    num_refinements: int | None = None,
    on_spec_ready: Callable | None = None,
    on_progress: Callable | None = None,
    config: PipelineConfig | None = None,
) -> str:
    """Stage 1.5-4: strategy → code gen → execute → refine.

    This is the second half of the HITL pipeline split (D8).
    Requires original image_filepath for Stage 4 SmartRefiner VL comparison.
    """
    config = config or PRESETS["balanced"]
    image_data = ImageData.from_filepath(image_filepath)

    # Stage 1.5: Strategy selection
    strategist = ModelingStrategist()
    context = strategist.select(drawing_spec)  # .select() not .select_strategy()
    # ... Stage 2-4 (same as current generate_step_v2 lines 200-348) ...
```

**Step 3: Update `/generate/drawing` route in generate.py**

```python
# backend/api/generate.py — modified drawing route
async def generate_drawing(...):
    async def event_generator():
        yield _sse("job_created", {"job_id": job_id})

        # Stage 1 only — analyze drawing
        spec = await asyncio.to_thread(
            analyze_drawing, image_path, config=pipeline_config
        )

        # Save original DrawingSpec to Job
        update_job(job_id,
            status=JobStatus.AWAITING_DRAWING_CONFIRMATION,
            drawing_spec=spec.model_dump(),
            image_path=image_path,
        )

        # Emit drawing_spec_ready event (end first SSE stream)
        yield _sse("drawing_spec_ready", {
            "job_id": job_id,
            "drawing_spec": spec.model_dump(),
        })
        # Stream ends here — user must call /confirm to continue

    return EventSourceResponse(event_generator())
```

**Step 4: Add SSE bridge support for `drawing_spec_ready`**

```python
# backend/pipeline/sse_bridge.py — add to _STAGE_TO_EVENT
_STAGE_TO_EVENT["drawing_spec_ready"] = "drawing_spec_ready"
```

**Step 5: Test the split**

```python
@pytest.mark.asyncio
async def test_drawing_route_pauses_after_spec(client, monkeypatch):
    """Drawing route should emit drawing_spec_ready and stop."""
    mock_spec = DrawingSpec(part_type="ROTATIONAL", ...)
    monkeypatch.setattr("backend.api.generate.analyze_drawing", lambda *a, **kw: mock_spec)

    response = client.post("/api/generate/drawing", files={"image": ...})
    events = parse_sse_events(response.text)

    statuses = [e["status"] for e in events if "status" in e]
    assert "drawing_spec_ready" in statuses
    assert "completed" not in statuses  # Should NOT complete yet!

    # Verify job status
    job = get_job(events[0]["job_id"])
    assert job.status == JobStatus.AWAITING_DRAWING_CONFIRMATION
    assert job.drawing_spec is not None
```

**Commit:**
```bash
git commit -m "feat: split drawing pipeline — analyze_drawing() + generate_from_drawing_spec() (P0.2 Task 2.2)"
```

---

### Task 9: Drawing Confirm Endpoint `[backend]`

**Files:**
- Modify: `backend/api/generate.py` (add POST /generate/drawing/{job_id}/confirm)
- Test: `tests/test_generate_api.py`

**Step 1: Implement confirm endpoint**

```python
class DrawingConfirmRequest(BaseModel):
    confirmed_spec: dict[str, Any]
    disclaimer_accepted: bool


@router.post("/generate/drawing/{job_id}/confirm")
async def confirm_drawing_spec(
    job_id: str, body: DrawingConfirmRequest
) -> EventSourceResponse:
    job = get_job(job_id)
    if not job or job.status != JobStatus.AWAITING_DRAWING_CONFIRMATION:
        raise HTTPException(404, "Job not found or not awaiting confirmation")

    if not body.disclaimer_accepted:
        raise HTTPException(400, "免责声明必须接受后方可继续生成")

    # Save confirmed spec
    update_job(job_id,
        drawing_spec_confirmed=body.confirmed_spec,
        status=JobStatus.GENERATING,
    )

    async def event_generator():
        bridge = PipelineBridge(job_id)  # Initialize SSE bridge for Stage 2
        try:
            confirmed_spec = DrawingSpec(**body.confirmed_spec)
            image_path = job.image_path  # Restored from Job record

            # Resume Stage 1.5-4
            step_path = await asyncio.to_thread(
                generate_from_drawing_spec,
                image_filepath=image_path,
                drawing_spec=confirmed_spec,
                output_filepath=f"outputs/{job_id}/model.step",
                on_progress=bridge.on_progress,
            )
            # ... convert to GLB, emit completed with printability ...
        except Exception as e:
            yield _sse("failed", {"job_id": job_id, "error": str(e)})

    return EventSourceResponse(event_generator())
```

**Step 2: Test confirm → resume → completed**

```python
@pytest.mark.asyncio
async def test_drawing_confirm_resumes_generation(client, monkeypatch):
    """Confirming DrawingSpec should resume pipeline and complete."""
    # Setup: create job in AWAITING_DRAWING_CONFIRMATION state
    # ... mock generate_from_drawing_spec ...
    response = client.post(f"/api/generate/drawing/{job_id}/confirm", json={
        "confirmed_spec": {...},
        "disclaimer_accepted": True,
    })
    events = parse_sse_events(response.text)
    assert any(e.get("status") == "completed" for e in events)
```

**Commit:**
```bash
git commit -m "feat: add drawing confirm endpoint with pipeline resume (P0.2 Task 2.3)"
```

---

### Task 10: User Correction Data + JSON Persistence `[backend]`

**Files:**
- Create: `backend/core/correction_tracker.py`
- Create: `backend/data/corrections/` (directory)
- Test: `tests/test_correction_tracker.py`

**Implementation:**

```python
# backend/core/correction_tracker.py
"""Field-level correction tracking for DrawingSpec HITL data flywheel."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CORRECTIONS_DIR = Path(__file__).parent.parent / "data" / "corrections"


def compute_corrections(
    original: dict[str, Any],
    confirmed: dict[str, Any],
    job_id: str,
) -> list[dict[str, Any]]:
    """Compare original and confirmed DrawingSpec, return field-level diffs."""
    corrections = []
    _diff_recursive(original, confirmed, "", corrections, job_id)
    return corrections


def _diff_recursive(
    orig: Any, conf: Any, path: str,
    corrections: list, job_id: str,
) -> None:
    if isinstance(orig, dict) and isinstance(conf, dict):
        for key in set(list(orig.keys()) + list(conf.keys())):
            _diff_recursive(
                orig.get(key), conf.get(key),
                f"{path}.{key}" if path else key,
                corrections, job_id,
            )
    elif orig != conf:
        corrections.append({
            "job_id": job_id,
            "field_path": path,
            "original_value": str(orig),
            "corrected_value": str(conf),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def persist_corrections(job_id: str, corrections: list[dict]) -> Path:
    """Persist corrections to JSON file. MANDATORY — not optional."""
    CORRECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = CORRECTIONS_DIR / f"{job_id}.json"
    path.write_text(json.dumps(corrections, ensure_ascii=False, indent=2))
    logger.info(f"Persisted {len(corrections)} corrections to {path}")
    return path
```

Wire into `confirm_drawing_spec()`:

```python
from backend.core.correction_tracker import compute_corrections, persist_corrections

# In confirm endpoint, after saving confirmed_spec:
if job.drawing_spec and body.confirmed_spec:
    corrections = compute_corrections(job.drawing_spec, body.confirmed_spec, job_id)
    if corrections:
        persist_corrections(job_id, corrections)
```

**Commit:**
```bash
git commit -m "feat: add correction tracking with mandatory JSON persistence (P0.2 Task 2.4)"
```

---

### Task 11: DrawingSpecReview Frontend Component `[frontend]`

**Files:**
- Create: `frontend/src/pages/Generate/DrawingSpecReview.tsx`
- Modify: `frontend/src/types/generate.ts`

**Component structure (layered per Gemini review P1):**

```typescript
// frontend/src/pages/Generate/DrawingSpecReview.tsx
import { Card, Form, InputNumber, Select, Checkbox, Button, Tag, Collapse, Alert } from 'antd';

interface DrawingSpecReviewProps {
  drawingSpec: DrawingSpec;
  onConfirm: (spec: DrawingSpec, disclaimerAccepted: boolean) => void;
  onCancel: () => void;
}

export default function DrawingSpecReview({ drawingSpec, onConfirm, onCancel }: DrawingSpecReviewProps) {
  const [form] = Form.useForm();
  const [disclaimerAccepted, setDisclaimerAccepted] = useState(false);

  return (
    <Card title="AI 图纸分析结果确认">
      {/* Top: Part type + confidence */}
      <div>
        <Select value={drawingSpec.part_type} options={PART_TYPE_OPTIONS} />
        <Tag color={confidence > 0.8 ? 'green' : 'orange'}>
          AI 置信度: {(confidence * 100).toFixed(0)}%
        </Tag>
      </div>

      {/* Middle: Editable dimensions table */}
      <Form form={form} initialValues={drawingSpec.overall_dimensions}>
        {Object.entries(drawingSpec.overall_dimensions).map(([key, value]) => (
          <Form.Item key={key} name={key} label={key}>
            <InputNumber precision={2} />
          </Form.Item>
        ))}
      </Form>

      {/* Middle: Base body params */}
      <Card size="small" title="基体参数">
        {/* base_body editor based on method type */}
      </Card>

      {/* Bottom: Features list (collapsible) */}
      <Collapse>
        {drawingSpec.features.map((feat, i) => (
          <Collapse.Panel key={i} header={feat.type}>
            {/* Feature params + delete button */}
          </Collapse.Panel>
        ))}
      </Collapse>

      {/* Disclaimer */}
      <Alert type="warning" message="AI 识别结果仅供参考" description="..." />
      <Checkbox checked={disclaimerAccepted} onChange={...}>
        我已确认以上信息，了解 AI 识别可能存在误差
      </Checkbox>

      <Button type="primary" disabled={!disclaimerAccepted} onClick={handleConfirm}>
        确认并生成
      </Button>
    </Card>
  );
}
```

**Commit:**
```bash
cd frontend && npx tsc --noEmit
git commit -m "feat: add DrawingSpecReview component with layered editing UI (P0.2 Task 2.5)"
```

---

### Task 12: Frontend SSE — Drawing Path HITL Flow `[frontend]`

**Files:**
- Modify: `frontend/src/pages/Generate/GenerateWorkflow.tsx:291-342`
- Modify: `frontend/src/types/generate.ts`

**Step 1: Add drawing_spec_ready handling**

```typescript
// In handleSSEEvent()
case 'drawing_spec_ready': {
  setState(prev => ({
    ...prev,
    phase: 'drawing_review',  // NEW phase
    drawingSpec: evt.drawing_spec,
  }));
  break;
}
```

**Step 2: Add confirmDrawingSpec method**

```typescript
const confirmDrawingSpec = async (confirmedSpec: DrawingSpec, disclaimerAccepted: boolean) => {
  const response = await fetch(`/api/generate/drawing/${state.jobId}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmed_spec: confirmedSpec, disclaimer_accepted: disclaimerAccepted }),
  });
  // Connect second SSE stream
  consumeSSE(response, handleSSEEvent);
  setState(prev => ({ ...prev, phase: 'generating' }));
};
```

**Step 3: Render DrawingSpecReview when phase is `drawing_review`**

```typescript
{state.phase === 'drawing_review' && state.drawingSpec && (
  <DrawingSpecReview
    drawingSpec={state.drawingSpec}
    onConfirm={confirmDrawingSpec}
    onCancel={reset}
  />
)}
```

**Commit:**
```bash
git commit -m "feat: connect drawing HITL flow in frontend SSE handler (P0.2 Task 2.6)"
```

---

### Task 13: Organic 3MF Export `[backend]`

**Files:**
- Modify: `backend/api/organic.py:255-280` (export section)

**Step 1: Add 3MF export after STL**

```python
# In organic.py, after STL export
import datetime

threemf_path = output_dir / "model.3mf"
try:
    # trimesh 3MF export with metadata
    mesh.export(str(threemf_path), file_type="3mf")
    # Add metadata via 3MF library if available, otherwise basic export
    threemf_url = f"/outputs/{job_id}/model.3mf"
except Exception as e:
    logger.warning(f"3MF export failed: {e}")
    threemf_url = None

yield _sse_event(job_id, "completed", ..., threemf_url=threemf_url)
```

**Step 2: Verify frontend 3MF download**

The frontend `OrganicWorkflow.tsx` already has `threemfUrl` in state — just verify it renders a download button when non-null.

**Commit:**
```bash
git commit -m "feat: add 3MF export with metadata for organic path (P0.3 Task 3.1-3.2)"
```

---

## Phase P1: 智能层（Groups 4-5）

---

### Task 14: PaddleOCR Dependency + Engine Wrapper `[backend]`

**Files:**
- Modify: `pyproject.toml` (add optional dependency)
- Create: `backend/core/ocr_engine.py`
- Test: `tests/test_ocr_engine.py`

**Step 1: Add dependency**

```toml
# pyproject.toml
[project.optional-dependencies]
ocr = ["paddleocr>=2.9.0", "paddlepaddle>=3.0.0"]
```

**Step 2: Create wrapper**

```python
# backend/core/ocr_engine.py
"""PaddleOCR engine wrapper, adapting to ocr_fn: Callable interface."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_paddle_ocr: Optional[object] = None


def get_ocr_fn():
    """Return OCR function matching Callable[[bytes], list[OCRResult]] interface.

    Returns empty-list function if PaddleOCR is not available.
    """
    def _ocr_unavailable(image_bytes: bytes) -> list:
        return []

    try:
        from paddleocr import PaddleOCR
        global _paddle_ocr
        if _paddle_ocr is None:
            _paddle_ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

        def _paddle_ocr_fn(image_bytes: bytes) -> list:
            import tempfile
            from pathlib import Path
            from backend.core.ocr_assist import OCRResult
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(image_bytes)
                tmp_path = f.name
            try:
                result = _paddle_ocr.ocr(tmp_path, cls=True)
                if not result or not result[0]:
                    return []
                return [
                    OCRResult(text=line[1][0], confidence=line[1][1], bbox=line[0])
                    for line in result[0]
                ]
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        return _paddle_ocr_fn

    except ImportError:
        logger.info("PaddleOCR not available, OCR disabled")
        return _ocr_unavailable
```

**Step 3: Test with mock**

```python
def test_ocr_fn_returns_list_on_success(monkeypatch):
    monkeypatch.setattr("backend.core.ocr_engine.PaddleOCR", MockPaddleOCR)
    fn = get_ocr_fn()
    result = fn(b"fake_image_bytes")
    assert isinstance(result, list)

def test_ocr_fn_returns_empty_when_unavailable(monkeypatch):
    monkeypatch.setattr("backend.core.ocr_engine.PaddleOCR", None)  # simulate ImportError
    fn = get_ocr_fn()
    assert fn(b"bytes") == []
```

**Commit:**
```bash
git commit -m "feat: add PaddleOCR engine wrapper with graceful fallback (P1.1 Task 4.1-4.3)"
```

---

### Task 15: OCR-VLM Fusion in DrawingAnalyzer `[backend]`

**Files:**
- Modify: `backend/core/drawing_analyzer.py` (Stage 1 VLM analysis)
- Reference: `backend/core/ocr_assist.py:108-150` (merge_ocr_with_vl)
- Test: `tests/test_drawing_analyzer.py`

**Step 1: Inject OCR after VLM analysis**

```python
# In DrawingAnalyzerChain.analyze() — after VLM produces DrawingSpec
from backend.core.ocr_engine import get_ocr_fn
from backend.core.ocr_assist import OCRAssistant, merge_ocr_with_vl

# Run OCR in parallel
ocr_fn = get_ocr_fn()
assistant = OCRAssistant(ocr_fn)
ocr_dims = assistant.extract_dimensions(image_data.to_bytes())

# Merge: OCR overrides VLM for numeric fields
if ocr_dims:
    merged, confidences = merge_ocr_with_vl(
        ocr_dims={d.label: d.value for d in ocr_dims},
        vl_dims=spec.overall_dimensions,
    )
    spec.overall_dimensions = merged
```

**Step 2: Test fusion priority rules**

```python
def test_ocr_overrides_vl_for_numeric_fields():
    """When OCR and VLM disagree on a number, OCR wins."""
    merged, conf = merge_ocr_with_vl(
        ocr_dims={"diameter": 50.0},
        vl_dims={"diameter": 48.0, "height": 30.0},
    )
    assert merged["diameter"] == 50.0  # OCR wins
    assert merged["height"] == 30.0    # VLM only
    assert conf["diameter"] == 0.7     # Disagreement confidence
```

**Commit:**
```bash
git commit -m "feat: integrate OCR-VLM fusion into drawing analyzer (P1.1 Task 4.4-4.5)"
```

---

### Task 16: IntentParser Replacement `[backend]`

**Files:**
- Modify: `backend/api/generate.py:99-124` (_match_template → IntentParser)
- Reference: `backend/core/intent_parser.py:128-168` (parse method)
- Test: `tests/test_generate_api.py`

**Step 1: Wire IntentParser with llm_callable**

```python
# backend/api/generate.py — module-level setup
from backend.core.intent_parser import IntentParser

_intent_parser: Optional[IntentParser] = None

def _get_intent_parser() -> IntentParser:
    global _intent_parser
    if _intent_parser is None:
        from backend.infra.chat_models import create_chat_model
        llm = create_chat_model("qwen-coder-plus")

        async def llm_callable(prompt, schema):
            # Adapt LangChain chat model to IntentParser's expected interface
            response = await llm.ainvoke(prompt)
            return schema.model_validate_json(response.content)

        _intent_parser = IntentParser(llm_callable=llm_callable)
    return _intent_parser
```

**Step 2: Replace _match_template with IntentParser + fallback**

```python
# In text generate route
try:
    parser = _get_intent_parser()
    intent = await parser.parse(body.text)
    if intent.confidence > 0.7 and intent.part_type:
        template, params = _match_template_by_intent(intent)
        if template:
            # Track A: parametric template
            ...
        else:
            # Track B: LLM code generation
            ...
    else:
        # Low confidence → Track B
        ...
except Exception:
    # Fallback: original keyword matching
    template, params = _match_template(body.text)
```

**Step 3: Test three scenarios**

```python
def test_intent_parser_high_confidence_routes_to_template(...)
def test_intent_parser_low_confidence_falls_back(...)
def test_intent_parser_failure_degrades_to_keyword_matching(...)
```

**Commit:**
```bash
git commit -m "feat: replace keyword matching with IntentParser + graceful fallback (P1.2 Task 5.1-5.4)"
```

---

## Phase P2: 数据基础设施（Groups 6-8）

---

### Task 17: SQLite + SQLAlchemy Setup `[backend]`

**Files:**
- Modify: `pyproject.toml` (add dependencies)
- Create: `backend/db/__init__.py`
- Create: `backend/db/database.py`

**Step 1: Add dependencies**

```toml
# pyproject.toml — add to existing [project] dependencies array:
# dependencies = [
#   ...existing...,
#   "sqlalchemy[asyncio]>=2.0.0",
#   "aiosqlite>=0.20.0",
#   "alembic>=1.14.0",
# ]
```

```bash
uv sync
```

**Step 2: Create database module**

```python
# backend/db/database.py
"""Async SQLAlchemy engine and session factory for SQLite."""
from __future__ import annotations

from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DB_PATH = Path(__file__).parent.parent / "data" / "cad3dify.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    DATABASE_URL,
    connect_args={"timeout": 30},  # busy timeout (D2)
    pool_pre_ping=True,
    echo=False,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables. Called on startup."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
```

**Commit:**
```bash
git commit -m "feat: add SQLite + SQLAlchemy async engine setup (P2.1 Task 6.1-6.2)"
```

---

### Task 18: ORM Models `[backend]`

**Files:**
- Create: `backend/db/models.py`

```python
# backend/db/models.py
"""SQLAlchemy ORM models for Job, OrganicJob, and UserCorrection."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.database import Base


class JobModel(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    input_type: Mapped[str] = mapped_column(String(16), default="text")
    input_text: Mapped[str] = mapped_column(Text, default="")
    intent: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    precise_spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    drawing_spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    drawing_spec_confirmed: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    printability_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class OrganicJobModel(Base):
    __tablename__ = "organic_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    prompt: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(32), default="auto")
    quality_mode: Mapped[str] = mapped_column(String(16), default="standard")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    printability_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class UserCorrectionModel(Base):
    __tablename__ = "user_corrections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    field_path: Mapped[str] = mapped_column(String(256))
    original_value: Mapped[str] = mapped_column(Text)
    corrected_value: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
```

**Commit:**
```bash
git commit -m "feat: add SQLAlchemy ORM models for Job, OrganicJob, UserCorrection (P2.1 Task 6.3)"
```

---

### Task 19: Repository Layer `[backend]`

**Files:**
- Create: `backend/db/repository.py`
- Test: `tests/test_repository.py`

**Implementation:** Async CRUD for all three models with pagination support. Follow the pattern in `backend/models/job.py` but using SQLAlchemy sessions.

```python
# backend/db/repository.py
async def create_job(session: AsyncSession, job_id: str, **kwargs) -> JobModel: ...
async def get_job(session: AsyncSession, job_id: str) -> JobModel | None: ...
async def update_job(session: AsyncSession, job_id: str, **kwargs) -> JobModel: ...
async def list_jobs(session: AsyncSession, page: int = 1, page_size: int = 20,
                    status: str | None = None, input_type: str | None = None) -> tuple[list[JobModel], int]: ...
async def create_organic_job(session: AsyncSession, job_id: str, **kwargs) -> OrganicJobModel: ...
# ... similar for organic jobs and corrections ...
```

**Commit:**
```bash
git commit -m "feat: add async repository layer with CRUD + pagination (P2.1 Task 6.4)"
```

---

### Task 20: Alembic Setup `[backend]`

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/001_initial.py`

```bash
uv run alembic init alembic
# Edit alembic.ini: sqlalchemy.url = sqlite+aiosqlite:///backend/data/cad3dify.db
# Edit env.py to use async engine
uv run alembic revision --autogenerate -m "initial: jobs, organic_jobs, user_corrections"
uv run alembic upgrade head
```

**Commit:**
```bash
git commit -m "feat: configure Alembic with initial migration (P2.1 Task 6.5)"
```

---

### Task 21: Refactor In-Memory → Repository `[backend]`

**Files:**
- Modify: `backend/models/job.py` (replace dict with repository)
- Modify: `backend/models/organic_job.py` (same)
- Modify: `backend/api/generate.py` (use async session)
- Modify: `backend/api/organic.py` (use async session)

Keep function signatures identical (`create_job`, `get_job`, etc.) but internally delegate to repository. Add FastAPI dependency injection for `AsyncSession`.

**Commit:**
```bash
git commit -m "refactor: replace in-memory job stores with SQLite repository (P2.1 Task 6.6)"
```

---

### Task 22: Corrections Migration Script `[backend]`

**Files:**
- Create: `scripts/migrate_corrections.py`

```python
"""One-time migration: JSON file corrections → SQLite."""
import asyncio
import json
from pathlib import Path
from backend.db.database import async_session, init_db
from backend.db.repository import create_correction

CORRECTIONS_DIR = Path("backend/data/corrections")

async def migrate():
    await init_db()
    async with async_session() as session:
        for json_file in CORRECTIONS_DIR.glob("*.json"):
            corrections = json.loads(json_file.read_text())
            for c in corrections:
                await create_correction(session, **c)
            await session.commit()

if __name__ == "__main__":
    asyncio.run(migrate())
```

**Commit:**
```bash
git commit -m "feat: add corrections JSON → SQLite migration script (P2.1 Task 6.7)"
```

---

### Task 23: Repository Tests `[test]`

**Files:**
- Create: `tests/test_repository.py`

```python
@pytest.mark.asyncio
async def test_create_and_get_job():
    """Job CRUD lifecycle."""
    async with test_session() as session:
        job = await create_job(session, "test-1", input_type="text")
        assert job.job_id == "test-1"
        fetched = await get_job(session, "test-1")
        assert fetched is not None

@pytest.mark.asyncio
async def test_list_jobs_pagination():
    """Pagination returns correct page."""
    # Create 25 jobs, list page 2 with page_size=10
    jobs, total = await list_jobs(session, page=2, page_size=10)
    assert len(jobs) == 10
    assert total == 25

@pytest.mark.asyncio
async def test_organic_job_crud():
    """OrganicJob CRUD lifecycle."""
    ...

@pytest.mark.asyncio
async def test_job_persists_after_engine_dispose():
    """Simulate process restart: dispose engine, recreate, verify data survives."""
    async with test_session() as session:
        await create_job(session, "persist-test", input_type="drawing")
    # Dispose engine (simulates process exit)
    await engine.dispose()
    # Recreate engine + session (simulates process restart)
    new_engine = create_async_engine(DATABASE_URL, connect_args={"timeout": 30})
    new_session_factory = async_sessionmaker(new_engine, class_=AsyncSession)
    async with new_session_factory() as session:
        fetched = await get_job(session, "persist-test")
        assert fetched is not None
        assert fetched.input_type == "drawing"
    await new_engine.dispose()
```

**Commit:**
```bash
git commit -m "test: add repository layer unit tests (P2.1 Task 6.8-6.9)"
```

---

### Task 24: History API Endpoints `[backend]`

**Files:**
- Create: `backend/api/history.py`
- Modify: `backend/main.py` (register router)

```python
# backend/api/history.py
router = APIRouter(prefix="/jobs", tags=["history"])  # Note: /api prefix added by main.py

@router.get("")
async def list_jobs(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    input_type: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse: ...

@router.get("/{job_id}")
async def get_job_detail(job_id: str, session: ...) -> JobDetail: ...

@router.post("/{job_id}/regenerate")
async def regenerate_job(job_id: str, session: ...) -> dict: ...

@router.delete("/{job_id}")
async def delete_job(job_id: str, session: ...) -> dict: ...
```

**Commit:**
```bash
git commit -m "feat: add history API endpoints — list, detail, regenerate, delete (P2.2 Task 7.1-7.3)"
```

---

### Task 25: History Frontend — HistoryPage `[frontend]`

**Files:**
- Create: `frontend/src/pages/History/HistoryPage.tsx`
- Create: `frontend/src/pages/History/JobDetailPage.tsx`
- Modify: `frontend/src/App.tsx` (add routes)
- Modify: `frontend/src/components/Layout/` (add nav entry)

**HistoryPage:**
- Card grid with thumbnail (GLB screenshot or placeholder), part name, timestamp, status badge
- Pagination via antd `Pagination`
- Status filter via `Select`

**JobDetailPage:**
- Three.js model viewer (reuse existing `ModelViewer` component)
- Parameter detail card
- `PrintReport` component
- Download buttons (STEP/STL/3MF/GLB)
- "改参数重生成" button → navigate to generate page with pre-filled params

**Routes:**
```typescript
<Route path="/history" element={<HistoryPage />} />
<Route path="/history/:jobId" element={<JobDetailPage />} />
```

**Commit:**
```bash
git commit -m "feat: add parts library history page with detail view (P2.2 Task 7.4-7.7)"
```

---

### Task 26: Preview API `[backend]`

**Files:**
- Create: `backend/api/preview.py`
- Modify: `backend/main.py` (register router)
- Test: `tests/test_preview_api.py`

```python
# backend/api/preview.py
import asyncio
import hashlib
import json
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/preview", tags=["preview"])  # Note: /api prefix added by main.py

_preview_cache: dict[str, str] = {}  # (template_name, params_hash) → glb_url

@router.post("/parametric")
async def preview_parametric(body: PreviewRequest) -> PreviewResponse:
    # 1. Validate params against template constraints
    template = get_template(body.template_name)
    if not template:
        raise HTTPException(404, f"Template '{body.template_name}' not found")

    violations = template.validate_params(body.params)
    if violations:
        raise HTTPException(422, detail=violations)

    # 2. Check cache
    params_hash = hashlib.md5(json.dumps(body.params, sort_keys=True).encode()).hexdigest()
    cache_key = f"{body.template_name}:{params_hash}"
    if cache_key in _preview_cache:
        return PreviewResponse(glb_url=_preview_cache[cache_key])

    # 3. Render + Execute with 5s timeout
    try:
        glb_url = await asyncio.wait_for(
            asyncio.to_thread(_render_preview, body.template_name, body.params),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(408, "预览超时，请直接生成完整模型")

    _preview_cache[cache_key] = glb_url
    return PreviewResponse(glb_url=glb_url)


def invalidate_preview_cache(template_name: str | None = None) -> int:
    """Invalidate preview cache entries. Returns count of removed entries.

    Args:
        template_name: If provided, only invalidate entries for this template.
                       If None, clear entire cache.
    """
    if template_name is None:
        count = len(_preview_cache)
        _preview_cache.clear()
        return count
    keys_to_remove = [k for k in _preview_cache if k.startswith(f"{template_name}:")]
    for k in keys_to_remove:
        del _preview_cache[k]
    return len(keys_to_remove)


def _render_preview(template_name: str, params: dict) -> str:
    """Render template → CadQuery execute (draft quality) → STEP → GLB."""
    # Use reduced tessellation for draft quality (~70% fewer faces)
    # ... TemplateEngine render → CadQuery → STEP → GLB ...
    pass
```

**Commit:**
```bash
git commit -m "feat: add parametric preview API with cache and timeout (P2.3 Task 8.1-8.4)"
```

---

### Task 27: Frontend Preview Integration `[frontend]`

**Files:**
- Modify: `frontend/src/pages/Generate/ParamForm.tsx`
- Reference: existing Three.js viewer component

**Step 1: Debounced preview trigger**

```typescript
// In ParamForm.tsx
import { useDebouncedCallback } from 'use-debounce';

const triggerPreview = useDebouncedCallback(async (params: Record<string, number>) => {
  setPreviewLoading(true);
  try {
    const res = await fetch('/api/preview/parametric', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template_name: templateName, params }),
    });
    if (res.ok) {
      const data = await res.json();
      // Hot-swap GLB in viewer — dispose old resources first
      if (currentGlbRef.current) {
        currentGlbRef.current.traverse((child) => {
          if (child.geometry) child.geometry.dispose();
          if (child.material) {
            if (Array.isArray(child.material)) child.material.forEach(m => m.dispose());
            else child.material.dispose();
          }
        });
      }
      onPreviewUpdate(data.glb_url);
    }
  } finally {
    setPreviewLoading(false);
  }
}, 300);
```

**Commit:**
```bash
git commit -m "feat: add debounced preview with GLB hot-swap in ParamForm (P2.3 Task 8.5)"
```

---

### Task 28: Integration Tests for All API Endpoints `[test]`

**Files:**
- Modify: `tests/test_generate_api.py` (printability, HITL)
- Modify: `tests/test_organic_api.py` (printability, 3MF)
- Create: `tests/test_history_api.py`
- Create: `tests/test_preview_api.py`

**Key test cases:**
- `test_precision_completed_has_printability_with_material_and_time`
- `test_organic_completed_has_printability`
- `test_drawing_hitl_full_flow_pause_confirm_complete`
- `test_organic_3mf_download_works`
- `test_history_list_pagination_and_filter`
- `test_history_delete_preserves_corrections`
- `test_preview_cache_hit_under_50ms`
- `test_preview_timeout_returns_408`

**Commit:**
```bash
git commit -m "test: add integration tests for all new API endpoints (P0-P2)"
```

---

## Dependency Graph Summary

```
Task 1-2 (geometry_extractor) → Task 3-5 (pipeline integration)
Task 7 (job model) → Task 8-9 (pipeline split + confirm)
Task 10 (corrections) → depends on Task 9
Task 11-12 (frontend HITL) → depends on Task 8-9

Task 14-15 (OCR) → independent
Task 16 (IntentParser) → independent

Task 17-20 (SQLite setup) → Task 21 (refactor) → Task 22 (migration)
Task 24 (history API) → depends on Task 21
Task 25 (history frontend) → depends on Task 24
Task 26 (preview API) → independent
Task 27 (preview frontend) → depends on Task 26
Task 28 (integration tests) → after all others
```

---

## G2 Checkpoint Evaluation

| 条件 | 值 | 满足? |
|------|---|-------|
| 域标签数 ≥ 3 | 3 (backend, frontend, test) | ✅ |
| 可并行任务数 ≥ 2 | 6+ (Groups 1/2/3 parallel, 4/5 parallel) | ✅ |
| 总任务数 ≥ 5 | 28 (grouped from 49 原始任务) | ✅ |

**推荐执行模式：Agent Team**（三条件全满足）
