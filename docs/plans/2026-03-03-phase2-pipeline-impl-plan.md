# Phase 2 Pipeline Nodes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 将 organic 管线的 4 个 stub/legacy 节点替换为真实的策略化实现，加上导出基础设施。

**Architecture:** 三层模型（节点=目的，策略=功能，部署=配置）。所有节点遵循 mesh_healer 的 Phase 1 验证模式。

**Tech Stack:** Python 3.10+, LangGraph, manifold3d, trimesh, asyncio, FastAPI

**OpenSpec:** `openspec/changes/phase2-pipeline-nodes/` — 含 design.md, specs/*/spec.md, tasks.md

---

## Task 1: 导出基础设施

**Files:**
- Create: `backend/core/mesh_converter.py`
- Create: `tests/test_mesh_converter.py`
- Create: `backend/api/routes/export.py`
- Create: `tests/test_export_api.py`
- Modify: `backend/api/routes/__init__.py` (register router)

**Spec:** `openspec/changes/phase2-pipeline-nodes/specs/mesh-format-export/spec.md`

**Step 1: Write failing tests for convert_mesh**

```python
# tests/test_mesh_converter.py
import pytest
from pathlib import Path

def test_convert_obj_to_stl(tmp_path):
    """OBJ → STL 转换生成正确文件名。"""
    # Create minimal OBJ
    obj_file = tmp_path / "model.obj"
    obj_file.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    from backend.core.mesh_converter import convert_mesh
    result = convert_mesh(obj_file, "stl", tmp_path / "out")
    assert result.name == "model.stl"
    assert result.exists()

def test_same_format_passthrough(tmp_path):
    """同格式使用 shutil.copy2，不走 trimesh。"""
    glb_file = tmp_path / "mesh.glb"
    glb_file.write_bytes(b"fake-glb-content")
    from backend.core.mesh_converter import convert_mesh
    result = convert_mesh(glb_file, "glb", tmp_path / "out")
    assert result.name == "mesh.glb"
    assert result.read_bytes() == b"fake-glb-content"

def test_unsupported_format_raises(tmp_path):
    """不支持的格式抛出 ValueError。"""
    obj_file = tmp_path / "model.obj"
    obj_file.write_text("v 0 0 0\n")
    from backend.core.mesh_converter import convert_mesh
    with pytest.raises(ValueError, match="支持"):
        convert_mesh(obj_file, "xyz", tmp_path / "out")
```

**Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_mesh_converter.py -v
```
Expected: FAIL (module not found)

**Step 3: Implement convert_mesh**

```python
# backend/core/mesh_converter.py
"""网格格式转换工具函数。"""
from __future__ import annotations
import shutil
from pathlib import Path

SUPPORTED_FORMATS = {"obj", "glb", "stl", "3mf"}

def convert_mesh(input_path: Path, output_format: str, output_dir: Path) -> Path:
    output_format = output_format.lower()
    if output_format not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的格式 '{output_format}'，支持: {sorted(SUPPORTED_FORMATS)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{input_path.stem}.{output_format}"
    input_ext = input_path.suffix.lstrip(".").lower()
    if input_ext == output_format:
        shutil.copy2(input_path, output_path)
        return output_path
    import trimesh
    mesh = trimesh.load(str(input_path), force="mesh")
    mesh.export(str(output_path), file_type=output_format)
    return output_path
```

**Step 4: Run tests, verify pass**

```bash
uv run pytest tests/test_mesh_converter.py -v
```

**Step 5: Write failing tests for export API endpoint**

```python
# tests/test_export_api.py — 使用 FastAPI TestClient
# 测试：原始格式下载、格式转换、400 不支持格式、404 不存在
```

**Step 6: Implement export API endpoint**

Key points:
- `format: str | None = Query(default=None)`
- `try: ... except ValueError as e: raise HTTPException(400, str(e))`
- `background_tasks.add_task(shutil.rmtree, tmp_dir, ignore_errors=True)`
- Register router in `backend/api/routes/__init__.py`

**Step 7: Run all tests, verify pass**

```bash
uv run pytest tests/test_mesh_converter.py tests/test_export_api.py -v
```

**Step 8: Commit**

```bash
git add backend/core/mesh_converter.py tests/test_mesh_converter.py backend/api/routes/export.py tests/test_export_api.py
git commit -m "feat(export): add mesh format conversion utility + API endpoint"
```

---

## Task 2: mesh_scale 实现

**Files:**
- Modify: `backend/graph/nodes/mesh_scale.py`
- Modify: `tests/test_mesh_pipeline.py`

**Spec:** `openspec/changes/phase2-pipeline-nodes/specs/mesh-scale/spec.md`

**Reference:** `backend/core/mesh_post_processor.py` → `MeshPostProcessor.scale_mesh()` — 已有均匀缩放逻辑，需提取并增强（底面贴合 + XY 居中）。

**Step 1: Write failing tests**

```python
# tests/test_mesh_pipeline.py (add/update mesh_scale section)
def test_mesh_scale_uniform_scaling():
    """缩放至目标包围盒，保持纵横比。"""

def test_mesh_scale_alignment_order():
    """执行顺序：缩放 → Z=0 贴合 → XY 居中。"""

def test_mesh_scale_passthrough_no_bbox():
    """final_bounding_box=None 时直接 passthrough。"""

def test_mesh_scale_skipped_no_input():
    """无 watertight_mesh 时跳过。"""
```

**Step 2: Run, verify fail**

**Step 3: Rewrite mesh_scale.py**

Key implementation:
- 从 `ctx.get_asset("watertight_mesh")` 获取输入
- 从 `ctx.get_data("organic_spec")` 获取 OrganicSpec
- 缩放：`scale_factor = min(target[i] / current[i] for i in range(3))`
- Z 贴合：`mesh.translate([0, 0, -mesh.bounds[0][2]])`
- XY 居中：`centroid = mesh.centroid; mesh.translate([-centroid[0], -centroid[1], 0])`
- `ctx.put_asset("scaled_mesh", path, format, metadata={...})`

**Step 4: Run, verify pass**

**Step 5: Commit**

```bash
git commit -m "feat(mesh_scale): implement uniform scaling with Z-align and XY-center"
```

---

## Task 3: boolean_assemble

**Files:**
- Create: `backend/graph/configs/boolean_assemble.py`
- Create: `backend/graph/strategies/boolean/__init__.py`
- Create: `backend/graph/strategies/boolean/manifold3d.py`
- Modify: `backend/graph/nodes/boolean_assemble.py` (replace boolean_cuts.py)
- Create: `tests/test_boolean_assemble.py`
- Delete: `backend/graph/nodes/boolean_cuts.py`
- Delete: `backend/graph/nodes/export_formats.py`

**Spec:** `openspec/changes/phase2-pipeline-nodes/specs/boolean-assemble/spec.md`

**Reference:** `backend/core/mesh_post_processor.py` → `apply_boolean_cuts()` — manifold3d 布尔运算逻辑。

**Step 1: Write failing tests**

```python
# tests/test_boolean_assemble.py
class TestBooleanAssembleRegistration:
    def test_registered_with_manifold3d_strategy(self): ...
    def test_replaces_boolean_cuts(self): ...

class TestManifoldCheckGate:
    def test_manifold_mesh_passes_directly(self): ...
    def test_non_manifold_repaired_by_voxelization(self): ...
    def test_voxelization_fails_skip_false_raises(self): ...
    def test_voxelization_fails_skip_true_passthrough(self): ...
    def test_voxelization_retry_2x_resolution(self): ...

class TestBooleanOperations:
    def test_flat_bottom_cut(self): ...
    def test_hole_cut(self): ...
    def test_single_cut_failure_continues(self): ...
    def test_all_cuts_fail_raises(self): ...

class TestPassthroughConditions:
    def test_no_cuts_passthrough(self): ...
    def test_draft_mode_passthrough(self): ...
    def test_no_input_skipped(self): ...
```

**Step 2: Implement BooleanAssembleConfig**

```python
# backend/graph/configs/boolean_assemble.py
from backend.graph.descriptor import BaseNodeConfig

class BooleanAssembleConfig(BaseNodeConfig):
    strategy: str = "manifold3d"
    voxel_resolution: int = 128
    skip_on_non_manifold: bool = False
```

**Step 3: Implement Manifold3DStrategy**

Key flow:
1. Load mesh → `is_manifold_check()` (trimesh.is_watertight)
2. If non-manifold → `force_voxelize(resolution)` → re-check
3. If still non-manifold → retry with `2 * resolution`
4. If still fails → respect `skip_on_non_manifold` config
5. For each engineering_cut: try/except, track failures
6. All cuts fail → raise error (unless draft mode)
7. `ctx.put_asset("final_mesh", path, fmt, metadata)`

**Step 4: Implement boolean_assemble node**

Replace `boolean_cuts.py` content (or create as new file `boolean_assemble.py`):
```python
@register_node(
    name="boolean_assemble",
    display_name="布尔装配",
    requires=["scaled_mesh"],
    produces=["final_mesh"],
    input_types=["organic"],
    config_model=BooleanAssembleConfig,
    strategies={"manifold3d": Manifold3DStrategy},
    default_strategy="manifold3d",
)
async def boolean_assemble_node(ctx: NodeContext) -> None:
    ...
```

**Step 5: Delete old stubs + update test_mesh_pipeline.py**

- Delete `boolean_cuts.py`, `export_formats.py`
- Update `tests/test_mesh_pipeline.py`: remove old stub tests, add boolean_assemble + mesh_scale integration

**Step 6: Run all tests**

```bash
uv run pytest tests/test_boolean_assemble.py tests/test_mesh_pipeline.py -v
```

**Step 7: Commit**

```bash
git commit -m "feat(boolean_assemble): manifold3d strategy with voxel repair gate"
```

---

## Task 4: generate_raw_mesh — Config + Strategies

**Files:**
- Create: `backend/graph/configs/generate_raw_mesh.py`
- Create: `backend/graph/strategies/generate/__init__.py`
- Create: `backend/graph/strategies/generate/base.py`
- Create: `backend/graph/strategies/generate/hunyuan3d.py`
- Create: `backend/graph/strategies/generate/tripo3d.py`
- Create: `backend/graph/strategies/generate/spar3d.py`
- Create: `backend/graph/strategies/generate/trellis.py`

**Spec:** `openspec/changes/phase2-pipeline-nodes/specs/generate-raw-mesh/spec.md`

**Reference:** `backend/infra/mesh_providers/` (TripoProvider, HunyuanProvider)

**Step 1: Write failing tests for config + strategies**

```python
# tests/test_generate_raw_mesh.py (part 1)
class TestGenerateRawMeshConfig:
    def test_default_values(self): ...
    def test_per_model_fields(self): ...

class TestLocalModelStrategy:
    def test_health_check_healthy(self): ...
    def test_health_check_unhealthy(self): ...
    def test_health_check_ttl_cache(self): ...

class TestHunyuan3DStrategy:
    def test_check_available_local_healthy(self): ...
    def test_check_available_local_unhealthy_saas_available(self): ...
    def test_check_available_local_only_unhealthy(self): ...
    def test_execute_local_first_fallback_saas(self): ...
    def test_execute_saas_only(self): ...

class TestTripo3DStrategy:
    def test_check_available_with_api_key(self): ...
    def test_wraps_tripo_provider(self): ...

class TestSPAR3DStrategy:
    def test_local_only_check_available(self): ...

class TestTRELLISStrategy:
    def test_local_only_check_available(self): ...
```

**Step 2: Implement GenerateRawMeshConfig**

```python
class GenerateRawMeshConfig(BaseNodeConfig):
    strategy: str = "hunyuan3d"
    hunyuan3d_api_key: str | None = None
    hunyuan3d_endpoint: str | None = None
    tripo3d_api_key: str | None = None
    spar3d_endpoint: str | None = None
    trellis_endpoint: str | None = None
    timeout: int = 120
    output_format: str = "glb"
```

**Step 3: Implement LocalModelStrategy base**

Only local HTTP: POST /v1/generate, health check with TTL cache. NO SaaS fallback.

**Step 4: Implement 4 strategies**

- **Hunyuan3DGenerateStrategy**: dual-deploy (local + SaaS), SaaS fallback logic HERE (not in base)
- **Tripo3DGenerateStrategy**: SaaS only, wraps TripoProvider
- **SPAR3DGenerateStrategy**: local only, extends LocalModelStrategy
- **TRELLISGenerateStrategy**: local only, extends LocalModelStrategy

**Step 5: Run tests, verify pass**

**Step 6: Commit**

```bash
git commit -m "feat(generate_raw_mesh): config + 4 model strategies with dual-deploy"
```

---

## Task 5: generate_raw_mesh — Node + Adapter + Tests

**Files:**
- Create: `backend/graph/nodes/generate_raw_mesh.py`
- Modify: `backend/graph/nodes/organic.py` (legacy adapter)
- Create/extend: `tests/test_generate_raw_mesh.py` (node + integration tests)

**Step 1: Write failing tests for node**

```python
class TestGenerateRawMeshNode:
    def test_registered_with_4_strategies(self): ...
    def test_fallback_chain(self): ...
    def test_auto_mode_execute_with_fallback(self): ...
    def test_timeout_fallback(self): ...
    def test_runtime_error_fallback(self): ...
    def test_all_strategies_exhausted_fails(self): ...
    def test_sse_progress_events(self): ...
    def test_put_asset_format_from_file_extension(self): ...

class TestLegacyAdapter:
    def test_adapter_accepts_cad_job_state(self): ...
    def test_adapter_syncs_products_back(self): ...
    def test_no_duplicate_registration(self): ...
```

**Step 2: Implement generate_raw_mesh node**

```python
@register_node(
    name="generate_raw_mesh",
    display_name="网格生成",
    requires=["confirmed_params"],
    produces=["raw_mesh"],
    input_types=["organic"],
    config_model=GenerateRawMeshConfig,
    strategies={
        "hunyuan3d": Hunyuan3DGenerateStrategy,
        "tripo3d": Tripo3DGenerateStrategy,
        "spar3d": SPAR3DGenerateStrategy,
        "trellis": TRELLISGenerateStrategy,
    },
    fallback_chain=["hunyuan3d", "tripo3d", "spar3d", "trellis"],
    default_strategy="hunyuan3d",
)
async def generate_raw_mesh_node(ctx: NodeContext) -> None:
    if ctx.config.strategy == "auto":
        await ctx.execute_with_fallback()
    else:
        strategy = ctx.get_strategy()
        await strategy.execute(ctx)
```

**Step 3: Implement legacy adapter in organic.py**

Remove `@register_node` from `generate_organic_mesh_node`, convert to adapter:
```python
async def generate_organic_mesh_node(state: dict) -> dict:
    """Legacy adapter: CadJobState → NodeContext bridge."""
    ctx = NodeContext.from_legacy_state(state, "generate_raw_mesh")
    await generate_raw_mesh_node(ctx)
    return ctx.to_state_diff()
```

**Step 4: Verify builder_legacy.py still imports**

```bash
uv run python -c "from backend.graph.nodes.organic import generate_organic_mesh_node; print('OK')"
```

**Step 5: Run full test suite**

```bash
uv run pytest tests/test_generate_raw_mesh.py -v
```

**Step 6: Commit**

```bash
git commit -m "feat(generate_raw_mesh): node registration + legacy CadJobState adapter"
```

---

## Task 6: slice_to_gcode

**Files:**
- Create: `backend/graph/configs/slice_to_gcode.py`
- Create: `backend/graph/strategies/slice/__init__.py`
- Create: `backend/graph/strategies/slice/prusaslicer.py`
- Create: `backend/graph/strategies/slice/orcaslicer.py`
- Create: `backend/core/gcode_parser.py`
- Create: `backend/graph/nodes/slice_to_gcode.py`
- Create: `tests/test_slice_to_gcode.py`

**Spec:** `openspec/changes/phase2-pipeline-nodes/specs/slice-to-gcode/spec.md`

**Step 1: Write failing tests**

```python
# tests/test_slice_to_gcode.py
class TestSliceToGcodeConfig:
    def test_default_values(self): ...
    def test_hardware_params(self): ...  # nozzle_diameter, filament_type

class TestPrusaSlicerStrategy:
    def test_check_available_found(self): ...
    def test_check_available_not_found(self): ...
    def test_cli_args_include_hardware_params(self): ...
    def test_configurable_cli_path(self): ...
    def test_timeout_fallback(self): ...
    def test_runtime_error_fallback(self): ...

class TestOrcaSlicerStrategy:
    def test_parameter_mapping_no_percent(self): ...
    def test_cli_path_detection(self): ...

class TestGcodeParser:
    def test_parse_prusaslicer_format(self): ...
    def test_parse_orcaslicer_format(self): ...
    def test_parse_failure_returns_empty(self): ...

class TestSliceToGcodeNode:
    def test_registered_with_strategies(self): ...
    def test_best_mesh_selection_prefers_final(self): ...
    def test_fallback_to_watertight(self): ...
    def test_no_mesh_skipped(self): ...
    def test_glb_auto_converted_to_stl(self): ...
    def test_all_strategies_fail(self): ...
```

**Step 2: Implement SliceToGcodeConfig**

```python
class SliceToGcodeConfig(BaseNodeConfig):
    strategy: str = "prusaslicer"
    prusaslicer_path: str | None = None
    orcaslicer_path: str | None = None
    layer_height: float = 0.2
    fill_density: int = 20
    support_material: bool = False
    nozzle_diameter: float = 0.4
    filament_type: str = "PLA"
    timeout: int = 120
```

**Step 3: Implement PrusaSlicerStrategy + OrcaSlicerStrategy**

Key: all hardware params (nozzle_diameter, filament_type) must be in CLI args.

**Step 4: Implement gcode_parser**

Multi-pattern matching for PrusaSlicer vs OrcaSlicer comment formats.

**Step 5: Implement slice_to_gcode node**

```python
@register_node(
    name="slice_to_gcode",
    display_name="切片出码",
    requires=[["final_mesh", "scaled_mesh", "watertight_mesh"]],
    produces=["gcode_bundle"],
    input_types=["organic"],
    config_model=SliceToGcodeConfig,
    strategies={"prusaslicer": PrusaSlicerStrategy, "orcaslicer": OrcaSlicerStrategy},
    fallback_chain=["prusaslicer", "orcaslicer"],
    default_strategy="prusaslicer",
)
```

Best mesh selection: final_mesh > scaled_mesh > watertight_mesh.
Auto-convert GLB→STL via convert_mesh before slicing.

**Step 6: Run tests**

```bash
uv run pytest tests/test_slice_to_gcode.py -v
```

**Step 7: Commit**

```bash
git commit -m "feat(slice_to_gcode): PrusaSlicer + OrcaSlicer strategies with gcode parsing"
```

---

## Task 7: 集成验证 + Legacy 废弃

**Files:**
- Create: `tests/test_phase2_integration.py`
- Modify: `backend/graph/nodes/lifecycle.py` (finalize_node)
- Modify: `backend/graph/nodes/organic.py` (deprecate postprocess)
- Delete: `backend/infra/mesh_providers/auto.py`
- Modify: `backend/infra/mesh_providers/__init__.py`

**Step 1: Write integration tests**

```python
# tests/test_phase2_integration.py
class TestEndToEndPipeline:
    """完整 organic 管线 mock 集成测试。"""
    async def test_full_pipeline_runs(self): ...
    # generate_raw_mesh(mock) → mesh_healer → mesh_scale → boolean_assemble → slice_to_gcode(mock)

class TestDependencyResolver:
    def test_new_topology_order(self): ...
    def test_no_export_formats_node(self): ...
    def test_no_boolean_cuts_node(self): ...
    def test_no_duplicate_generate_organic_mesh(self): ...

class TestFinalizeNode:
    def test_reads_new_assets(self): ...
    # raw_mesh, watertight_mesh, final_mesh, gcode_bundle
```

**Step 2: Update finalize_node**

Read from PipelineState.assets: raw_mesh, watertight_mesh, final_mesh, gcode_bundle.
Map to frontend-expected fields: model_url, stl_url, etc.

**Step 3: Deprecate postprocess_organic_node**

```python
import warnings

@register_node(...)
async def postprocess_organic_node(ctx):
    warnings.warn("postprocess_organic_node is deprecated, use new pipeline nodes", DeprecationWarning)
    ...
```

**Step 4: Delete AutoProvider**

Remove `backend/infra/mesh_providers/auto.py`, update `__init__.py` exports.

**Step 5: Run full test suite**

```bash
uv run pytest tests/ -v
```

**Step 6: Commit**

```bash
git commit -m "feat(phase2): integration tests + finalize_node update + legacy deprecation"
```

---

## Execution Summary

| Task | OpenSpec Tasks | Estimated Scope |
|------|---------------|-----------------|
| 1. 导出基础设施 | 1.1-1.4 | 2 new files + tests |
| 2. mesh_scale | 2.1-2.2 | 1 file rewrite + tests |
| 3. boolean_assemble | 3.1-3.6 | 4 new files + tests + 2 deletions |
| 4. generate_raw_mesh (strategies) | 4.1-4.6 | 6 new files |
| 5. generate_raw_mesh (node) | 4.7-4.10 | 1 new file + 1 modify + tests |
| 6. slice_to_gcode | 5.1-5.6 | 5 new files + tests |
| 7. 集成 + Legacy | 6.1-6.6 | integration tests + cleanup |

**Total:** 7 tasks, ~20 new files, ~3 modified files, ~2 deleted files.
