import numpy as np
import pytest
import trimesh

from backend.core.vertex_analyzer import VertexAnalyzer, VertexAnalysisResult


class TestWallThickness:
    def test_solid_box_has_thickness(self, tmp_path):
        """A solid box: rays should find opposing faces."""
        mesh = trimesh.creation.box(extents=[10, 10, 10])
        path = str(tmp_path / "box.stl")
        mesh.export(path)
        result = VertexAnalyzer().analyze(path)
        assert result.wall_thickness.shape[0] == len(mesh.vertices)
        valid = result.wall_thickness[result.wall_thickness < 999.0]
        assert len(valid) > 0

    def test_sentinel_for_no_hit(self, tmp_path):
        """Open mesh edges may produce sentinel values."""
        # A single triangle has no opposing surface
        mesh = trimesh.Trimesh(
            vertices=[[0, 0, 0], [1, 0, 0], [0.5, 1, 0]], faces=[[0, 1, 2]]
        )
        path = str(tmp_path / "tri.stl")
        mesh.export(path)
        result = VertexAnalyzer().analyze(path)
        assert np.all(result.wall_thickness >= 999.0)


class TestOverhangAngle:
    def test_top_face_zero_degrees(self, tmp_path):
        """Cylinder top cap vertices have +Z normals → low overhang."""
        # Cylinder has interior cap vertices with pure +Z normals
        mesh = trimesh.creation.cylinder(radius=5, height=10, sections=32)
        mesh.apply_translation([0, 0, 10])
        path = str(tmp_path / "cyl_high.stl")
        mesh.export(path)
        result = VertexAnalyzer().analyze(path)
        assert np.any(result.overhang_angle < 5.0)

    def test_bottom_on_build_plate_excluded(self, tmp_path):
        """Bottom vertices at z≈0 with downward normals → 0° (build plate)."""
        mesh = trimesh.creation.cylinder(radius=5, height=2, sections=32)
        mesh.apply_translation([0, 0, 1])
        path = str(tmp_path / "plate.stl")
        mesh.export(path)
        result = VertexAnalyzer(build_plate_tolerance=0.5).analyze(path)
        bottom_mask = np.array(mesh.vertices)[:, 2] < 0.5
        if np.any(bottom_mask):
            # At least some bottom vertices should be excluded (set to 0°)
            assert np.any(result.overhang_angle[bottom_mask] < 1.0)

    def test_downward_face_elevated(self, tmp_path):
        """Elevated downward-facing surface → high overhang angle."""
        mesh = trimesh.creation.cylinder(radius=5, height=2, sections=32)
        mesh.apply_translation([0, 0, 20])
        path = str(tmp_path / "elevated.stl")
        mesh.export(path)
        result = VertexAnalyzer().analyze(path)
        # Bottom cap vertices should have high angle (~180°)
        assert np.any(result.overhang_angle > 90.0)


class TestRiskNormalization:
    def test_risk_range(self, tmp_path):
        """Risk values should be in [0, 1]."""
        mesh = trimesh.creation.box(extents=[10, 10, 10])
        path = str(tmp_path / "box.stl")
        mesh.export(path)
        result = VertexAnalyzer().analyze(path)
        assert np.all(result.risk_wall >= 0.0)
        assert np.all(result.risk_wall <= 1.0)
        assert np.all(result.risk_overhang >= 0.0)
        assert np.all(result.risk_overhang <= 1.0)

    def test_stats_populated(self, tmp_path):
        mesh = trimesh.creation.box(extents=[10, 10, 10])
        path = str(tmp_path / "box.stl")
        mesh.export(path)
        result = VertexAnalyzer().analyze(path)
        assert "vertices_analyzed" in result.stats
        assert "decimation_applied" in result.stats
