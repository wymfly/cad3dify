# V3 Phase 1: 架构重构 + 快速收益 — 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 cad3dify 从纯 Python 库重构为前后端分离应用，完成 FastAPI 后端 + React 前端骨架、STL/3MF 导出、3D 预览、评测基准框架。

**Architecture:** 保留现有 `cad3dify/` 作为兼容层（重导出），新建 `backend/` 承载迁移后的核心模块 + FastAPI API 层，新建 `frontend/` 承载 React + Three.js 前端。V2 管道逻辑平移到 `backend/`，不做功能变更。

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, CadQuery, LangChain | React 18, TypeScript 5.6, Vite 5, Ant Design, Three.js (React Three Fiber)

**OpenSpec Reference:** `openspec/changes/2026-02-26-v3-text-to-printable/`

---

## Skill 路由

| Task | 域标签 | Skills |
|------|--------|--------|
| 1.1 | `[backend]` `[architecture]` | — |
| 1.2 | `[backend]` | — |
| 1.3 | `[frontend]` | `frontend-design`, `ui-ux-pro-max` |
| 1.4 | `[backend]` | — |
| 1.5 | `[backend]` | — |
| 1.6 | `[backend]` | — |
| 1.7 | `[backend]` `[test]` | `qa-testing-strategy` |
| 1.8 | `[backend]` `[security]` | `security-review` |
| 1.9 | `[frontend]` | `frontend-design`, `ui-ux-pro-max` |
| 1.10 | `[frontend]` | `frontend-design` |

## G2 关卡分析

| 条件 | 阈值 | 实际 | 满足 |
|------|------|------|------|
| 域标签数 | ≥ 3 | 5 (`backend`, `architecture`, `frontend`, `test`, `security`) | ✅ |
| 可并行任务数 | ≥ 2 | 6 (1.1 完成后 1.2/1.3/1.4/1.5/1.6/1.8 可并行) | ✅ |
| 总任务数 | ≥ 5 | 10 | ✅ |

→ **三条全满足，推荐 Agent Team**（需用户确认）

## 依赖关系

```
Task 1.1 (目录重构)
  ├→ Task 1.2 (FastAPI 后端) ──┐
  ├→ Task 1.3 (React 前端) ───┤→ Task 1.9 (3D 预览, 依赖 1.3+1.4)
  ├→ Task 1.4 (STL 导出) ────┘
  ├→ Task 1.5 (体积估算) ──┐
  ├→ Task 1.6 (Token 监控) ┤→ Task 1.7 (评测基准) → Task 1.10 (评测前端, 依赖 1.7+1.3)
  └→ Task 1.8 (安全沙箱)
```

**并行批次：**
- **Batch 0:** Task 1.1（所有任务的前置）
- **Batch 1:** Task 1.2, 1.3, 1.4, 1.5, 1.6, 1.8（全部可并行）
- **Batch 2:** Task 1.7（依赖 1.5+1.6）, Task 1.9（依赖 1.3+1.4）
- **Batch 3:** Task 1.10（依赖 1.7+1.3）

---

## Task 1.1: 项目目录结构重构

**域标签:** `[backend]` `[architecture]`

**Files:**
- Create: `backend/__init__.py`, `backend/core/__init__.py`, `backend/infra/__init__.py`, `backend/knowledge/__init__.py`, `backend/models/__init__.py`, `backend/pipeline/__init__.py`, `backend/api/__init__.py`, `backend/benchmark/__init__.py`, `backend/v1/__init__.py`
- Modify: `cad3dify/__init__.py` (改为从 backend 重导出)
- Modify: `pyproject.toml` (添加 FastAPI 等依赖)
- Test: `tests/test_import_compat.py`

### Step 1: 创建 backend 目录骨架

创建所有 `__init__.py` 空文件，建立包结构：

```
backend/
├── __init__.py
├── api/__init__.py
├── core/__init__.py
├── infra/__init__.py
├── knowledge/__init__.py
│   └── examples/__init__.py
├── models/__init__.py
├── pipeline/__init__.py
├── benchmark/__init__.py
└── v1/__init__.py
```

### Step 2: 迁移 V2 核心模块到 backend/core/

将以下文件**复制**（不是移动，保留原始文件直到兼容层验证完成）：

| 源文件 | 目标文件 |
|--------|----------|
| `cad3dify/v2/drawing_analyzer.py` | `backend/core/drawing_analyzer.py` |
| `cad3dify/v2/modeling_strategist.py` | `backend/core/modeling_strategist.py` |
| `cad3dify/v2/code_generator.py` | `backend/core/code_generator.py` |
| `cad3dify/v2/smart_refiner.py` | `backend/core/smart_refiner.py` |
| `cad3dify/v2/validators.py` | `backend/core/validators.py` |

修复所有内部 import 路径：`from ..knowledge.part_types` → `from backend.knowledge.part_types`

