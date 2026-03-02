import numpy as np
import pytest
import trimesh

from backend.core.format_exporter import FormatExporter


class TestDfamGlbExport:
    def test_export_creates_file(self, tmp_path):
        mesh = trimesh.creation.box(extents=[10, 10, 10])
        n = len(mesh.vertices)
        output = str(tmp_path / "model_dfam.glb")
        FormatExporter().export_dfam_glb(
            mesh=mesh,
            risk_wall=np.random.rand(n),
            risk_overhang=np.random.rand(n),
            wall_stats={
                "analysis_type": "wall_thickness",
                "threshold": 1.0,
                "min_value": 0.5,
                "max_value": 5.0,
                "vertices_at_risk_count": 10,
                "vertices_at_risk_percent": 5.0,
            },
            overhang_stats={
                "analysis_type": "overhang",
                "threshold": 45.0,
                "min_value": 0.0,
                "max_value": 90.0,
                "vertices_at_risk_count": 20,
                "vertices_at_risk_percent": 10.0,
            },
            output_path=output,
        )
        assert (tmp_path / "model_dfam.glb").exists()
        assert (tmp_path / "model_dfam.glb").stat().st_size > 0

    def test_two_named_meshes(self, tmp_path):
        mesh = trimesh.creation.box(extents=[10, 10, 10])
        n = len(mesh.vertices)
        output = str(tmp_path / "model_dfam.glb")
        FormatExporter().export_dfam_glb(
            mesh=mesh,
            risk_wall=np.ones(n),
            risk_overhang=np.zeros(n),
            wall_stats={
                "analysis_type": "wall_thickness",
                "threshold": 1.0,
                "min_value": 1.0,
                "max_value": 5.0,
                "vertices_at_risk_count": 0,
                "vertices_at_risk_percent": 0.0,
            },
            overhang_stats={
                "analysis_type": "overhang",
                "threshold": 45.0,
                "min_value": 0.0,
                "max_value": 45.0,
                "vertices_at_risk_count": 0,
                "vertices_at_risk_percent": 0.0,
            },
            output_path=output,
        )
        scene = trimesh.load(output)
        if hasattr(scene, "geometry"):
            names = list(scene.geometry.keys())
            assert "wall_thickness" in names, f"Missing wall_thickness in {names}"
            assert "overhang" in names, f"Missing overhang in {names}"

    def test_vertex_colors_present(self, tmp_path):
        mesh = trimesh.creation.box(extents=[10, 10, 10])
        n = len(mesh.vertices)
        risk = np.linspace(0, 1, n)
        output = str(tmp_path / "model_dfam.glb")
        FormatExporter().export_dfam_glb(
            mesh=mesh,
            risk_wall=risk,
            risk_overhang=risk,
            wall_stats={
                "analysis_type": "wall_thickness",
                "threshold": 1.0,
                "min_value": 0.0,
                "max_value": 10.0,
                "vertices_at_risk_count": 5,
                "vertices_at_risk_percent": 2.5,
            },
            overhang_stats={
                "analysis_type": "overhang",
                "threshold": 45.0,
                "min_value": 0.0,
                "max_value": 90.0,
                "vertices_at_risk_count": 10,
                "vertices_at_risk_percent": 5.0,
            },
            output_path=output,
        )
        scene = trimesh.load(output)
        for name in ["wall_thickness", "overhang"]:
            if name in scene.geometry:
                m = scene.geometry[name]
                assert m.visual.vertex_colors is not None
                assert len(m.visual.vertex_colors) == n
