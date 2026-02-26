"""Tests for topology validation."""
from __future__ import annotations

import pytest


class TestCountTopology:
    def test_simple_box(self, tmp_path) -> None:
        """A box has 6 faces, all planar, 1 solid, 1 shell."""
        import cadquery as cq

        step_path = str(tmp_path / "box.step")
        result = cq.Workplane("XY").box(100, 50, 30)
        cq.exporters.export(result, step_path)

        from backend.core.validators import count_topology

        topo = count_topology(step_path)
        assert topo.num_solids == 1
        assert topo.num_shells == 1
        assert topo.num_faces == 6
        assert topo.num_planar_faces == 6
        assert topo.num_cylindrical_faces == 0

    def test_cylinder_with_hole(self, tmp_path) -> None:
        """A cylinder with a through-hole has cylindrical faces."""
        import cadquery as cq

        step_path = str(tmp_path / "cyl_hole.step")
        result = (
            cq.Workplane("XY")
            .circle(50)
            .extrude(30)
            .faces(">Z")
            .workplane()
            .hole(20)
        )
        cq.exporters.export(result, step_path)

        from backend.core.validators import count_topology

        topo = count_topology(step_path)
        assert topo.num_solids == 1
        assert topo.num_cylindrical_faces >= 2  # outer + inner cylindrical

    def test_nonexistent_file(self) -> None:
        from backend.core.validators import count_topology

        topo = count_topology("/nonexistent.step")
        assert topo.error != ""


class TestCompareTopology:
    def test_topology_match(self) -> None:
        from backend.core.validators import TopologyResult, compare_topology

        actual = TopologyResult(
            num_solids=1,
            num_shells=1,
            num_faces=8,
            num_cylindrical_faces=2,
            num_planar_faces=6,
        )
        result = compare_topology(actual, expected_holes=1)
        assert result.passed is True

    def test_topology_mismatch_missing_holes(self) -> None:
        from backend.core.validators import TopologyResult, compare_topology

        actual = TopologyResult(
            num_solids=1,
            num_shells=1,
            num_faces=6,
            num_cylindrical_faces=0,
            num_planar_faces=6,
        )
        result = compare_topology(actual, expected_holes=3)
        assert result.passed is False
        assert len(result.mismatches) > 0

    def test_no_solids_fails(self) -> None:
        from backend.core.validators import TopologyResult, compare_topology

        actual = TopologyResult(num_solids=0)
        result = compare_topology(actual, expected_holes=0)
        assert result.passed is False