### Step 3: 迁移 infra 模块

| 源文件 | 目标文件 |
|--------|----------|
| `cad3dify/agents.py` | `backend/infra/agents.py` |
| `cad3dify/chat_models.py` | `backend/infra/chat_models.py` |
| `cad3dify/image.py` | `backend/infra/image.py` |
| `cad3dify/render.py` | `backend/infra/render.py` |

### Step 4: 迁移 knowledge 模块

| 源目录 | 目标目录 |
|--------|----------|
| `cad3dify/knowledge/` | `backend/knowledge/` |

保持内部结构不变（`part_types.py`, `modeling_strategies.py`, `examples/`）。

### Step 5: 迁移 V1 fallback

| 源目录 | 目标目录 |
|--------|----------|
| `cad3dify/v1/` | `backend/v1/` |

### Step 6: 迁移 pipeline

将 `cad3dify/pipeline.py` 拆分为：

- `backend/pipeline/pipeline.py` — `generate_step_v2()`, `generate_step_from_2d_cad_image()`

更新所有内部 import 指向 `backend.*`。

### Step 7: 编写兼容层

修改 `cad3dify/__init__.py`：

```python
"""cad3dify — compatibility shim.

Imports public API from the new backend package layout.
"""
from backend.pipeline.pipeline import generate_step_from_2d_cad_image
from backend.pipeline.pipeline import generate_step_v2
from backend.infra.image import ImageData
```

### Step 8: 写兼容性测试

```python
# tests/test_import_compat.py
def test_cad3dify_public_api_importable():
    """cad3dify 公共 API 仍可通过旧路径导入"""
    from cad3dify import generate_step_v2
    from cad3dify import generate_step_from_2d_cad_image
    from cad3dify import ImageData
    assert callable(generate_step_v2)
    assert callable(generate_step_from_2d_cad_image)

def test_backend_direct_import():
    """backend 包的新路径可直接导入"""
    from backend.knowledge.part_types import DrawingSpec, PartType
    from backend.core.validators import validate_code_params, ValidationResult
    assert DrawingSpec is not None
    assert PartType is not None
```

### Step 9: 运行测试验证

```bash
pytest tests/ -v
```

Expected: 所有现有测试 + 新增兼容性测试全部通过。

### Step 10: 更新 pyproject.toml

添加 V3 新依赖（不删除现有依赖）：

```toml
[tool.poetry.dependencies]
# V3 新增
fastapi = "^0.115.0"
uvicorn = {version = "^0.34.0", extras = ["standard"]}
sse-starlette = "^2.2.0"
pydantic-settings = "^2.7.0"
trimesh = "^4.5.0"      # STEP → STL/glTF
```

### Step 11: Commit

```bash
git add backend/ tests/test_import_compat.py cad3dify/__init__.py pyproject.toml
git commit -m "refactor: [architecture] restructure to backend/ package with compat shim

Migrate V2 modules to backend/{core,infra,knowledge,pipeline,v1}.
cad3dify/__init__.py now re-exports from backend for backward compatibility.
Add FastAPI and related dependencies to pyproject.toml."
```

---

## Task 1.2: FastAPI 后端骨架 + PipelineConfig

**域标签:** `[backend]`
**依赖:** Task 1.1

**Files:**
- Create: `backend/main.py`, `backend/config.py`, `backend/models/pipeline_config.py`, `backend/api/generate.py`, `backend/api/pipeline.py`, `backend/api/health.py`
- Test: `tests/test_api_health.py`, `tests/test_pipeline_config.py`

### Step 1: 写 PipelineConfig 模型测试

```python
# tests/test_pipeline_config.py
def test_pipeline_config_default_is_balanced():
    from backend.models.pipeline_config import PipelineConfig
    config = PipelineConfig()
    assert config.preset == "balanced"

def test_pipeline_config_fast_preset():
    from backend.models.pipeline_config import PRESETS
    fast = PRESETS["fast"]
    assert fast.best_of_n == 1
    assert fast.rag_enabled is False

def test_pipeline_config_precise_preset():
    from backend.models.pipeline_config import PRESETS
    precise = PRESETS["precise"]
    assert precise.best_of_n == 5
    assert precise.ocr_assist is True
    assert precise.multi_model_voting is True

def test_tooltip_spec_fields():
    from backend.models.pipeline_config import TooltipSpec
    tip = TooltipSpec(
        title="多路生成",
        description="生成 N 份候选代码并择优",
        when_to_use="复杂零件推荐",
        cost="耗时 ×N",
        default="balanced: N=3",
    )
    assert tip.title == "多路生成"

def test_get_tooltips_returns_all_fields():
    from backend.models.pipeline_config import get_tooltips
    tooltips = get_tooltips()
    assert "best_of_n" in tooltips
    assert "rag_enabled" in tooltips
    assert tooltips["best_of_n"].title != ""
```

### Step 2: 运行测试确认失败

