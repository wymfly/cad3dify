"""Tests for multi-model voting and self-consistency aggregation."""

import pytest

from backend.core.voting import (
    AggregatedResult,
    FieldConfidence,
    VotingAggregator,
    aggregate_categorical,
    aggregate_numeric,
)
from backend.knowledge.part_types import BaseBodySpec, DrawingSpec, PartType


class TestAggregateNumeric:
    def test_median_of_three(self):
        assert aggregate_numeric([100.0, 105.0, 100.0]) == 100.0

    def test_median_of_two(self):
        assert aggregate_numeric([100.0, 110.0]) == 105.0

    def test_single_value(self):
        assert aggregate_numeric([50.0]) == 50.0

    def test_empty(self):
        assert aggregate_numeric([]) is None

    def test_median_of_five(self):
        assert aggregate_numeric([10.0, 20.0, 30.0, 40.0, 50.0]) == 30.0

    def test_all_same(self):
        assert aggregate_numeric([42.0, 42.0, 42.0]) == 42.0

    def test_integers_treated_as_float(self):
        result = aggregate_numeric([1.0, 2.0, 3.0])
        assert isinstance(result, float)


class TestAggregateCategorical:
    def test_majority(self):
        assert aggregate_categorical(["rotational", "rotational", "plate"]) == "rotational"

    def test_tie_returns_first(self):
        # Counter.most_common returns first-seen on tie in CPython
        result = aggregate_categorical(["rotational", "plate"])
        assert result in ("rotational", "plate")

    def test_single(self):
        assert aggregate_categorical(["gear"]) == "gear"

    def test_empty(self):
        assert aggregate_categorical([]) is None

    def test_all_same(self):
        assert aggregate_categorical(["housing", "housing", "housing"]) == "housing"

    def test_three_way_tie(self):
        result = aggregate_categorical(["rotational", "plate", "gear"])
        assert result in ("rotational", "plate", "gear")


class TestFieldConfidence:
    def test_all_agree_high(self):
        fc = FieldConfidence.from_values([100.0, 100.0, 100.0])
        assert fc.confidence >= 0.9
        assert fc.is_consistent is True

    def test_disagreement_low(self):
        fc = FieldConfidence.from_values([100.0, 200.0, 150.0])
        assert fc.confidence < 0.9
        assert fc.is_consistent is False

    def test_categorical_agree(self):
        fc = FieldConfidence.from_values(["rotational", "rotational", "rotational"])
        assert fc.confidence >= 0.9

    def test_categorical_disagree(self):
        fc = FieldConfidence.from_values(["rotational", "plate", "gear"])
        assert fc.confidence < 0.5

    def test_single_numeric_is_consistent(self):
        """Single value should always be consistent."""
        fc = FieldConfidence.from_values([100.0])
        assert fc.is_consistent is True
        assert fc.confidence == 1.0

    def test_single_categorical_is_consistent(self):
        fc = FieldConfidence.from_values(["rotational"])
        assert fc.is_consistent is True
        assert fc.confidence == 1.0

    def test_empty_values(self):
        fc = FieldConfidence.from_values([])
        assert fc.confidence == 0.0
        assert fc.is_consistent is False

    def test_small_numeric_variation_is_consistent(self):
        """CV < 0.1 should be considered consistent."""
        fc = FieldConfidence.from_values([100.0, 101.0, 99.0])
        assert fc.is_consistent is True

    def test_large_numeric_variation_is_inconsistent(self):
        """Large spread should be inconsistent."""
        fc = FieldConfidence.from_values([10.0, 100.0, 1000.0])
        assert fc.is_consistent is False

    def test_zero_mean_numeric(self):
        """Zero mean should not cause division by zero."""
        fc = FieldConfidence.from_values([0.0, 0.0, 0.0])
        assert fc.is_consistent is True
        assert fc.confidence == 1.0

    def test_categorical_majority_2_of_3(self):
        fc = FieldConfidence.from_values(["rotational", "rotational", "plate"])
        assert fc.is_consistent is True  # 2/3 > 0.5
        assert fc.confidence == pytest.approx(2 / 3)

    def test_values_stored(self):
        fc = FieldConfidence.from_values([1.0, 2.0, 3.0])
        assert fc.values == [1.0, 2.0, 3.0]


class TestAggregatedResult:
    def test_basic_fields(self):
        spec = DrawingSpec(
            part_type="rotational",
            description="test",
            overall_dimensions={"diameter": 100.0},
            base_body=BaseBodySpec(method="revolve"),
        )
        result = AggregatedResult(spec=spec, source_count=3)
        assert result.spec == spec
        assert result.source_count == 3
        assert result.field_confidences == {}


