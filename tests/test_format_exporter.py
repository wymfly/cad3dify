"""Tests for FormatExporter — STEP → STL/glTF/3MF conversion.

These tests require real CadQuery and trimesh installations.
They are automatically skipped if dependencies are missing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import cadquery as cq

    _HAS_CADQUERY = True
except ImportError:
    _HAS_CADQUERY = False

try:
    import trimesh  # noqa: F401

    _HAS_TRIMESH = True
except ImportError:
    _HAS_TRIMESH = False

needs_cadquery = pytest.mark.skipif(not _HAS_CADQUERY, reason="cadquery not installed")
needs_trimesh = pytest.mark.skipif(not _HAS_TRIMESH, reason="trimesh not installed")


@pytest.fixture
def sample_step(tmp_path: Path) -> str:
    """Create a simple STEP file for testing."""
    if not _HAS_CADQUERY:
        pytest.skip("cadquery not installed")
    result = cq.Workplane("XY").box(10, 10, 10)
    step_path = str(tmp_path / "test.step")
    cq.exporters.export(result, step_path)
    return step_path


@needs_cadquery
def test_export_stl(sample_step: str, tmp_path: Path) -> None:
    from backend.core.format_exporter import ExportConfig, FormatExporter

    exporter = FormatExporter()
    out = str(tmp_path / "out.stl")
    exporter.export(sample_step, out, ExportConfig(format="stl"))
    assert Path(out).exists()
    assert Path(out).stat().st_size > 0


@needs_cadquery
@needs_trimesh
def test_export_gltf(sample_step: str, tmp_path: Path) -> None:
    from backend.core.format_exporter import ExportConfig, FormatExporter

    exporter = FormatExporter()
    out = str(tmp_path / "out.glb")
    exporter.export(sample_step, out, ExportConfig(format="gltf"))
    assert Path(out).exists()
    assert Path(out).stat().st_size > 0


@needs_cadquery
@needs_trimesh
def test_export_3mf(sample_step: str, tmp_path: Path) -> None:
    from backend.core.format_exporter import ExportConfig, FormatExporter

    exporter = FormatExporter()
    out = str(tmp_path / "out.3mf")
    exporter.export(sample_step, out, ExportConfig(format="3mf"))
    assert Path(out).exists()
    assert Path(out).stat().st_size > 0


@needs_cadquery
@needs_trimesh
def test_to_gltf_bytes(sample_step: str) -> None:
    from backend.core.format_exporter import FormatExporter

    exporter = FormatExporter()
    data = exporter.to_gltf_for_preview(sample_step)
    assert isinstance(data, bytes)
    assert len(data) > 0


def test_export_config_defaults() -> None:
    from backend.core.format_exporter import ExportConfig

    config = ExportConfig()
    assert config.format == "stl"
    assert config.linear_deflection == 0.1
    assert config.angular_deflection == 0.5