```bash
pytest tests/test_pipeline_config.py -v
```
Expected: FAIL — `backend.models.pipeline_config` 不存在

### Step 3: 实现 PipelineConfig 模型

创建 `backend/models/pipeline_config.py`，内容来自 design.md 的 ADR-6 定义（PipelineConfig + TooltipSpec + PRESETS + get_tooltips()）。

关键数据结构：
- `PipelineConfig(BaseModel)` — 所有管道开关
- `TooltipSpec(BaseModel)` — title/description/when_to_use/cost/default
- `PRESETS: dict[str, PipelineConfig]` — fast/balanced/precise 三个预设
- `get_tooltips() -> dict[str, TooltipSpec]` — 返回所有字段的 Tooltip

### Step 4: 运行测试确认通过

```bash
pytest tests/test_pipeline_config.py -v
```

### Step 5: 写 FastAPI 健康检查测试

```python
# tests/test_api_health.py
import pytest
from fastapi.testclient import TestClient

def test_health_check():
    from backend.main import app
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_pipeline_tooltips_endpoint():
    from backend.main import app
    client = TestClient(app)
    resp = client.get("/api/pipeline/tooltips")
    assert resp.status_code == 200
    data = resp.json()
    assert "best_of_n" in data

def test_pipeline_presets_endpoint():
    from backend.main import app
    client = TestClient(app)
    resp = client.get("/api/pipeline/presets")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3  # fast, balanced, precise
```

### Step 6: 实现 FastAPI 应用

**`backend/config.py`:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "cad3dify"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8780
    cors_origins: list[str] = ["http://localhost:3001"]

    class Config:
        env_file = ".env"
        env_prefix = "CAD3DIFY_"
```

**`backend/main.py`:**
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import Settings
from backend.api import health, pipeline, generate

settings = Settings()

app = FastAPI(title="cad3dify", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api/pipeline")
app.include_router(generate.router, prefix="/api")
```

**`backend/api/health.py`:**
```python
from fastapi import APIRouter
router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "ok", "version": "3.0.0"}
```

**`backend/api/pipeline.py`:**
```python
from fastapi import APIRouter
from backend.models.pipeline_config import PRESETS, get_tooltips

router = APIRouter()

@router.get("/tooltips")
async def get_pipeline_tooltips():
    return {k: v.model_dump() for k, v in get_tooltips().items()}

@router.get("/presets")
async def get_pipeline_presets():
    return [{"name": k, **v.model_dump()} for k, v in PRESETS.items()]
```

**`backend/api/generate.py`:** SSE 流式端点（基础版，调用 V2 管道）

```python
from fastapi import APIRouter, UploadFile, File, Form
from sse_starlette.sse import EventSourceResponse
import json

router = APIRouter()

@router.post("/generate")
async def generate(
    image: UploadFile = File(...),
    pipeline_config: str = Form("{}"),
):
    config = json.loads(pipeline_config)
    # Phase 1: 基础实现 — 保存上传文件，调用 V2 管道，流式返回进度
    async def event_generator():
        yield {"event": "progress", "data": json.dumps({"stage": "started"})}
        # TODO: 实际调用管道
        yield {"event": "complete", "data": json.dumps({"message": "placeholder"})}
    return EventSourceResponse(event_generator())
```

### Step 7: 运行测试确认通过

```bash
pytest tests/test_api_health.py tests/test_pipeline_config.py -v
```

### Step 8: 手动验证

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
uvicorn backend.main:app --port 8780 &
curl localhost:8780/api/health
curl localhost:8780/api/pipeline/tooltips
curl localhost:8780/api/pipeline/presets
kill %1
```

### Step 9: Commit

```bash
git add backend/main.py backend/config.py backend/models/pipeline_config.py \
  backend/api/health.py backend/api/pipeline.py backend/api/generate.py \
  tests/test_pipeline_config.py tests/test_api_health.py
git commit -m "feat: [backend] add FastAPI skeleton with PipelineConfig model

- /api/health, /api/pipeline/tooltips, /api/pipeline/presets endpoints
- PipelineConfig with fast/balanced/precise presets + TooltipSpec
- SSE-based /api/generate endpoint (placeholder)
- CORS configured for frontend dev server :3001"
```

---

## Task 1.3: React 前端骨架 + 管道配置组件

**域标签:** `[frontend]`
**Skills:** `frontend-design`, `ui-ux-pro-max`

**Files:**
- Create: `frontend/` 完整 Vite + React 骨架
- Create: `frontend/src/components/PipelineConfigBar/`
- Create: `frontend/src/services/api.ts`

### Step 1: 初始化 Vite + React + TypeScript 项目

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install antd @ant-design/icons
npm install axios
npm install react-router-dom
```

### Step 2: 配置 Vite 代理

`frontend/vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    proxy: {
      '/api': {
        target: 'http://localhost:8780',
        changeOrigin: true,
      },
    },
  },
})
```

