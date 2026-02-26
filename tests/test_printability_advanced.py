"""Tests for advanced printability analysis."""
from __future__ import annotations

import pytest

from backend.core.printability import (
    CorrectionAdvice,
    MaterialEstimate,
    OrientationAdvice,
    PrintabilityChecker,
    SupportAdvice,
    TimeEstimate,
)
from backend.models.printability import PrintIssue, PrintProfile, PrintabilityResult


@pytest.fixture
def checker():
    return PrintabilityChecker()


@pytest.fixture
def sample_geometry():
    return {
        "bounding_box": {"x": 100, "y": 80, "z": 60},
        "volume_cm3": 150.0,
        "min_wall_thickness": 1.2,
        "max_overhang_angle": 40,
        "min_hole_diameter": 3.0,
    }


# ---------------------------------------------------------------------------
# Orientation recommendation
# ---------------------------------------------------------------------------


class TestOrientationRecommendation:
    def test_recommends_axis(self, checker, sample_geometry):
        advice = checker.recommend_orientation(sample_geometry)
        assert advice.axis in ("X", "Y", "Z")
        assert advice.reason

    def test_prefers_largest_base(self, checker):
        """Should prefer Z-up when XY is largest face."""
        geo = {"bounding_box": {"x": 200, "y": 200, "z": 10}}
        advice = checker.recommend_orientation(geo)
        assert advice.axis == "Z"

    def test_prefers_y_when_xz_largest(self, checker):
        """Should prefer Y-up when XZ is largest face."""
        geo = {"bounding_box": {"x": 200, "y": 10, "z": 200}}
        advice = checker.recommend_orientation(geo)
        assert advice.axis == "Y"

    def test_missing_bbox_returns_default(self, checker):
        advice = checker.recommend_orientation({})
        assert advice.axis == "Z"  # default orientation

    def test_returns_orientation_advice_type(self, checker, sample_geometry):
        advice = checker.recommend_orientation(sample_geometry)
        assert isinstance(advice, OrientationAdvice)
        assert isinstance(advice.estimated_support_area_cm2, float)


# ---------------------------------------------------------------------------
# Support suggestion
# ---------------------------------------------------------------------------


class TestSupportSuggestion:
    def test_fdm_with_overhang(self, checker, sample_geometry):
        profile = PrintProfile(
            name="fdm_test",
            technology="FDM",
            min_wall_thickness=0.8,
            max_overhang_angle=45,
            min_hole_diameter=2.0,
            min_rib_thickness=0.8,
            build_volume=(220, 220, 250),
        )
        advice = checker.suggest_supports(profile, sample_geometry)
        assert advice.strategy in ("tree", "linear", "none")

    def test_sls_no_support(self, checker, sample_geometry):
        """SLS is self-supporting — strategy should be 'none'."""
        profile = PrintProfile(
            name="sls_test",
            technology="SLS",
            min_wall_thickness=0.7,
            max_overhang_angle=90,
            min_hole_diameter=1.5,
            min_rib_thickness=0.7,
            build_volume=(300, 300, 300),
        )
        advice = checker.suggest_supports(profile, sample_geometry)
        assert advice.strategy == "none"

    def test_returns_support_advice_type(self, checker, sample_geometry):
        profile = PrintProfile(
            name="fdm_test",
            technology="FDM",
            min_wall_thickness=0.8,
            max_overhang_angle=45,
            min_hole_diameter=2.0,
            min_rib_thickness=0.8,
            build_volume=(220, 220, 250),
        )
        advice = checker.suggest_supports(profile, sample_geometry)
        assert isinstance(advice, SupportAdvice)
        assert isinstance(advice.density_percent, float)


# ---------------------------------------------------------------------------
# Material estimate
# ---------------------------------------------------------------------------


