"""Tests for the Refiner subgraph (Compare -> Fix -> Re-execute cycle)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_lcel_chains.py)
# ---------------------------------------------------------------------------


class _FakeChatModel:
    """Minimal fake that supports ``with_retry()`` and ``|`` (pipe) operator."""

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.retry_kwargs: dict | None = None

    def with_retry(self, **kwargs) -> RunnableLambda:
        self.retry_kwargs = kwargs
        return RunnableLambda(
            lambda _input: AIMessage(content=self._response_text)
        )

    def invoke(self, input):
        return AIMessage(content=self._response_text)


def _setup_mock_model(mock_get_model, response_text: str) -> _FakeChatModel:
    """Wire up get_model_for_role -> ChatModelParameters -> _FakeChatModel."""
    fake_llm = _FakeChatModel(response_text)
    mock_get_model.return_value.create_chat_model.return_value = fake_llm
    return fake_llm


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DUMMY_SPEC_DICT = {
    "part_type": "rotational",
    "description": "test cylinder",
    "views": ["front"],
    "overall_dimensions": {"max_diameter": 50.0, "total_height": 30.0},
    "base_body": {
        "method": "revolve",
        "profile": [{"diameter": 50.0, "height": 30.0}],
    },
    "features": [],
    "notes": [],
}


def _make_refiner_state(**overrides) -> dict:
    """Create a minimal RefinerState dict for testing."""
    base = {
        "code": "import cadquery as cq\nresult = cq.Workplane('XY').cylinder(30, 25)",
        "step_path": "/tmp/test.step",
        "drawing_spec": _DUMMY_SPEC_DICT,
        "image_path": "/tmp/test_drawing.png",
        "round": 0,
        "max_rounds": 3,
        "verdict": "pending",
        "static_notes": [],
        "comparison_result": None,
        "rendered_image_path": None,
        "prev_score": None,
        "prev_code": None,
        "prev_step_path": None,
    }
    base.update(overrides)
    return base


def _make_config(**pipeline_overrides) -> dict:
    """Create a LangGraph config dict with PipelineConfig."""
    from backend.models.pipeline_config import PipelineConfig

    pc = PipelineConfig(**pipeline_overrides)
    return {"configurable": {"pipeline_config": pc}}


# ---------------------------------------------------------------------------
# Node unit tests
# ---------------------------------------------------------------------------


class TestStaticDiagnose:
    def test_runs_without_step_file(self):
        """static_diagnose should not crash when step_path is empty."""
        from backend.graph.subgraphs.refiner import static_diagnose

        state = _make_refiner_state(step_path="")
        config = _make_config()
        result = static_diagnose(state, config)
        assert "static_notes" in result
        assert isinstance(result["static_notes"], list)

    @patch("backend.graph.subgraphs.refiner.validate_step_geometry")
    @patch("backend.graph.subgraphs.refiner.validate_code_params")
    def test_collects_param_mismatches(self, mock_params, mock_geo):
        from backend.graph.subgraphs.refiner import static_diagnose
        from backend.core.validators import ValidationResult

        mock_params.return_value = ValidationResult(
            passed=False,
            mismatches=["overall_height: expected 30, found 40"],
            warnings=["bore_diameter: expected 10, not found"],
        )
        mock_geo.return_value = MagicMock(is_valid=False, bbox=None)

        state = _make_refiner_state()
        config = _make_config()
        result = static_diagnose(state, config)

        notes = result["static_notes"]
        assert any("Param mismatch" in n for n in notes)
        assert any("Param warning" in n for n in notes)


class TestRenderForCompare:
    @patch("backend.graph.subgraphs.refiner.render_and_export_image")
    @patch("backend.graph.subgraphs.refiner.render_multi_view")
    def test_multi_view_fallback_to_single(self, mock_multi, mock_single):
        """Falls back to single view when multi-view fails."""
        from backend.graph.subgraphs.refiner import render_for_compare

        mock_multi.side_effect = RuntimeError("No CadQuery")
        mock_single.return_value = None  # render_and_export_image returns None

        state = _make_refiner_state()
        config = _make_config(multi_view_render=True)
        result = render_for_compare(state, config)

        assert "rendered_image_path" in result
        mock_multi.assert_called_once()
        mock_single.assert_called_once()


# ---------------------------------------------------------------------------
# Integration tests (subgraph execution)
# ---------------------------------------------------------------------------


class TestRefinerSubgraphIntegration:
    """Integration tests running the full subgraph with mocked externals."""

    @patch("backend.graph.subgraphs.refiner._score_geometry")
    @patch("backend.graph.subgraphs.refiner.SafeExecutor")
    @patch("backend.graph.subgraphs.refiner.ImageData")
    @patch("backend.graph.subgraphs.refiner.render_and_export_image")
    @patch("backend.graph.subgraphs.refiner.render_multi_view")
    @patch("backend.graph.subgraphs.refiner.validate_step_geometry")
    @patch("backend.graph.subgraphs.refiner.validate_code_params")
    @patch("backend.graph.chains.compare_chain.get_model_for_role")
    def test_pass_first_round(
        self,
        mock_compare_model,
        mock_params,
        mock_geo,
        mock_multi_render,
        mock_single_render,
        mock_image_data,
        mock_executor_cls,
        mock_score_geo,
    ):
        """VL returns PASS on first round -> 1 round exit, verdict='pass'."""
        from backend.core.validators import ValidationResult
        from backend.graph.subgraphs.refiner import build_refiner_subgraph

        # Static diagnose mocks
        mock_params.return_value = ValidationResult(passed=True)
        mock_geo.return_value = MagicMock(is_valid=True, bbox=(50.0, 50.0, 30.0))

        # Render mocks
        mock_multi_render.return_value = {"isometric": "/tmp/iso.png"}

        # ImageData mock
        mock_img = MagicMock()
        mock_img.type = "png"
        mock_img.data = "base64data"
        mock_image_data.load_from_file.return_value = mock_img

        # Compare chain: PASS (returns None)
        _setup_mock_model(mock_compare_model, "PASS")

        graph = build_refiner_subgraph()
        state = _make_refiner_state()
        config = _make_config()

        result = graph.invoke(state, config=config)

        assert result["verdict"] == "pass"
        assert result["round"] == 0  # no fix rounds executed

    @patch("backend.graph.subgraphs.refiner._score_geometry")
    @patch("backend.graph.subgraphs.refiner.SafeExecutor")
    @patch("backend.graph.subgraphs.refiner.ImageData")
    @patch("backend.graph.subgraphs.refiner.render_and_export_image")
    @patch("backend.graph.subgraphs.refiner.render_multi_view")
    @patch("backend.graph.subgraphs.refiner.validate_step_geometry")
    @patch("backend.graph.subgraphs.refiner.validate_code_params")
    @patch("backend.graph.chains.fix_chain.get_model_for_role")
    @patch("backend.graph.chains.compare_chain.get_model_for_role")
    def test_max_rounds_exit(
        self,
        mock_compare_model,
        mock_fix_model,
        mock_params,
        mock_geo,
        mock_multi_render,
        mock_single_render,
        mock_image_data,
        mock_executor_cls,
        mock_score_geo,
    ):
        """VL always returns FAIL -> exits with max_rounds_reached after max_rounds."""
        from backend.core.validators import ValidationResult
        from backend.graph.subgraphs.refiner import build_refiner_subgraph

        # Static diagnose mocks
        mock_params.return_value = ValidationResult(passed=True)
        mock_geo.return_value = MagicMock(is_valid=True, bbox=(50.0, 50.0, 30.0))

        # Render mocks
        mock_multi_render.return_value = {"isometric": "/tmp/iso.png"}

        # ImageData mock
        mock_img = MagicMock()
        mock_img.type = "png"
        mock_img.data = "base64data"
        mock_image_data.load_from_file.return_value = mock_img

        # Compare chain: always FAIL
        _setup_mock_model(
            mock_compare_model,
            "FAIL: diameter is too large, expected 50mm got 60mm",
        )

        # Fix chain: return fixed code
        _setup_mock_model(
            mock_fix_model,
            "```python\nimport cadquery as cq\nresult = cq.Workplane('XY').cylinder(30, 25)\n```",
        )

        # Executor mock
        mock_exec_instance = MagicMock()
        mock_exec_instance.execute.return_value = MagicMock(
            success=True, stdout="", stderr=""
        )
        mock_executor_cls.return_value = mock_exec_instance

        # Score geometry: compiled + reasonable score
        mock_score_geo.return_value = (True, True, True, False)

        max_rounds = 2
        graph = build_refiner_subgraph()
        state = _make_refiner_state(max_rounds=max_rounds)
        config = _make_config(max_refinements=max_rounds, rollback_on_degrade=False)

        result = graph.invoke(state, config=config)

        assert result["verdict"] == "max_rounds_reached"
        assert result["round"] >= max_rounds

    @patch("backend.graph.subgraphs.refiner._score_geometry")
    @patch("backend.graph.subgraphs.refiner.SafeExecutor")
    @patch("backend.graph.subgraphs.refiner.ImageData")
    @patch("backend.graph.subgraphs.refiner.render_and_export_image")
    @patch("backend.graph.subgraphs.refiner.render_multi_view")
    @patch("backend.graph.subgraphs.refiner.validate_step_geometry")
    @patch("backend.graph.subgraphs.refiner.validate_code_params")
    @patch("backend.graph.chains.fix_chain.get_model_for_role")
    @patch("backend.graph.chains.compare_chain.get_model_for_role")
    def test_rollback_on_score_degradation(
        self,
        mock_compare_model,
        mock_fix_model,
        mock_params,
        mock_geo,
        mock_multi_render,
        mock_single_render,
        mock_image_data,
        mock_executor_cls,
        mock_score_geo,
    ):
        """New code scores lower than prev_score -> rollback to previous code."""
        from backend.core.validators import ValidationResult
        from backend.graph.subgraphs.refiner import build_refiner_subgraph

        # Static diagnose mocks
        mock_params.return_value = ValidationResult(passed=True)
        mock_geo.return_value = MagicMock(is_valid=True, bbox=(50.0, 50.0, 30.0))

        # Render mocks
        mock_multi_render.return_value = {"isometric": "/tmp/iso.png"}

        # ImageData mock
        mock_img = MagicMock()
        mock_img.type = "png"
        mock_img.data = "base64data"
        mock_image_data.load_from_file.return_value = mock_img

        # Compare chain: FAIL (triggers fix)
        _setup_mock_model(
            mock_compare_model,
            "FAIL: shape is wrong",
        )

        # Fix chain: return "degraded" code
        degraded_code = "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)"
        _setup_mock_model(
            mock_fix_model,
            f"```python\n{degraded_code}\n```",
        )

        # Executor mock
        mock_exec_instance = MagicMock()
        mock_exec_instance.execute.return_value = MagicMock(
            success=True, stdout="", stderr=""
        )
        mock_executor_cls.return_value = mock_exec_instance

        # Score: first round gives low score (triggers rollback against prev_score)
        # compiled=True, volume=False, bbox=False, topology=False -> score=50
        mock_score_geo.return_value = (True, False, False, False)

        original_code = "import cadquery as cq\nresult = cq.Workplane('XY').cylinder(30, 25)"

        graph = build_refiner_subgraph()
        state = _make_refiner_state(
            code=original_code,
            max_rounds=1,
            prev_score=90.0,  # High previous score
        )
        config = _make_config(
            max_refinements=1,
            rollback_on_degrade=True,
        )

        result = graph.invoke(state, config=config)

        # After rollback, code should revert to original
        assert result["code"] == original_code

    @patch("backend.graph.subgraphs.refiner._score_geometry")
    @patch("backend.graph.subgraphs.refiner.SafeExecutor")
    @patch("backend.graph.subgraphs.refiner.ImageData")
    @patch("backend.graph.subgraphs.refiner.render_and_export_image")
    @patch("backend.graph.subgraphs.refiner.render_multi_view")
    @patch("backend.graph.subgraphs.refiner.validate_step_geometry")
    @patch("backend.graph.subgraphs.refiner.validate_code_params")
    @patch("backend.graph.chains.fix_chain.get_model_for_role")
    @patch("backend.graph.chains.compare_chain.get_model_for_role")
    def test_comparison_result_available_in_coder_fix(
        self,
        mock_compare_model,
        mock_fix_model,
        mock_params,
        mock_geo,
        mock_multi_render,
        mock_single_render,
        mock_image_data,
        mock_executor_cls,
        mock_score_geo,
    ):
        """coder_fix can read comparison_result from vl_compare."""
        from backend.core.validators import ValidationResult
        from backend.graph.subgraphs.refiner import build_refiner_subgraph

        # Static diagnose mocks
        mock_params.return_value = ValidationResult(passed=True)
        mock_geo.return_value = MagicMock(is_valid=True, bbox=(50.0, 50.0, 30.0))

        # Render mocks
        mock_multi_render.return_value = {"isometric": "/tmp/iso.png"}

        # ImageData mock
        mock_img = MagicMock()
        mock_img.type = "png"
        mock_img.data = "base64data"
        mock_image_data.load_from_file.return_value = mock_img

        # Compare chain: specific feedback text
        comparison_feedback = "FAIL: The bore diameter should be 10mm not 15mm"
        _setup_mock_model(mock_compare_model, comparison_feedback)

        # Fix chain: capture the input to verify comparison_result is passed
        fix_invocations = []
        original_fix_model = _FakeChatModel(
            "```python\nimport cadquery as cq\nresult = cq.Workplane('XY').cylinder(30, 25)\n```"
        )

        def _capturing_retry(**kwargs):
            original_fix_model.retry_kwargs = kwargs
            def _run(input_dict):
                fix_invocations.append(input_dict)
                return AIMessage(
                    content="```python\nimport cadquery as cq\nresult = cq.Workplane('XY').cylinder(30, 25)\n```"
                )
            return RunnableLambda(_run)

        original_fix_model.with_retry = _capturing_retry
        mock_fix_model.return_value.create_chat_model.return_value = original_fix_model

        # Executor mock
        mock_exec_instance = MagicMock()
        mock_exec_instance.execute.return_value = MagicMock(
            success=True, stdout="", stderr=""
        )
        mock_executor_cls.return_value = mock_exec_instance

        # Score geometry
        mock_score_geo.return_value = (True, True, True, True)

        graph = build_refiner_subgraph()
        state = _make_refiner_state(max_rounds=1)
        config = _make_config(max_refinements=1, rollback_on_degrade=False)

        result = graph.invoke(state, config=config)

        # Verify fix chain was called and received comparison feedback
        assert len(fix_invocations) >= 1
        fix_input = fix_invocations[0]
        # The fix_instructions should contain the VL comparison feedback
        assert "bore diameter" in fix_input.messages[0].content[0]["text"]


# ---------------------------------------------------------------------------
# State mapping tests
# ---------------------------------------------------------------------------


class TestStateMapping:
    def test_map_job_to_refiner_with_drawing_spec_object(self):
        from backend.graph.subgraphs.refiner import map_job_to_refiner
        from backend.knowledge.part_types import DrawingSpec

        spec = DrawingSpec(**_DUMMY_SPEC_DICT)
        state = {
            "generated_code": "code_here",
            "step_path": "/tmp/out.step",
            "drawing_spec": spec,
            "image_path": "/tmp/drawing.png",
        }
        config = _make_config(max_refinements=5)

        result = map_job_to_refiner(state, config)

        assert result["code"] == "code_here"
        assert result["max_rounds"] == 5
        assert isinstance(result["drawing_spec"], dict)
        assert result["drawing_spec"]["part_type"] == "rotational"

    def test_map_job_to_refiner_with_dict_spec(self):
        from backend.graph.subgraphs.refiner import map_job_to_refiner

        state = {
            "generated_code": "code_here",
            "step_path": "/tmp/out.step",
            "drawing_spec": _DUMMY_SPEC_DICT,
            "image_path": "/tmp/drawing.png",
        }
        config = _make_config()

        result = map_job_to_refiner(state, config)
        assert result["drawing_spec"] == _DUMMY_SPEC_DICT

    def test_map_refiner_to_job(self):
        from backend.graph.subgraphs.refiner import map_refiner_to_job

        refiner_state = _make_refiner_state(
            code="final_code",
            step_path="/tmp/final.step",
        )

        result = map_refiner_to_job(refiner_state)
        assert result["generated_code"] == "final_code"
        assert result["step_path"] == "/tmp/final.step"
