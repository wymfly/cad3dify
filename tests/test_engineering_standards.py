"""Tests for engineering standards knowledge base (Phase 4 Task 4.3).

Validates:
- YAML data loading (5 categories)
- list_categories / get_category / get_entry
- recommend_params() for flange, bolt, gear, keyway
- check_constraints() for geometry, flange, gear
- Edge cases: unknown part_type, empty params, missing data
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from backend.core.engineering_standards import (
    ConstraintViolation,
    EngineeringStandards,
    ParamRecommendation,
    StandardEntry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def standards_dir(tmp_path: Path) -> Path:
    """Create a temporary standards directory with test YAML files."""
    d = tmp_path / "standards"
    d.mkdir()

    (d / "bolts.yaml").write_text(
        textwrap.dedent("""\
            standards:
              - name: "M6"
                params:
                  nominal_diameter: 6.0
                  pitch: 1.0
                  through_hole: 6.6
                  counterbore_dia: 11.0
                  counterbore_depth: 6.0
                  head_height: 4.0
              - name: "M10"
                params:
                  nominal_diameter: 10.0
                  pitch: 1.5
                  through_hole: 11.0
                  counterbore_dia: 17.5
                  counterbore_depth: 10.0
                  head_height: 6.4
              - name: "M20"
                params:
                  nominal_diameter: 20.0
                  pitch: 2.5
                  through_hole: 22.0
                  counterbore_dia: 33.0
                  counterbore_depth: 20.0
                  head_height: 12.5
        """),
        encoding="utf-8",
    )

    (d / "flanges.yaml").write_text(
        textwrap.dedent("""\
            standards:
              - name: "DN50"
                params:
                  nominal_diameter: 50
                  outer_diameter: 165.0
                  thickness: 18.0
                  pcd: 125.0
                  hole_count: 4
                  hole_diameter: 18.0
                  bore_diameter: 57.0
              - name: "DN100"
                params:
                  nominal_diameter: 100
                  outer_diameter: 220.0
                  thickness: 20.0
                  pcd: 180.0
                  hole_count: 8
                  hole_diameter: 18.0
                  bore_diameter: 108.0
              - name: "DN200"
                params:
                  nominal_diameter: 200
                  outer_diameter: 340.0
                  thickness: 24.0
                  pcd: 295.0
                  hole_count: 8
                  hole_diameter: 22.0
                  bore_diameter: 219.0
        """),
        encoding="utf-8",
    )

    (d / "tolerances.yaml").write_text(
        textwrap.dedent("""\
            standards:
              - name: "H7/h6"
                params:
                  fit_type: "clearance"
                  description: "间隙配合"
                  hole_upper_deviation: 0.021
                  hole_lower_deviation: 0.0
                  shaft_upper_deviation: 0.0
                  shaft_lower_deviation: -0.013
              - name: "H7/p6"
                params:
                  fit_type: "interference"
                  description: "过盈配合"
                  hole_upper_deviation: 0.021
                  hole_lower_deviation: 0.0
                  shaft_upper_deviation: 0.035
                  shaft_lower_deviation: 0.022
        """),
        encoding="utf-8",
    )

    (d / "keyways.yaml").write_text(
        textwrap.dedent("""\
            standards:
              - name: "d17-22"
                params:
                  shaft_diameter_min: 17.0
                  shaft_diameter_max: 22.0
                  key_width: 6.0
                  key_height: 6.0
                  shaft_groove_depth: 3.5
                  hub_groove_depth: 2.8
              - name: "d22-30"
                params:
                  shaft_diameter_min: 22.0
                  shaft_diameter_max: 30.0
                  key_width: 8.0
                  key_height: 7.0
                  shaft_groove_depth: 4.0
                  hub_groove_depth: 3.3
        """),
        encoding="utf-8",
    )

    (d / "gears.yaml").write_text(
        textwrap.dedent("""\
            standards:
              - name: "m1"
                params:
                  module: 1.0
                  pressure_angle: 20.0
                  min_teeth: 12
                  max_teeth: 150
                  addendum_coefficient: 1.0
                  dedendum_coefficient: 1.25
              - name: "m2"
                params:
                  module: 2.0
                  pressure_angle: 20.0
                  min_teeth: 14
                  max_teeth: 80
                  addendum_coefficient: 1.0
                  dedendum_coefficient: 1.25
              - name: "m5"
                params:
                  module: 5.0
                  pressure_angle: 20.0
                  min_teeth: 16
                  max_teeth: 45
                  addendum_coefficient: 1.0
                  dedendum_coefficient: 1.25
        """),
        encoding="utf-8",
    )

    return d


@pytest.fixture()
def eng(standards_dir: Path) -> EngineeringStandards:
    """Create an EngineeringStandards instance from the test YAML files."""
    return EngineeringStandards(standards_dir=standards_dir)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


class TestDataLoading:
    def test_loads_all_five_categories(self, eng: EngineeringStandards) -> None:
        cats = eng.list_categories()
        assert len(cats) == 5
        assert set(cats) == {"bolt", "flange", "tolerance", "keyway", "gear"}

    def test_bolt_entries_count(self, eng: EngineeringStandards) -> None:
        bolts = eng.get_category("bolt")
        assert len(bolts) == 3

    def test_flange_entries_count(self, eng: EngineeringStandards) -> None:
        flanges = eng.get_category("flange")
        assert len(flanges) == 3

    def test_tolerance_entries_count(self, eng: EngineeringStandards) -> None:
        tols = eng.get_category("tolerance")
        assert len(tols) == 2

    def test_keyway_entries_count(self, eng: EngineeringStandards) -> None:
        kws = eng.get_category("keyway")
        assert len(kws) == 2

    def test_gear_entries_count(self, eng: EngineeringStandards) -> None:
        gears = eng.get_category("gear")
        assert len(gears) == 3

    def test_entry_is_standard_entry(self, eng: EngineeringStandards) -> None:
        bolts = eng.get_category("bolt")
        assert all(isinstance(e, StandardEntry) for e in bolts)

    def test_entry_has_correct_category(self, eng: EngineeringStandards) -> None:
        for entry in eng.get_category("flange"):
            assert entry.category == "flange"


# ---------------------------------------------------------------------------
# get_entry
# ---------------------------------------------------------------------------


class TestGetEntry:
    def test_get_existing_bolt(self, eng: EngineeringStandards) -> None:
        entry = eng.get_entry("bolt", "M10")
        assert entry is not None
        assert entry.params["nominal_diameter"] == 10.0
        assert entry.params["through_hole"] == 11.0

    def test_get_existing_flange(self, eng: EngineeringStandards) -> None:
        entry = eng.get_entry("flange", "DN100")
        assert entry is not None
        assert entry.params["outer_diameter"] == 220.0

    def test_get_nonexistent_entry(self, eng: EngineeringStandards) -> None:
        assert eng.get_entry("bolt", "M99") is None

    def test_get_nonexistent_category(self, eng: EngineeringStandards) -> None:
        assert eng.get_entry("spring", "S1") is None

    def test_unknown_category_returns_empty(self, eng: EngineeringStandards) -> None:
        assert eng.get_category("nonexistent") == []


# ---------------------------------------------------------------------------
# recommend_params — flange
# ---------------------------------------------------------------------------


class TestRecommendFlange:
    def test_recommend_from_outer_diameter_220(self, eng: EngineeringStandards) -> None:
        """outer_diameter=220 should match DN100 and recommend its params."""
        recs = eng.recommend_params("rotational", {"outer_diameter": 220.0})
        names = {r.param_name for r in recs}
        assert "thickness" in names
        assert "pcd" in names
        assert "hole_count" in names
        assert "hole_diameter" in names

    def test_recommend_flange_values(self, eng: EngineeringStandards) -> None:
        """Check actual recommended values for DN100."""
        recs = eng.recommend_params("rotational", {"outer_diameter": 220.0})
        by_name = {r.param_name: r for r in recs}
        assert by_name["thickness"].value == 20.0
        assert by_name["pcd"].value == 180.0
        assert by_name["hole_count"].value == 8.0

    def test_recommend_closest_match(self, eng: EngineeringStandards) -> None:
        """outer_diameter=200 is closer to DN50 (165) vs DN100 (220) — picks DN100 (diff 20 < 35)."""
        recs = eng.recommend_params("rotational", {"outer_diameter": 200.0})
        by_name = {r.param_name: r for r in recs}
        # 200 is closer to DN100 (220, diff=20) than DN50 (165, diff=35)
        assert by_name["pcd"].value == 180.0

    def test_no_recommendation_without_outer_diameter(self, eng: EngineeringStandards) -> None:
        recs = eng.recommend_params("rotational", {"thickness": 15.0})
        # No flange recommendations without outer_diameter (bolt recs also empty)
        assert recs == []

    def test_skips_already_known_params(self, eng: EngineeringStandards) -> None:
        """Should not recommend params that are already known."""
        recs = eng.recommend_params(
            "rotational",
            {"outer_diameter": 220.0, "thickness": 15.0, "pcd": 170.0},
        )
        names = {r.param_name for r in recs}
        assert "thickness" not in names
        assert "pcd" not in names


# ---------------------------------------------------------------------------
# recommend_params — bolt
# ---------------------------------------------------------------------------


class TestRecommendBolt:
    def test_m10_through_hole(self, eng: EngineeringStandards) -> None:
        """M10 bolt → through_hole = 11.0mm."""
        recs = eng.recommend_params("rotational", {"outer_diameter": 220.0, "bolt_size": 10.0})
        bolt_recs = [r for r in recs if r.param_name == "through_hole"]
        assert len(bolt_recs) == 1
        assert bolt_recs[0].value == 11.0

    def test_m10_counterbore(self, eng: EngineeringStandards) -> None:
        recs = eng.recommend_params("rotational", {"outer_diameter": 220.0, "bolt_size": 10.0})
        cb_recs = [r for r in recs if r.param_name == "counterbore_dia"]
        assert len(cb_recs) == 1
        assert cb_recs[0].value == 17.5

    def test_unknown_bolt_size(self, eng: EngineeringStandards) -> None:
        recs = eng.recommend_params("rotational", {"outer_diameter": 220.0, "bolt_size": 99.0})
        bolt_recs = [r for r in recs if r.param_name == "through_hole"]
        assert bolt_recs == []


# ---------------------------------------------------------------------------
# recommend_params — gear
# ---------------------------------------------------------------------------


class TestRecommendGear:
    def test_gear_module_2(self, eng: EngineeringStandards) -> None:
        recs = eng.recommend_params("gear", {"module": 2.0})
        names = {r.param_name for r in recs}
        assert "min_teeth" in names
        assert "pressure_angle" in names

    def test_gear_pressure_angle_value(self, eng: EngineeringStandards) -> None:
        recs = eng.recommend_params("gear", {"module": 2.0})
        pa = [r for r in recs if r.param_name == "pressure_angle"][0]
        assert pa.value == 20.0
        assert pa.unit == "deg"


# ---------------------------------------------------------------------------
# recommend_params — keyway
# ---------------------------------------------------------------------------


class TestRecommendKeyway:
    def test_keyway_shaft_20(self, eng: EngineeringStandards) -> None:
        """Shaft diameter 20mm → key_width=6, shaft_groove_depth=3.5."""
        recs = eng.recommend_params("rotational_stepped", {"shaft_diameter": 20.0})
        by_name = {r.param_name: r for r in recs}
        assert by_name["key_width"].value == 6.0
        assert by_name["shaft_groove_depth"].value == 3.5

    def test_keyway_shaft_25(self, eng: EngineeringStandards) -> None:
        """Shaft diameter 25mm → key_width=8."""
        recs = eng.recommend_params("rotational_stepped", {"shaft_diameter": 25.0})
        by_name = {r.param_name: r for r in recs}
        assert by_name["key_width"].value == 8.0

    def test_keyway_no_shaft_diameter(self, eng: EngineeringStandards) -> None:
        recs = eng.recommend_params("rotational_stepped", {"width": 10.0})
        assert recs == []


# ---------------------------------------------------------------------------
# recommend_params — edge cases
# ---------------------------------------------------------------------------


class TestRecommendEdgeCases:
    def test_unknown_part_type(self, eng: EngineeringStandards) -> None:
        recs = eng.recommend_params("unknown_type", {"outer_diameter": 100.0})
        assert recs == []

    def test_empty_params(self, eng: EngineeringStandards) -> None:
        recs = eng.recommend_params("rotational", {})
        assert recs == []

    def test_recommendation_is_pydantic_model(self, eng: EngineeringStandards) -> None:
        recs = eng.recommend_params("rotational", {"outer_diameter": 220.0})
        assert all(isinstance(r, ParamRecommendation) for r in recs)

    def test_recommendation_has_source(self, eng: EngineeringStandards) -> None:
        recs = eng.recommend_params("rotational", {"outer_diameter": 220.0})
        for r in recs:
            assert r.source != ""


# ---------------------------------------------------------------------------
# check_constraints — flange OK
# ---------------------------------------------------------------------------


class TestCheckConstraintsOK:
    def test_valid_flange_params(self, eng: EngineeringStandards) -> None:
        violations = eng.check_constraints(
            "rotational",
            {
                "outer_diameter": 220.0,
                "pcd": 180.0,
                "hole_diameter": 18.0,
                "hole_count": 8,
                "bore_diameter": 108.0,
            },
        )
        assert violations == []

    def test_valid_params_no_violations(self, eng: EngineeringStandards) -> None:
        violations = eng.check_constraints(
            "rotational",
            {"outer_diameter": 100.0, "bore_diameter": 30.0},
        )
        assert violations == []


# ---------------------------------------------------------------------------
# check_constraints — flange violations
# ---------------------------------------------------------------------------


class TestCheckConstraintsViolations:
    def test_pcd_exceeds_outer_diameter(self, eng: EngineeringStandards) -> None:
        violations = eng.check_constraints(
            "rotational",
            {"outer_diameter": 100.0, "pcd": 120.0},
        )
        assert len(violations) >= 1
        assert any("pcd" in v.constraint for v in violations)

    def test_bore_exceeds_outer_diameter(self, eng: EngineeringStandards) -> None:
        violations = eng.check_constraints(
            "rotational",
            {"outer_diameter": 50.0, "bore_diameter": 60.0},
        )
        assert any("bore_diameter" in v.constraint for v in violations)

    def test_holes_overlap(self, eng: EngineeringStandards) -> None:
        # pcd*pi/hole_count = 30*pi/4 ≈ 23.6, so hole_diameter=30 > 23.6 → overlap
        violations = eng.check_constraints(
            "rotational",
            {
                "outer_diameter": 200.0,
                "pcd": 30.0,
                "hole_diameter": 30.0,
                "hole_count": 4,
            },
        )
        assert any("hole_diameter" in v.constraint for v in violations)

    def test_wall_thickness_warning(self, eng: EngineeringStandards) -> None:
        violations = eng.check_constraints(
            "rotational",
            {"outer_diameter": 100.0, "wall_thickness": 0.5},
        )
        warnings = [v for v in violations if v.severity == "warning"]
        assert len(warnings) >= 1

    def test_violation_is_pydantic_model(self, eng: EngineeringStandards) -> None:
        violations = eng.check_constraints(
            "rotational",
            {"outer_diameter": 50.0, "bore_diameter": 60.0},
        )
        assert all(isinstance(v, ConstraintViolation) for v in violations)


# ---------------------------------------------------------------------------
# check_constraints — gear
# ---------------------------------------------------------------------------


class TestCheckConstraintsGear:
    def test_gear_low_teeth_warning(self, eng: EngineeringStandards) -> None:
        violations = eng.check_constraints("gear", {"module": 2.0, "teeth": 10})
        assert any("teeth" in v.constraint for v in violations)

    def test_gear_negative_module(self, eng: EngineeringStandards) -> None:
        violations = eng.check_constraints("gear", {"module": -1.0})
        assert any("module" in v.constraint for v in violations)

    def test_gear_valid_params(self, eng: EngineeringStandards) -> None:
        violations = eng.check_constraints("gear", {"module": 2.0, "teeth": 30})
        assert violations == []


# ---------------------------------------------------------------------------
# check_constraints — edge cases
# ---------------------------------------------------------------------------


class TestCheckConstraintsEdgeCases:
    def test_unknown_part_type_basic_checks_only(self, eng: EngineeringStandards) -> None:
        # Unknown type still runs basic geometry checks
        violations = eng.check_constraints(
            "unknown",
            {"outer_diameter": 50.0, "bore_diameter": 60.0},
        )
        assert len(violations) >= 1

    def test_empty_params(self, eng: EngineeringStandards) -> None:
        violations = eng.check_constraints("rotational", {})
        assert violations == []


# ---------------------------------------------------------------------------
# Loading from real data directory
# ---------------------------------------------------------------------------


class TestRealDataLoading:
    """Test loading from the actual project standards directory (if available)."""

    def test_real_standards_dir_loads(self) -> None:
        """Load from the real standards directory and verify all categories present."""
        real_dir = (
            Path(__file__).resolve().parent.parent
            / "backend"
            / "knowledge"
            / "standards"
        )
        if not real_dir.exists():
            pytest.skip("Real standards directory not found")
        eng = EngineeringStandards(standards_dir=real_dir)
        cats = eng.list_categories()
        assert len(cats) == 5
        # Verify minimum entry counts from real data
        assert len(eng.get_category("bolt")) >= 9
        assert len(eng.get_category("flange")) >= 12
        assert len(eng.get_category("gear")) >= 13