### Step 3: 创建路由结构

```
frontend/src/
├── App.tsx              # 路由配置
├── main.tsx             # 入口
├── layouts/
│   └── MainLayout.tsx   # Header + Sidebar + Content
├── pages/
│   ├── Home/index.tsx
│   ├── Generate/index.tsx
│   ├── Templates/index.tsx
│   ├── Benchmark/index.tsx
│   └── Settings/index.tsx
├── components/
│   └── PipelineConfigBar/
│       ├── index.tsx
│       ├── PresetSelector.tsx
│       └── CustomPanel.tsx
├── services/
│   └── api.ts           # API 客户端 + SSE helper
└── types/
    └── pipeline.ts      # PipelineConfig, TooltipSpec 类型
```

### Step 4: 实现 TypeScript 类型定义

`frontend/src/types/pipeline.ts`:
```typescript
export interface PipelineConfig {
  preset: 'fast' | 'balanced' | 'precise' | 'custom';
  ocr_assist: boolean;
  two_pass_analysis: boolean;
  multi_model_voting: boolean;
  self_consistency_runs: number;
  best_of_n: number;
  rag_enabled: boolean;
  api_whitelist: boolean;
  ast_pre_check: boolean;
  volume_check: boolean;
  topology_check: boolean;
  cross_section_check: boolean;
  max_refinements: number;
  multi_view_render: boolean;
  structured_feedback: boolean;
  rollback_on_degrade: boolean;
  contour_overlay: boolean;
  printability_check: boolean;
  output_formats: string[];
}

export interface TooltipSpec {
  title: string;
  description: string;
  when_to_use: string;
  cost: string;
  default: string;
}
```

### Step 5: 实现 API 客户端

`frontend/src/services/api.ts`:
```typescript
import axios from 'axios';
import type { TooltipSpec, PipelineConfig } from '../types/pipeline';

const api = axios.create({ baseURL: '/api' });

export async function getTooltips(): Promise<Record<string, TooltipSpec>> {
  const { data } = await api.get('/pipeline/tooltips');
  return data;
}

export async function getPresets(): Promise<Array<{ name: string } & PipelineConfig>> {
  const { data } = await api.get('/pipeline/presets');
  return data;
}
```

### Step 6: 实现 PipelineConfigBar 组件

使用 Ant Design 的 `Radio.Group`（预设切换）+ `Collapse`（自定义面板）+ `Checkbox` + `Tooltip`。

核心交互：
1. 默认显示 4 个预设按钮（⚡快速 / ⚖️均衡 / 🎯精确 / ⚙️自定义）
2. 选择「自定义」时展开面板，显示所有开关
3. 每个开关旁有 `<QuestionCircleOutlined />` 图标，hover 显示 Tooltip
4. Tooltip 数据从 `/api/pipeline/tooltips` 加载

### Step 7: 实现布局和路由

- `MainLayout.tsx`: Ant Design `Layout` + `Menu` 侧边栏
- `App.tsx`: React Router routes 配置
- 各 page 先放占位内容

### Step 8: 验证

```bash
cd frontend && npm run dev
```

Expected: `:3001` 可访问，路由切换正常，PipelineConfigBar 预设切换和自定义面板展开/折叠正常。

### Step 9: Commit

```bash
git add frontend/
git commit -m "feat: [frontend] React skeleton with PipelineConfigBar component

- Vite + React 18 + TypeScript + Ant Design
- Route structure: /, /generate, /templates, /benchmark, /settings
- PipelineConfigBar: preset selector + custom toggle panel with tooltips
- API client with SSE support"
```

---

## Task 1.4: STL/3MF 格式导出

**域标签:** `[backend]`

**Files:**
- Create: `backend/core/format_exporter.py`
- Create: `backend/api/export.py`
- Test: `tests/test_format_exporter.py`

### Step 1: 写导出测试

```python
# tests/test_format_exporter.py
import pytest
from backend.core.format_exporter import FormatExporter, ExportConfig

@pytest.fixture
def sample_step(tmp_path):
    """创建一个简单的 STEP 文件用于测试"""
    import cadquery as cq
    result = cq.Workplane("XY").box(10, 10, 10)
    step_path = str(tmp_path / "test.step")
    cq.exporters.export(result, step_path)
    return step_path

def test_export_stl(sample_step, tmp_path):
    exporter = FormatExporter()
    out = str(tmp_path / "out.stl")
    exporter.export(sample_step, out, ExportConfig(format="stl"))
    assert Path(out).exists()
    assert Path(out).stat().st_size > 0

def test_export_gltf(sample_step, tmp_path):
    exporter = FormatExporter()
    out = str(tmp_path / "out.glb")
    exporter.export(sample_step, out, ExportConfig(format="gltf"))
    assert Path(out).exists()

def test_to_gltf_bytes(sample_step):
    exporter = FormatExporter()
    data = exporter.to_gltf_for_preview(sample_step)
    assert isinstance(data, bytes)
    assert len(data) > 0
```

