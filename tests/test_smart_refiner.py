"""Tests for SmartRefiner three-layer defense."""

from unittest.mock import MagicMock, patch

import pytest

from cad3dify.knowledge.part_types import (
    BaseBodySpec,
    BoreSpec,
    DimensionLayer,
    DrawingSpec,
    PartType,
)
from cad3dify.v2.smart_refiner import SmartRefiner


def _make_spec() -> DrawingSpec:
    return DrawingSpec(
        part_type=PartType.ROTATIONAL_STEPPED,
        description="test flange",
        views=["front_section"],
        overall_dimensions={"max_diameter": 100, "total_height": 30},
        base_body=BaseBodySpec(
            method="revolve",
            profile=[
                DimensionLayer(diameter=100, height=10, label="base"),
            ],
            bore=BoreSpec(diameter=10, through=True),
        ),
        features=[],
    )


class TestSmartRefinerGuard:
    """Test the three-layer defense logic without hitting real LLM APIs."""

    def _make_refiner(self) -> SmartRefiner:
        """Create a SmartRefiner with mocked chains (no LLM init)."""
        with patch.object(SmartRefiner, "__init__", lambda self: None):
            refiner = SmartRefiner()
            refiner.compare_chain = MagicMock()
            refiner.fix_chain = MagicMock()
            return refiner

    def test_static_fail_triggers_fix_without_vl(self):
        """Layer 1: static validation fails → fix chain called, VL skipped."""
        refiner = self._make_refiner()
        refiner.fix_chain.invoke.return_value = {"result": "fixed_code"}

        bad_code = "d_base = 50\n"  # should be 100
        result = refiner.refine(
            code=bad_code,
            original_image=MagicMock(),
            rendered_image=MagicMock(),
            drawing_spec=_make_spec(),
        )

        refiner.fix_chain.invoke.assert_called_once()
        refiner.compare_chain.invoke.assert_not_called()
        assert result == "fixed_code"

    def test_correct_code_reaches_vl(self):
        """Layers 1-2 pass → VL comparison is reached."""
        refiner = self._make_refiner()
        refiner.compare_chain.invoke.return_value = {"result": None}  # VL PASS

        good_code = "d_base = 100\nh_base = 10\nd_bore = 10\ntotal_height = 30\n"
        result = refiner.refine(
            code=good_code,
            original_image=MagicMock(),
            rendered_image=MagicMock(),
            drawing_spec=_make_spec(),
        )

        refiner.compare_chain.invoke.assert_called_once()
        refiner.fix_chain.invoke.assert_not_called()
        assert result is None  # PASS

    def test_vl_finds_issue_triggers_fix(self):
        """VL comparison finds differences → fix chain called."""
        refiner = self._make_refiner()
        refiner.compare_chain.invoke.return_value = {"result": "问题1: 孔数不对"}
        refiner.fix_chain.invoke.return_value = {"result": "fixed_code_vl"}

        good_code = "d_base = 100\nh_base = 10\nd_bore = 10\ntotal_height = 30\n"
        result = refiner.refine(
            code=good_code,
            original_image=MagicMock(),
            rendered_image=MagicMock(),
            drawing_spec=_make_spec(),
        )

        refiner.compare_chain.invoke.assert_called_once()
        refiner.fix_chain.invoke.assert_called_once()
        assert result == "fixed_code_vl"

    @patch("cad3dify.v2.smart_refiner._get_bbox_from_step")
    def test_bbox_fail_triggers_fix_without_vl(self, mock_bbox):
        """Layer 2: bbox validation fails → fix chain called, VL skipped."""
        mock_bbox.return_value = (50.0, 50.0, 10.0)  # way off from 100×100×30

        refiner = self._make_refiner()
        refiner.fix_chain.invoke.return_value = {"result": "bbox_fixed"}

        good_code = "d_base = 100\nh_base = 10\nd_bore = 10\ntotal_height = 30\n"
        result = refiner.refine(
            code=good_code,
            original_image=MagicMock(),
            rendered_image=MagicMock(),
            drawing_spec=_make_spec(),
            step_filepath="/fake/output.step",
        )

        refiner.fix_chain.invoke.assert_called_once()
        refiner.compare_chain.invoke.assert_not_called()
        assert result == "bbox_fixed"

    @patch("cad3dify.v2.smart_refiner._get_bbox_from_step")
    def test_bbox_pass_reaches_vl(self, mock_bbox):
        """Layer 2: bbox passes → proceeds to VL."""
        mock_bbox.return_value = (100.0, 100.0, 30.0)  # matches spec

        refiner = self._make_refiner()
        refiner.compare_chain.invoke.return_value = {"result": None}  # VL PASS

        good_code = "d_base = 100\nh_base = 10\nd_bore = 10\ntotal_height = 30\n"
        result = refiner.refine(
            code=good_code,
            original_image=MagicMock(),
            rendered_image=MagicMock(),
            drawing_spec=_make_spec(),
            step_filepath="/fake/output.step",
        )

        refiner.compare_chain.invoke.assert_called_once()
        assert result is None

    def test_no_step_filepath_skips_bbox(self):
        """No step_filepath → bbox check skipped, goes directly to VL."""
        refiner = self._make_refiner()
        refiner.compare_chain.invoke.return_value = {"result": None}

        good_code = "d_base = 100\nh_base = 10\nd_bore = 10\ntotal_height = 30\n"
        result = refiner.refine(
            code=good_code,
            original_image=MagicMock(),
            rendered_image=MagicMock(),
            drawing_spec=_make_spec(),
            step_filepath=None,
        )

        refiner.compare_chain.invoke.assert_called_once()
        assert result is None