class TestVotingAggregator:
    def _make_spec(self, part_type: str, diameter: float) -> DrawingSpec:
        return DrawingSpec(
            part_type=part_type,
            description="test",
            overall_dimensions={"max_diameter": diameter},
            base_body=BaseBodySpec(method="revolve"),
            features=[],
        )

    def test_aggregate_consistent_specs(self):
        specs = [
            self._make_spec("rotational", 100),
            self._make_spec("rotational", 100),
            self._make_spec("rotational", 102),
        ]
        agg = VotingAggregator()
        result = agg.aggregate(specs)
        assert result is not None
        assert result.spec.part_type == PartType.ROTATIONAL
        assert result.spec.overall_dimensions["max_diameter"] == 100.0

    def test_aggregate_type_voting(self):
        specs = [
            self._make_spec("rotational", 100),
            self._make_spec("rotational", 100),
            self._make_spec("plate", 100),
        ]
        agg = VotingAggregator()
        result = agg.aggregate(specs)
        assert result is not None
        assert result.spec.part_type == PartType.ROTATIONAL

    def test_aggregate_single_spec(self):
        specs = [self._make_spec("gear", 50)]
        agg = VotingAggregator()
        result = agg.aggregate(specs)
        assert result is not None
        assert result.spec.part_type == PartType.GEAR

    def test_confidence_map(self):
        specs = [
            self._make_spec("rotational", 100),
            self._make_spec("rotational", 200),  # outlier
            self._make_spec("rotational", 100),
        ]
        agg = VotingAggregator()
        result = agg.aggregate(specs)
        assert result is not None
        # max_diameter has inconsistency
        conf = result.field_confidences.get("max_diameter")
        assert conf is not None
        assert conf.is_consistent is False

    def test_empty_specs_returns_none(self):
        agg = VotingAggregator()
        result = agg.aggregate([])
        assert result is None

    def test_source_count(self):
        specs = [
            self._make_spec("rotational", 100),
            self._make_spec("rotational", 100),
            self._make_spec("rotational", 100),
        ]
        agg = VotingAggregator()
        result = agg.aggregate(specs)
        assert result is not None
        assert result.source_count == 3

    def test_part_type_confidence_included(self):
        specs = [
            self._make_spec("rotational", 100),
            self._make_spec("plate", 100),
            self._make_spec("rotational", 100),
        ]
        agg = VotingAggregator()
        result = agg.aggregate(specs)
        assert result is not None
        assert "part_type" in result.field_confidences

    def test_method_voting(self):
        """base_body.method should be aggregated by majority vote."""
        spec1 = DrawingSpec(
            part_type="rotational",
            description="test",
            overall_dimensions={"diameter": 100},
            base_body=BaseBodySpec(method="revolve"),
        )
        spec2 = DrawingSpec(
            part_type="rotational",
            description="test",
            overall_dimensions={"diameter": 100},
            base_body=BaseBodySpec(method="extrude"),
        )
        spec3 = DrawingSpec(
            part_type="rotational",
            description="test",
            overall_dimensions={"diameter": 100},
            base_body=BaseBodySpec(method="revolve"),
        )
        agg = VotingAggregator()
        result = agg.aggregate([spec1, spec2, spec3])
        assert result is not None
        assert result.spec.base_body.method == "revolve"

    def test_description_from_first_spec(self):
        """Description should be taken from the first spec."""
        spec1 = DrawingSpec(
            part_type="rotational",
            description="first description",
            overall_dimensions={"diameter": 100},
            base_body=BaseBodySpec(method="revolve"),
        )
        spec2 = DrawingSpec(
            part_type="rotational",
            description="second description",
            overall_dimensions={"diameter": 100},
            base_body=BaseBodySpec(method="revolve"),
        )
        agg = VotingAggregator()
        result = agg.aggregate([spec1, spec2])
        assert result is not None
        assert result.spec.description == "first description"

    def test_features_from_first_spec(self):
        """Features should be taken from first spec (simplified merging)."""
        from backend.knowledge.part_types import Feature

        spec1 = DrawingSpec(
            part_type="rotational",
            description="test",
            overall_dimensions={"diameter": 100},
            base_body=BaseBodySpec(method="revolve"),
            features=[Feature(type="fillet", spec={"radius": 3.0})],
        )
        spec2 = DrawingSpec(
            part_type="rotational",
            description="test",
            overall_dimensions={"diameter": 100},
            base_body=BaseBodySpec(method="revolve"),
            features=[Feature(type="chamfer", spec={"size": 2.0})],
        )
        agg = VotingAggregator()
        result = agg.aggregate([spec1, spec2])
        assert result is not None
        assert len(result.spec.features) == 1
        assert result.spec.features[0].type == "fillet"

    def test_union_of_dimension_keys(self):
        """All dimension keys from all specs should be present."""
        spec1 = DrawingSpec(
            part_type="rotational",
            description="test",
            overall_dimensions={"diameter": 100, "height": 50},
            base_body=BaseBodySpec(method="revolve"),
        )
        spec2 = DrawingSpec(
            part_type="rotational",
            description="test",
            overall_dimensions={"diameter": 100, "width": 30},
            base_body=BaseBodySpec(method="revolve"),
        )
        agg = VotingAggregator()
        result = agg.aggregate([spec1, spec2])
        assert result is not None
        dims = result.spec.overall_dimensions
        assert "diameter" in dims
        assert "height" in dims
        assert "width" in dims