**注意:** 这些测试需要真实 CadQuery 安装，标记为 `@pytest.mark.skipif` 在 CI 无 CadQuery 时跳过。

### Step 2: 实现 FormatExporter

`backend/core/format_exporter.py`:

```python
from pydantic import BaseModel
from typing import Literal

class ExportConfig(BaseModel):
    format: Literal["stl", "3mf", "gltf"] = "stl"
    linear_deflection: float = 0.1
    angular_deflection: float = 0.5

class FormatExporter:
    def export(self, step_path: str, output_path: str, config: ExportConfig) -> None:
        import cadquery as cq
        shape = cq.importers.importStep(step_path)

        if config.format == "stl":
            cq.exporters.export(shape, output_path, exportType="STL",
                                tolerance=config.linear_deflection,
                                angularTolerance=config.angular_deflection)
        elif config.format == "gltf":
            self._export_gltf(shape, output_path, config)
        elif config.format == "3mf":
            self._export_3mf(shape, output_path, config)

    def to_gltf_for_preview(self, step_path: str) -> bytes:
        """STEP → glTF binary (GLB) for Three.js preview"""
        import cadquery as cq
        import trimesh
        import tempfile, os

        # STEP → STL → trimesh → GLB
        shape = cq.importers.importStep(step_path)
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
            cq.exporters.export(shape, f.name, exportType="STL")
            mesh = trimesh.load(f.name)
            os.unlink(f.name)
        return mesh.export(file_type="glb")

    def _export_gltf(self, shape, output_path: str, config: ExportConfig) -> None:
        import trimesh, tempfile, os
        import cadquery as cq
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
            cq.exporters.export(shape, f.name, exportType="STL",
                                tolerance=config.linear_deflection)
            mesh = trimesh.load(f.name)
            os.unlink(f.name)
        mesh.export(output_path, file_type="glb")

    def _export_3mf(self, shape, output_path: str, config: ExportConfig) -> None:
        import trimesh, tempfile, os
        import cadquery as cq
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
            cq.exporters.export(shape, f.name, exportType="STL",
                                tolerance=config.linear_deflection)
            mesh = trimesh.load(f.name)
            os.unlink(f.name)
        mesh.export(output_path, file_type="3mf")
```

### Step 3: 实现导出 API

`backend/api/export.py`:

```python
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from backend.core.format_exporter import FormatExporter, ExportConfig

router = APIRouter()

@router.post("/export")
async def export_model(step_path: str, config: ExportConfig):
    exporter = FormatExporter()
    # 生成输出路径，返回文件
    ...
```

### Step 4: 运行测试、Commit

```bash
pytest tests/test_format_exporter.py -v
git add backend/core/format_exporter.py backend/api/export.py tests/test_format_exporter.py
git commit -m "feat: [backend] add FormatExporter for STL/3MF/glTF export

- STEP → STL (CadQuery native)
- STEP → glTF/GLB (via trimesh, for Three.js preview)
- STEP → 3MF (via trimesh)
- /api/export endpoint"
```

---

## Task 1.5: 体积估算验证器

**域标签:** `[backend]`

**Files:**
- Modify: `backend/core/validators.py`
- Test: `tests/test_volume_estimator.py`

### Step 1: 写测试

```python
# tests/test_volume_estimator.py
import math
from backend.core.validators import estimate_volume
from backend.knowledge.part_types import DrawingSpec, PartType, BaseBodySpec, DimensionLayer

def test_cylinder_volume():
    """圆柱体: π * r² * h"""
    spec = DrawingSpec(
        part_type=PartType.ROTATIONAL,
        description="圆柱",
        base_body=BaseBodySpec(
            method="revolve",
            profile=[DimensionLayer(diameter=100, height=50)],
        ),
    )
    vol = estimate_volume(spec)
    expected = math.pi * 50**2 * 50  # π * r² * h
    assert abs(vol - expected) / expected < 0.05

def test_stepped_shaft_volume():
    """阶梯轴: 各段圆柱体积之和"""
    spec = DrawingSpec(
        part_type=PartType.ROTATIONAL_STEPPED,
        description="阶梯轴",
        base_body=BaseBodySpec(
            method="revolve",
            profile=[
                DimensionLayer(diameter=60, height=30),
                DimensionLayer(diameter=40, height=50),
            ],
        ),
    )
    vol = estimate_volume(spec)
    expected = math.pi * 30**2 * 30 + math.pi * 20**2 * 50
    assert abs(vol - expected) / expected < 0.05

def test_plate_volume():
    """板件: length * width * height"""
    spec = DrawingSpec(
        part_type=PartType.PLATE,
        description="矩形板",
        base_body=BaseBodySpec(
            method="extrude",
            length=200, width=100, height=10,
        ),
    )
    vol = estimate_volume(spec)
    expected = 200 * 100 * 10
    assert abs(vol - expected) / expected < 0.05
```

