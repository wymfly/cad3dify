"""Tests for mesh_scale node — uniform scaling with Z-align and XY-center.

TDD tests for Phase 2 Task 2: mesh_scale node implementation.
Tests cover:
- Uniform scaling to target bounding box
- Execution order: scale -> Z=0 align -> XY center
- Passthrough when final_bounding_box is None
- Skip when no watertight_mesh input
- Metadata correctness (scale_factor, bounding_box)
"""

from __future__ import annotations

import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
import trimesh

from backend.graph.configs.base import BaseNodeConfig
from backend.graph.context import AssetRegistry, NodeContext
from backend.graph.registry import registry


def _reset_registry() -> None:
    """Force re-discovery so newly added modules are registered."""
    import backend.graph.discovery as disc

    disc._discovered = False
    disc.discover_nodes()


@pytest.fixture(autouse=True, scope="module")
def _ensure_discovery() -> None:
    _reset_registry()


def _make_organic_spec(
    final_bounding_box: tuple[float, float, float] | None = None,
) -> dict:
    """Build a serialized OrganicSpec dict for ctx.get_data('organic_spec')."""
    from backend.models.organic import OrganicSpec

    spec = OrganicSpec(
        prompt_en="test shape",
        prompt_original="测试形状",
        shape_category="abstract",
        final_bounding_box=final_bounding_box,
    )
    return spec


def _make_test_mesh(
    extents: tuple[float, float, float] = (20.0, 30.0, 40.0),
    center: tuple[float, float, float] = (10.0, 15.0, 20.0),
) -> trimesh.Trimesh:
    """Create a box mesh with given extents centered at given center."""
    mesh = trimesh.primitives.Box(extents=extents).to_mesh()
    # Move center to specified location
    current_center = mesh.centroid
    offset = np.array(center) - current_center
    mesh.apply_translation(offset)
    return mesh


