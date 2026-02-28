"""Tests for CadJobState and STATE_TO_ORM_MAPPING."""

from backend.graph.state import CadJobState, STATE_TO_ORM_MAPPING


class TestCadJobState:
    def test_state_has_required_fields(self) -> None:
        hints = CadJobState.__annotations__
        required = [
            "job_id", "input_type", "input_text", "image_path",
            "intent", "matched_template", "drawing_spec",
            "confirmed_params", "confirmed_spec", "disclaimer_accepted",
            "step_path", "model_url", "printability",
            "status", "error", "failure_reason",
        ]
        for field in required:
            assert field in hints, f"Missing field: {field}"

    def test_state_to_orm_mapping_covers_key_fields(self) -> None:
        assert STATE_TO_ORM_MAPPING["confirmed_spec"] == "drawing_spec_confirmed"
        assert STATE_TO_ORM_MAPPING["printability"] == "printability_result"
        assert STATE_TO_ORM_MAPPING["step_path"] == "output_step_path"

    def test_state_to_orm_mapping_values_are_strings(self) -> None:
        for k, v in STATE_TO_ORM_MAPPING.items():
            assert isinstance(k, str)
            assert isinstance(v, str)