### Step 2: 实现 estimate_volume()

在 `backend/core/validators.py` 中添加：

```python
def estimate_volume(spec: DrawingSpec) -> float:
    """从 DrawingSpec 估算理论体积（mm³）。

    回转体: Σ(π * r² * h)
    板件/支架: length * width * height
    """
    import math

    if spec.part_type in (PartType.ROTATIONAL, PartType.ROTATIONAL_STEPPED):
        total = 0.0
        for layer in spec.base_body.profile:
            r = layer.diameter / 2
            total += math.pi * r * r * layer.height
        # 减去中心孔体积
        if spec.base_body.bore:
            br = spec.base_body.bore.diameter / 2
            h = sum(l.height for l in spec.base_body.profile)
            total -= math.pi * br * br * h
        return total

    # 板件、支架等: L × W × H
    l = spec.base_body.length or spec.overall_dimensions.get("length", 0)
    w = spec.base_body.width or spec.overall_dimensions.get("width", 0)
    h = spec.base_body.height or spec.overall_dimensions.get("height", 0)
    return l * w * h
```

### Step 3: 运行测试、Commit

```bash
pytest tests/test_volume_estimator.py -v
git add backend/core/validators.py tests/test_volume_estimator.py
git commit -m "feat: [backend] add estimate_volume() for theoretical volume estimation

- Rotational: Σ(π*r²*h) with bore subtraction
- Plate/bracket: L*W*H
- Integrates with SmartRefiner diagnostic context"
```

---

## Task 1.6: Token 用量监控

**域标签:** `[backend]`

**Files:**
- Create: `backend/infra/token_tracker.py`
- Test: `tests/test_token_tracker.py`

### Step 1: 写测试

```python
# tests/test_token_tracker.py
from backend.infra.token_tracker import TokenTracker

def test_token_tracker_records_usage():
    tracker = TokenTracker()
    tracker.record("stage1_analysis", input_tokens=500, output_tokens=200, duration_s=1.5)
    tracker.record("stage2_codegen", input_tokens=1000, output_tokens=800, duration_s=3.2)
    stats = tracker.get_stats()
    assert stats["total_input_tokens"] == 1500
    assert stats["total_output_tokens"] == 1000
    assert len(stats["stages"]) == 2

def test_token_tracker_export_json(tmp_path):
    tracker = TokenTracker()
    tracker.record("test", input_tokens=100, output_tokens=50, duration_s=0.5)
    path = str(tmp_path / "stats.json")
    tracker.export_json(path)
    import json
    with open(path) as f:
        data = json.load(f)
    assert data["total_input_tokens"] == 100
```

### Step 2: 实现 TokenTracker

`backend/infra/token_tracker.py`:

```python
import json
import time
from dataclasses import dataclass, field

@dataclass
class StageStats:
    name: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_s: float = 0.0

class TokenTracker:
    def __init__(self):
        self._stages: list[StageStats] = []
        self._start_time: float = time.time()

    def record(self, stage_name: str, input_tokens: int, output_tokens: int, duration_s: float) -> None:
        self._stages.append(StageStats(
            name=stage_name, input_tokens=input_tokens,
            output_tokens=output_tokens, duration_s=duration_s,
        ))

    def get_stats(self) -> dict:
        return {
            "total_input_tokens": sum(s.input_tokens for s in self._stages),
            "total_output_tokens": sum(s.output_tokens for s in self._stages),
            "total_duration_s": sum(s.duration_s for s in self._stages),
            "wall_time_s": time.time() - self._start_time,
            "stages": [
                {"name": s.name, "input_tokens": s.input_tokens,
                 "output_tokens": s.output_tokens, "duration_s": s.duration_s}
                for s in self._stages
            ],
        }

    def export_json(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.get_stats(), f, indent=2)
```

### Step 3: 运行测试、Commit

```bash
pytest tests/test_token_tracker.py -v
git add backend/infra/token_tracker.py tests/test_token_tracker.py
git commit -m "feat: [backend] add TokenTracker for per-stage LLM usage monitoring"
```

---

## Task 1.7: 评测基准框架 + 失败分类

**域标签:** `[backend]` `[test]`
**Skills:** `qa-testing-strategy`
**依赖:** Task 1.5, Task 1.6

**Files:**
- Create: `backend/benchmark/runner.py`, `backend/benchmark/metrics.py`, `backend/benchmark/reporter.py`
- Create: `backend/api/benchmark.py`
- Create: `benchmarks/v1/` 初始数据集 (5 case)
- Test: `tests/test_benchmark.py`

### Step 1: 写测试