class TestMaterialEstimate:
    def test_basic_estimate(self, checker):
        geo = {"volume_cm3": 100.0}
        est = checker.estimate_material(geo, infill_percent=20)
        assert est.filament_weight_g > 0
        assert est.filament_length_m > 0
        assert est.cost_estimate_cny > 0

    def test_higher_infill_more_material(self, checker):
        geo = {"volume_cm3": 100.0}
        low = checker.estimate_material(geo, infill_percent=10)
        high = checker.estimate_material(geo, infill_percent=50)
        assert high.filament_weight_g > low.filament_weight_g

    def test_zero_volume(self, checker):
        est = checker.estimate_material({"volume_cm3": 0}, infill_percent=20)
        assert est.filament_weight_g == 0

    def test_returns_material_estimate_type(self, checker):
        geo = {"volume_cm3": 50.0}
        est = checker.estimate_material(geo)
        assert isinstance(est, MaterialEstimate)


# ---------------------------------------------------------------------------
# Time estimate
# ---------------------------------------------------------------------------


class TestTimeEstimate:
    def test_basic_estimate(self, checker):
        geo = {"bounding_box": {"x": 100, "y": 80, "z": 60}}
        est = checker.estimate_print_time(geo, layer_height=0.2)
        assert est.total_minutes > 0
        assert est.layer_count == 300  # 60mm / 0.2mm

    def test_finer_layer_more_time(self, checker):
        geo = {"bounding_box": {"x": 100, "y": 80, "z": 60}}
        fast = checker.estimate_print_time(geo, layer_height=0.3)
        slow = checker.estimate_print_time(geo, layer_height=0.1)
        assert slow.total_minutes > fast.total_minutes

    def test_missing_bbox(self, checker):
        est = checker.estimate_print_time({})
        assert est.total_minutes == 0

    def test_returns_time_estimate_type(self, checker):
        geo = {"bounding_box": {"x": 50, "y": 50, "z": 20}}
        est = checker.estimate_print_time(geo)
        assert isinstance(est, TimeEstimate)
        assert isinstance(est.per_layer_seconds, float)


# ---------------------------------------------------------------------------
# Correction advice
# ---------------------------------------------------------------------------


class TestCorrectionAdvice:
    def test_thin_wall_correction(self, checker):
        issues = [
            PrintIssue(
                check="wall_thickness",
                severity="error",
                message="Wall too thin: 0.3mm < 0.8mm minimum",
                value=0.3,
                threshold=0.8,
            ),
        ]
        corrections = checker.suggest_corrections(issues)
        assert len(corrections) == 1
        assert "壁厚" in corrections[0].suggestion or "wall" in corrections[0].suggestion.lower()

    def test_overhang_correction(self, checker):
        issues = [
            PrintIssue(
                check="overhang",
                severity="warning",
                message="Overhang angle 55° exceeds 45°",
                value=55,
                threshold=45,
            ),
        ]
        corrections = checker.suggest_corrections(issues)
        assert len(corrections) >= 1

    def test_empty_issues(self, checker):
        corrections = checker.suggest_corrections([])
        assert corrections == []

    def test_returns_correction_advice_type(self, checker):
        issues = [
            PrintIssue(
                check="hole_diameter",
                severity="error",
                message="Hole too small",
                value=1.0,
                threshold=2.0,
            ),
        ]
        corrections = checker.suggest_corrections(issues)
        assert len(corrections) == 1
        assert isinstance(corrections[0], CorrectionAdvice)
        assert isinstance(corrections[0].auto_fixable, bool)


# ---------------------------------------------------------------------------
# PrintabilityResult extended fields
# ---------------------------------------------------------------------------


class TestPrintabilityResultExtended:
    def test_new_optional_fields_default_none(self):
        result = PrintabilityResult(
            printable=True,
            profile="fdm_standard",
            issues=[],
        )
        assert result.orientation is None
        assert result.support_advice is None
        assert result.material_estimate is None
        assert result.time_estimate is None
        assert result.corrections == []

    def test_new_fields_accept_dicts(self):
        result = PrintabilityResult(
            printable=True,
            profile="fdm_standard",
            issues=[],
            orientation={"axis": "Z", "rotation_deg": 0},
            support_advice={"strategy": "none", "density_percent": 0},
            material_estimate={"filament_weight_g": 50.0},
            time_estimate={"total_minutes": 120.0},
            corrections=[{"issue_type": "wall_thickness", "suggestion": "fix"}],
        )
        assert result.orientation["axis"] == "Z"
        assert result.corrections[0]["issue_type"] == "wall_thickness"