def _save_mesh_to_tmp(mesh: trimesh.Trimesh) -> str:
    """Export mesh to a temp file and return path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".glb", delete=False)
    mesh.export(tmp.name)
    tmp.close()
    return tmp.name


def _make_ctx(
    *,
    has_watertight: bool = True,
    mesh: trimesh.Trimesh | None = None,
    organic_spec: object | None = None,
) -> NodeContext:
    """Build a NodeContext for mesh_scale testing."""
    desc = registry.get("mesh_scale")
    asset_reg = AssetRegistry()

    mesh_path = ""
    if has_watertight:
        if mesh is None:
            mesh = _make_test_mesh()
        mesh_path = _save_mesh_to_tmp(mesh)
        asset_reg.put("watertight_mesh", mesh_path, "mesh", "mesh_healer")

    data: dict = {}
    if organic_spec is not None:
        data["organic_spec"] = organic_spec

    config = desc.config_model() if desc.config_model else BaseNodeConfig()
    ctx = NodeContext(
        job_id="test-scale-1",
        input_type="organic",
        assets=asset_reg,
        data=data,
        config=config,
        descriptor=desc,
        node_name="mesh_scale",
    )
    return ctx


# ---------------------------------------------------------------------------
# Skip / Passthrough tests
# ---------------------------------------------------------------------------


class TestMeshScaleSkipConditions:
    """Tests for passthrough and skip conditions."""

    @pytest.mark.asyncio
    async def test_skips_when_no_watertight_mesh(self) -> None:
        """No watertight_mesh -> sets mesh_scale_status=skipped_no_input."""
        from backend.graph.nodes.mesh_scale import mesh_scale_node

        ctx = _make_ctx(has_watertight=False)
        await mesh_scale_node(ctx)

        assert not ctx.has_asset("scaled_mesh")
        assert ctx.get_data("mesh_scale_status") == "skipped_no_input"

    @pytest.mark.asyncio
    async def test_passthrough_when_no_bounding_box(self) -> None:
        """final_bounding_box=None -> passes watertight_mesh directly as scaled_mesh."""
        from backend.graph.nodes.mesh_scale import mesh_scale_node

        spec = _make_organic_spec(final_bounding_box=None)
        ctx = _make_ctx(has_watertight=True, organic_spec=spec)

        await mesh_scale_node(ctx)

        assert ctx.has_asset("scaled_mesh")
        # Path should be the same as watertight_mesh (passthrough)
        watertight_path = ctx.get_asset("watertight_mesh").path
        scaled_path = ctx.get_asset("scaled_mesh").path
        assert scaled_path == watertight_path
        assert ctx.get_data("mesh_scale_status") == "passthrough"

    @pytest.mark.asyncio
    async def test_passthrough_when_no_organic_spec(self) -> None:
        """No organic_spec in data -> passthrough (same as no bounding box)."""
        from backend.graph.nodes.mesh_scale import mesh_scale_node

        ctx = _make_ctx(has_watertight=True, organic_spec=None)

        await mesh_scale_node(ctx)

        assert ctx.has_asset("scaled_mesh")
        assert ctx.get_data("mesh_scale_status") == "passthrough"


# ---------------------------------------------------------------------------
# Uniform scaling tests
# ---------------------------------------------------------------------------


class TestMeshScaleUniform:
    """Tests for uniform scaling logic."""

    @pytest.mark.asyncio
    async def test_uniform_scale_preserves_aspect_ratio(self) -> None:
        """Scale factor = min(target/current) for each axis."""
        from backend.graph.nodes.mesh_scale import mesh_scale_node

        # Mesh: 20x30x40, Target: 100x80x50
        # scale_factors: 100/20=5, 80/30=2.667, 50/40=1.25
        # uniform = min = 1.25
        mesh = _make_test_mesh(extents=(20.0, 30.0, 40.0))
        spec = _make_organic_spec(final_bounding_box=(100.0, 80.0, 50.0))
        ctx = _make_ctx(has_watertight=True, mesh=mesh, organic_spec=spec)

        await mesh_scale_node(ctx)

        assert ctx.has_asset("scaled_mesh")
        assert ctx.get_data("mesh_scale_status") == "scaled"

        # Verify metadata
        metadata = ctx.get_asset("scaled_mesh").metadata
        assert "scale_factor" in metadata
        assert abs(metadata["scale_factor"] - 1.25) < 0.01

    @pytest.mark.asyncio
    async def test_scale_factor_in_metadata(self) -> None:
        """Metadata should contain scale_factor and bounding_box."""
        from backend.graph.nodes.mesh_scale import mesh_scale_node

        mesh = _make_test_mesh(extents=(10.0, 10.0, 10.0))
        spec = _make_organic_spec(final_bounding_box=(50.0, 50.0, 50.0))
        ctx = _make_ctx(has_watertight=True, mesh=mesh, organic_spec=spec)

        await mesh_scale_node(ctx)

        metadata = ctx.get_asset("scaled_mesh").metadata
        assert "scale_factor" in metadata
        assert abs(metadata["scale_factor"] - 5.0) < 0.01
        assert "bounding_box" in metadata

    @pytest.mark.asyncio
    async def test_no_scale_when_already_fits(self) -> None:
        """If mesh already fits target, scale_factor ~ 1.0 (still processes alignment)."""
        from backend.graph.nodes.mesh_scale import mesh_scale_node

        mesh = _make_test_mesh(extents=(100.0, 80.0, 50.0))
        spec = _make_organic_spec(final_bounding_box=(100.0, 80.0, 50.0))
        ctx = _make_ctx(has_watertight=True, mesh=mesh, organic_spec=spec)

        await mesh_scale_node(ctx)

        assert ctx.has_asset("scaled_mesh")
        metadata = ctx.get_asset("scaled_mesh").metadata
        assert abs(metadata["scale_factor"] - 1.0) < 0.01


# ---------------------------------------------------------------------------
# Alignment tests (Z=0 and XY centering)
# ---------------------------------------------------------------------------


class TestMeshScaleAlignment:
    """Tests for post-scale alignment: Z=0 bottom + XY centering."""

    @pytest.mark.asyncio
    async def test_z_bottom_aligned_to_zero(self) -> None:
        """After scaling, mesh bottom (min Z) should be at Z=0."""
        from backend.graph.nodes.mesh_scale import mesh_scale_node

        # Mesh with Z range 10..50 (bottom at z=10)
        mesh = _make_test_mesh(
            extents=(20.0, 20.0, 40.0),
            center=(0.0, 0.0, 30.0),  # z range: 10..50
        )
        spec = _make_organic_spec(final_bounding_box=(40.0, 40.0, 80.0))
        ctx = _make_ctx(has_watertight=True, mesh=mesh, organic_spec=spec)

        await mesh_scale_node(ctx)

        # Load the output mesh and verify Z alignment
        scaled_path = ctx.get_asset("scaled_mesh").path
        scaled_mesh = trimesh.load(scaled_path, force="mesh")
        bounds = scaled_mesh.bounds  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
        assert abs(bounds[0][2]) < 0.01, f"Bottom Z should be ~0, got {bounds[0][2]}"

    @pytest.mark.asyncio
    async def test_xy_centroid_at_origin(self) -> None:
        """After scaling, mesh centroid X and Y should be ~0."""
        from backend.graph.nodes.mesh_scale import mesh_scale_node

        mesh = _make_test_mesh(
            extents=(20.0, 30.0, 40.0),
            center=(50.0, 60.0, 20.0),  # off-center
        )
        spec = _make_organic_spec(final_bounding_box=(100.0, 100.0, 100.0))
        ctx = _make_ctx(has_watertight=True, mesh=mesh, organic_spec=spec)

        await mesh_scale_node(ctx)

        scaled_path = ctx.get_asset("scaled_mesh").path
        scaled_mesh = trimesh.load(scaled_path, force="mesh")
        centroid = scaled_mesh.centroid
        assert abs(centroid[0]) < 0.01, f"Centroid X should be ~0, got {centroid[0]}"
        assert abs(centroid[1]) < 0.01, f"Centroid Y should be ~0, got {centroid[1]}"

    @pytest.mark.asyncio
    async def test_execution_order_scale_then_z_then_xy(self) -> None:
        """Verify execution order: 1) scale -> 2) Z=0 align -> 3) XY center.

        After all three steps:
        - Bottom Z = 0
        - Centroid X, Y = 0
        - Extents match uniform scale
        """
        from backend.graph.nodes.mesh_scale import mesh_scale_node

        # Mesh at odd position: 20x30x40, centered at (100, 200, 300)
        mesh = _make_test_mesh(
            extents=(20.0, 30.0, 40.0),
            center=(100.0, 200.0, 300.0),
        )
        # Target: (60, 90, 120), scale = min(60/20, 90/30, 120/40) = 3.0
        spec = _make_organic_spec(final_bounding_box=(60.0, 90.0, 120.0))
        ctx = _make_ctx(has_watertight=True, mesh=mesh, organic_spec=spec)

        await mesh_scale_node(ctx)

        scaled_path = ctx.get_asset("scaled_mesh").path
        scaled_mesh = trimesh.load(scaled_path, force="mesh")

        # Check extents: 20*3=60, 30*3=90, 40*3=120
        extents = scaled_mesh.bounding_box.extents
        assert abs(extents[0] - 60.0) < 0.1, f"X extent: expected 60, got {extents[0]}"
        assert abs(extents[1] - 90.0) < 0.1, f"Y extent: expected 90, got {extents[1]}"
        assert abs(extents[2] - 120.0) < 0.1, f"Z extent: expected 120, got {extents[2]}"

        # Check Z=0 alignment
        bounds = scaled_mesh.bounds
        assert abs(bounds[0][2]) < 0.1, f"Bottom Z: expected 0, got {bounds[0][2]}"

        # Check XY centering
        centroid = scaled_mesh.centroid
        assert abs(centroid[0]) < 0.1, f"Centroid X: expected 0, got {centroid[0]}"
        assert abs(centroid[1]) < 0.1, f"Centroid Y: expected 0, got {centroid[1]}"


# ---------------------------------------------------------------------------
# Output format tests
# ---------------------------------------------------------------------------


class TestMeshScaleOutput:
    """Tests for output asset registration and format."""

    @pytest.mark.asyncio
    async def test_produces_scaled_mesh_asset(self) -> None:
        """Node should produce a 'scaled_mesh' asset in the registry."""
        from backend.graph.nodes.mesh_scale import mesh_scale_node

        mesh = _make_test_mesh()
        spec = _make_organic_spec(final_bounding_box=(100.0, 100.0, 100.0))
        ctx = _make_ctx(has_watertight=True, mesh=mesh, organic_spec=spec)

        await mesh_scale_node(ctx)

        assert ctx.has_asset("scaled_mesh")
        asset = ctx.get_asset("scaled_mesh")
        assert asset.path.endswith((".glb", ".stl", ".obj"))

    @pytest.mark.asyncio
    async def test_metadata_has_bounding_box(self) -> None:
        """Metadata should contain final bounding box dimensions."""
        from backend.graph.nodes.mesh_scale import mesh_scale_node

        mesh = _make_test_mesh(extents=(10.0, 20.0, 30.0))
        spec = _make_organic_spec(final_bounding_box=(50.0, 100.0, 150.0))
        ctx = _make_ctx(has_watertight=True, mesh=mesh, organic_spec=spec)

        await mesh_scale_node(ctx)

        metadata = ctx.get_asset("scaled_mesh").metadata
        assert "bounding_box" in metadata
        bbox = metadata["bounding_box"]
        assert "x" in bbox and "y" in bbox and "z" in bbox

    @pytest.mark.asyncio
    async def test_state_diff_includes_new_assets(self) -> None:
        """to_state_diff() should include scaled_mesh in assets."""
        from backend.graph.nodes.mesh_scale import mesh_scale_node

        mesh = _make_test_mesh()
        spec = _make_organic_spec(final_bounding_box=(100.0, 100.0, 100.0))
        ctx = _make_ctx(has_watertight=True, mesh=mesh, organic_spec=spec)

        await mesh_scale_node(ctx)

        diff = ctx.to_state_diff()
        assert "assets" in diff
        assert "scaled_mesh" in diff["assets"]