```python
# tests/test_benchmark.py
from backend.benchmark.metrics import BenchmarkMetrics, FailureCategory, classify_failure

def test_failure_classification():
    assert classify_failure(compile_error="NameError") == FailureCategory.CODE_EXECUTION
    assert classify_failure(type_mismatch=True) == FailureCategory.TYPE_RECOGNITION
    assert classify_failure(param_error="diameter off by 50%") == FailureCategory.DIMENSION_DEVIATION

def test_metrics_calculation():
    metrics = BenchmarkMetrics.from_results([
        {"compiled": True, "type_correct": True, "param_accuracy": 0.95, "bbox_match": True, "duration": 10},
        {"compiled": True, "type_correct": False, "param_accuracy": 0.80, "bbox_match": False, "duration": 15},
        {"compiled": False, "type_correct": False, "param_accuracy": 0.0, "bbox_match": False, "duration": 5},
    ])
    assert metrics.compile_rate == pytest.approx(2/3)
    assert metrics.type_accuracy == pytest.approx(1/3)
```

### Step 2: 实现 metrics + reporter + runner

**`backend/benchmark/metrics.py`:**
- `FailureCategory` 枚举 (TYPE_RECOGNITION, ANNOTATION_MISS, CODE_EXECUTION, STRUCTURAL_ERROR, DIMENSION_DEVIATION)
- `classify_failure()` 分类函数
- `BenchmarkMetrics` 数据类 (5 项指标)

**`backend/benchmark/reporter.py`:**
- Markdown 报告生成
- JSON 报告导出
- 失败分类统计（按频率排序）

**`backend/benchmark/runner.py`:**
- `BenchmarkRunner.run(dataset_dir, workers)` — 遍历数据集运行管道
- 支持 CLI: `python -m backend.benchmark.runner run --dataset benchmarks/v1/`

### Step 3: 创建初始数据集

`benchmarks/v1/` 包含 5 个 case，每个有：
- `case_NNN.json` — 元数据（expected_spec, expected_bbox）
- `case_NNN.png` — 工程图纸

### Step 4: 实现评测 API

`backend/api/benchmark.py`:
- `POST /api/benchmark/run` — SSE 流式返回进度 + 结果
- `GET /api/benchmark/history` — 历史报告列表
- `GET /api/benchmark/history/{run_id}` — 详细报告

### Step 5: 运行测试、Commit

```bash
pytest tests/test_benchmark.py -v
git add backend/benchmark/ backend/api/benchmark.py benchmarks/ tests/test_benchmark.py
git commit -m "feat: [backend] add benchmark framework with failure classification

- BenchmarkRunner with 5 metrics (compile/type/param/bbox/duration)
- Failure classification: 5 categories, frequency-sorted reporting
- CLI: python -m backend.benchmark.runner
- API: /api/benchmark/run (SSE), /api/benchmark/history
- Initial dataset: 5 hand-labeled cases"
```

---

## Task 1.8: 代码执行安全沙箱

**域标签:** `[backend]` `[security]`
**Skills:** `security-review`

**Files:**
- Create: `backend/infra/sandbox.py`
- Modify: `backend/config.py` (安全配置项)
- Test: `tests/test_sandbox.py`

### Step 1: 写安全测试

```python
# tests/test_sandbox.py
import pytest
from backend.infra.sandbox import SafeExecutor, SecurityViolation

def test_blocks_os_system():
    executor = SafeExecutor()
    with pytest.raises(SecurityViolation, match="os.system"):
        executor.check_code("import os; os.system('ls')")

def test_blocks_subprocess():
    executor = SafeExecutor()
    with pytest.raises(SecurityViolation, match="subprocess"):
        executor.check_code("import subprocess; subprocess.run(['ls'])")

def test_blocks_eval():
    executor = SafeExecutor()
    with pytest.raises(SecurityViolation, match="eval"):
        executor.check_code("eval('1+1')")

def test_allows_cadquery_code():
    executor = SafeExecutor()
    code = """
import cadquery as cq
result = cq.Workplane("XY").box(10, 10, 10)
"""
    # Should not raise
    executor.check_code(code)

def test_timeout_enforcement():
    executor = SafeExecutor(timeout_s=2)
    result = executor.execute("import time; time.sleep(10)")
    assert result.timed_out is True

def test_file_isolation(tmp_path):
    executor = SafeExecutor(work_dir=str(tmp_path))
    result = executor.execute("open('/etc/passwd').read()")
    assert result.success is False
```

### Step 2: 实现 SafeExecutor

`backend/infra/sandbox.py`:

- AST 预检查：扫描 import/call 禁用列表 (os.system, subprocess, eval, exec, __import__)
- subprocess 执行：独立子进程 + timeout + 内存限制
- 文件系统隔离：chdir 到指定 tmp 目录
- 并发限制：asyncio.Semaphore(N)

### Step 3: API 层鉴权

在 `backend/config.py` 增加：
```python
api_key: str | None = None  # 设置后启用 API Key 验证
max_concurrent_executions: int = 4
execution_timeout_s: int = 60
execution_memory_mb: int = 2048
```

### Step 4: 运行测试、Commit

```bash
pytest tests/test_sandbox.py -v
git add backend/infra/sandbox.py backend/config.py tests/test_sandbox.py
git commit -m "feat: [security] add SafeExecutor with AST pre-check and subprocess isolation

- AST-level blocking of dangerous modules (os.system, subprocess, eval, exec)
- Subprocess execution with timeout (60s) and memory limit (2GB)
- File system isolation (work_dir restriction)
- Concurrency limiter (max 4 parallel executions)
- API key authentication support"
```

---

## Task 1.9: 3D 预览组件

**域标签:** `[frontend]`
**Skills:** `frontend-design`, `ui-ux-pro-max`
**依赖:** Task 1.3, Task 1.4

**Files:**
- Create: `frontend/src/components/Viewer3D/index.tsx`
- Install: `@react-three/fiber`, `@react-three/drei`, `three`

### Step 1: 安装 Three.js 依赖

```bash
cd frontend
npm install three @react-three/fiber @react-three/drei
npm install -D @types/three
```

### Step 2: 实现 Viewer3D 组件

`frontend/src/components/Viewer3D/index.tsx`:

使用 React Three Fiber：
- `Canvas` + `OrbitControls` 提供旋转/缩放/平移
- `GLTFLoader` 或 `useGLTF` 加载 GLB 文件
- 线框/实体模式切换（`<meshStandardMaterial wireframe={wireframe} />`）
- 标准视角快捷按钮（Front/Top/Side/Iso）通过 `camera.position.set()` 实现
- 响应式：`Canvas` 设置 `style={{ width: '100%', height: '100%' }}`

关键 props：
```typescript
interface Viewer3DProps {
  modelUrl: string | null;    // GLB 文件 URL
  wireframe?: boolean;
  onLoaded?: () => void;
}
```

### Step 3: 添加视角控制条

4 个按钮：正视 / 俯视 / 侧视 / 等轴测，点击切换 camera position。

### Step 4: 验证

手动创建一个测试 GLB 文件，确认加载渲染正常，交互流畅。

### Step 5: Commit

```bash
git add frontend/src/components/Viewer3D/ frontend/package.json frontend/package-lock.json
git commit -m "feat: [frontend] add Viewer3D component with Three.js

- React Three Fiber + GLB loading
- OrbitControls (rotate/zoom/pan)
- Wireframe/solid mode toggle
- Standard view shortcuts (front/top/side/isometric)
- Responsive layout"
```

---

## Task 1.10: 评测基准前端页面

**域标签:** `[frontend]`
**Skills:** `frontend-design`
**依赖:** Task 1.7, Task 1.3

**Files:**
- Create: `frontend/src/pages/Benchmark/index.tsx`
- Create: `frontend/src/pages/Benchmark/RunBenchmark.tsx`
- Create: `frontend/src/pages/Benchmark/ReportDetail.tsx`

### Step 1: 实现评测运行页面

`RunBenchmark.tsx`:
- 选择数据集（下拉框，从 `/api/benchmark/datasets` 获取）
- 「运行评测」按钮 → `POST /api/benchmark/run` → SSE 进度条
- 进度：显示当前 case N/Total + 当前 stage

### Step 2: 实现历史报告列表

`index.tsx`:
- Ant Design `Table` 组件
- 列：日期 / 数据集 / 编译率 / 类型准确率 / 参数准确率 / 几何匹配率 / 详情链接

### Step 3: 实现报告详情页

`ReportDetail.tsx`:
- 指标摘要卡片（5 项指标）
- 失败分类饼图（Ant Design Charts 或简单 HTML）
- 逐 case 结果表（可展开查看详情）

### Step 4: 验证

确保完整评测流程可走通：触发 → 进度显示 → 报告查看。

### Step 5: Commit

```bash
git add frontend/src/pages/Benchmark/
git commit -m "feat: [frontend] add Benchmark page with run/history/detail views

- Benchmark run trigger with SSE progress display
- History report list with metrics summary
- Report detail: metric cards + failure classification + per-case results"
```

---

## 验证清单（Phase 1 完成后）

- [ ] `pytest tests/ -v` — 所有测试通过
- [ ] `python -c "from cad3dify import generate_step_v2"` — 兼容性
- [ ] `uvicorn backend.main:app --port 8780` — 后端启动
- [ ] `curl localhost:8780/api/health` → 200
- [ ] `curl localhost:8780/api/pipeline/tooltips` → 返回 Tooltip 数据
- [ ] `cd frontend && npm run dev` — 前端启动 `:3001`
- [ ] 前端路由切换正常
- [ ] PipelineConfigBar 预设切换 + 自定义面板
- [ ] 3D Viewer 加载 GLB 渲染正常
- [ ] 评测基准运行流程可走通
