"""Tests for backend.benchmark.runner — mocks pipeline & validator, tests runner logic."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.benchmark.metrics import BenchmarkMetrics, BenchmarkResult, FailureCategory
from backend.benchmark.runner import (
    BenchmarkCase,
    BenchmarkRunner,
    _check_bbox_match,
    _classify_exception,
    _compute_param_accuracy,
    _extract_numeric_values,
)


# ---------------------------------------------------------------------------
# Unit tests: _extract_numeric_values
# ---------------------------------------------------------------------------


class TestExtractNumericValues:
    def test_flat_dict(self):
        result = _extract_numeric_values({"diameter": 50.0, "height": 80})
        assert result == {"diameter": 50.0, "height": 80.0}

    def test_nested_dict(self):
        data = {"base_body": {"method": "revolve", "bore": {"diameter": 20.0}}}
        result = _extract_numeric_values(data)
        assert "base_body.bore.diameter" in result
        assert result["base_body.bore.diameter"] == 20.0

    def test_list_of_dicts(self):
        data = {"profile": [{"diameter": 60, "height": 30}, {"diameter": 40, "height": 50}]}
        result = _extract_numeric_values(data)
        assert result["profile[0].diameter"] == 60.0
        assert result["profile[1].height"] == 50.0

    def test_skips_booleans(self):
        data = {"through": True, "count": 6}
        result = _extract_numeric_values(data)
        assert "through" not in result
        assert result["count"] == 6.0

    def test_skips_tolerance_keys(self):
        data = {"xlen": 50, "tolerance_pct": 10}
        result = _extract_numeric_values(data)
        assert "tolerance_pct" not in result
        assert result["xlen"] == 50.0

    def test_empty_inputs(self):
        assert _extract_numeric_values({}) == {}
        assert _extract_numeric_values([]) == {}

    def test_string_values_ignored(self):
        data = {"method": "revolve", "diameter": 50}
        result = _extract_numeric_values(data)
        assert "method" not in result
        assert result["diameter"] == 50.0


# ---------------------------------------------------------------------------
# Unit tests: _compute_param_accuracy
# ---------------------------------------------------------------------------


class TestComputeParamAccuracy:
    def test_perfect_match(self):
        spec = {"diameter": 50, "height": 80}
        bbox = (50.0, 80.0, 50.0)
        assert _compute_param_accuracy(spec, bbox) == 1.0

    def test_partial_match(self):
        spec = {"diameter": 50, "height": 80, "bore": 20}
        bbox = (50.0, 80.0, 50.0)
        acc = _compute_param_accuracy(spec, bbox)
        assert acc == pytest.approx(2 / 3)

    def test_no_match(self):
        spec = {"diameter": 50}
        bbox = (200.0, 200.0, 200.0)
        assert _compute_param_accuracy(spec, bbox) == 0.0

    def test_none_bbox(self):
        assert _compute_param_accuracy({"diameter": 50}, None) == 0.0

    def test_empty_spec(self):
        assert _compute_param_accuracy({}, (50.0, 80.0, 50.0)) == 0.0

    def test_within_10_percent(self):
        spec = {"diameter": 50}
        bbox = (54.0, 200.0, 54.0)  # 54/50 = 1.08, within 10%
        assert _compute_param_accuracy(spec, bbox) == 1.0

    def test_outside_10_percent(self):
        spec = {"diameter": 50}
        bbox = (56.0, 200.0, 56.0)  # 56/50 = 1.12, outside 10%
        assert _compute_param_accuracy(spec, bbox) == 0.0

    def test_zero_actual_dims(self):
        spec = {"diameter": 50}
        bbox = (0.0, 0.0, 0.0)
        assert _compute_param_accuracy(spec, bbox) == 0.0


# ---------------------------------------------------------------------------
# Unit tests: _check_bbox_match
# ---------------------------------------------------------------------------


class TestCheckBboxMatch:
    def test_perfect_match(self):
        expected = {"xlen": 50, "ylen": 80, "zlen": 50}
        actual = (50.0, 80.0, 50.0)
        assert _check_bbox_match(expected, actual) is True

    def test_within_tolerance(self):
        expected = {"xlen": 50, "ylen": 80, "zlen": 50, "tolerance_pct": 15}
        actual = (56.0, 90.0, 56.0)  # 12%, 12.5%, 12%
        assert _check_bbox_match(expected, actual) is True

    def test_outside_tolerance(self):
        expected = {"xlen": 50, "ylen": 80, "zlen": 50, "tolerance_pct": 10}
        actual = (60.0, 80.0, 50.0)  # xlen: 20%
        assert _check_bbox_match(expected, actual) is False

    def test_none_bbox(self):
        assert _check_bbox_match({"xlen": 50}, None) is False

    def test_empty_expected(self):
        assert _check_bbox_match({}, (50.0, 80.0, 50.0)) is False

    def test_default_tolerance_15pct(self):
        expected = {"xlen": 100, "ylen": 100, "zlen": 100}
        actual = (114.0, 114.0, 114.0)  # 14%, within default 15%
        assert _check_bbox_match(expected, actual) is True

    def test_skips_zero_expected(self):
        expected = {"xlen": 0, "ylen": 80, "zlen": 50}
        actual = (999.0, 80.0, 50.0)
        assert _check_bbox_match(expected, actual) is True


# ---------------------------------------------------------------------------
# Unit tests: _classify_exception
# ---------------------------------------------------------------------------


class TestClassifyException:
    def test_compile_error(self):
        result = _classify_exception(RuntimeError("Compilation failed"))
        assert result == FailureCategory.CODE_EXECUTION

    def test_syntax_error(self):
        result = _classify_exception(SyntaxError("invalid syntax"))
        assert result == FailureCategory.CODE_EXECUTION

    def test_type_mismatch(self):
        result = _classify_exception(ValueError("Type mismatch detected"))
        assert result == FailureCategory.TYPE_RECOGNITION

    def test_template_not_found(self):
        result = _classify_exception(RuntimeError("Template not found"))
        assert result == FailureCategory.STRUCTURAL_ERROR

    def test_generic_error(self):
        result = _classify_exception(RuntimeError("Something went wrong"))
        assert result == FailureCategory.CODE_EXECUTION


# ---------------------------------------------------------------------------
# BenchmarkCase
# ---------------------------------------------------------------------------


class TestBenchmarkCase:
    def test_from_json_drawing(self, tmp_path):
        case_data = {
            "case_id": "test_drawing",
            "drawing_path": "test.png",
            "expected_spec": {"part_type": "rotational"},
            "expected_bbox": {"xlen": 50, "ylen": 80, "zlen": 50},
        }
        path = tmp_path / "case_test.json"
        path.write_text(json.dumps(case_data))

        case = BenchmarkCase.from_json(str(path))
        assert case.case_id == "test_drawing"
        assert case.input_type == "drawing"
        assert case.drawing_path.endswith("test.png")
        assert case.expected_spec["part_type"] == "rotational"

    def test_from_json_text(self, tmp_path):
        case_data = {
            "case_id": "test_text",
            "input_type": "text",
            "input_text": "一个圆柱体",
            "template_name": "cylinder_simple",
            "params": {"diameter": 50, "height": 80},
            "expected_spec": {"part_type": "rotational"},
            "expected_bbox": {"xlen": 50, "ylen": 80, "zlen": 50},
        }
        path = tmp_path / "case_test.json"
        path.write_text(json.dumps(case_data))

        case = BenchmarkCase.from_json(str(path))
        assert case.input_type == "text"
        assert case.input_text == "一个圆柱体"
        assert case.template_name == "cylinder_simple"
        assert case.params["diameter"] == 50

    def test_from_json_resolves_relative_path(self, tmp_path):
        case_data = {
            "case_id": "test_rel",
            "drawing_path": "images/part.png",
        }
        path = tmp_path / "case_rel.json"
        path.write_text(json.dumps(case_data))

        case = BenchmarkCase.from_json(str(path))
        assert str(tmp_path / "images" / "part.png") == case.drawing_path

    def test_from_json_defaults(self, tmp_path):
        case_data = {"case_id": "minimal"}
        path = tmp_path / "case_min.json"
        path.write_text(json.dumps(case_data))

        case = BenchmarkCase.from_json(str(path))
        assert case.input_type == "drawing"
        assert case.drawing_path == ""
        assert case.expected_spec == {}
        assert case.params == {}


# ---------------------------------------------------------------------------
# Runner: _run_single
# ---------------------------------------------------------------------------


class TestRunSingle:
    @pytest.fixture
    def runner(self, tmp_path):
        return BenchmarkRunner(reports_dir=str(tmp_path / "reports"))

    @pytest.fixture
    def drawing_case(self):
        return BenchmarkCase(
            case_id="test_draw_001",
            input_type="drawing",
            drawing_path="/tmp/test.png",
            expected_spec={
                "part_type": "rotational",
                "base_body": {"method": "revolve", "profile": [{"diameter": 50, "height": 80}]},
            },
            expected_bbox={"xlen": 50, "ylen": 80, "zlen": 50, "tolerance_pct": 15},
        )

    @pytest.fixture
    def text_case(self):
        return BenchmarkCase(
            case_id="test_text_001",
            input_type="text",
            input_text="一个圆柱体",
            template_name="cylinder_simple",
            params={"diameter": 50, "height": 80},
            expected_spec={"part_type": "rotational"},
            expected_bbox={"xlen": 50, "ylen": 80, "zlen": 50, "tolerance_pct": 15},
        )

    def test_drawing_success(self, runner, drawing_case):
        """Drawing case: pipeline succeeds, geometry valid, all metrics correct."""
        mock_geo = MagicMock(is_valid=True, volume=1000.0, bbox=(50.0, 80.0, 50.0), error="")

        with (
            patch.object(runner, "_run_drawing_case", new_callable=AsyncMock, return_value="# code"),
            patch("backend.core.validators.validate_step_geometry", return_value=mock_geo),
        ):
            result = asyncio.run(runner._run_single(drawing_case))

        assert result.compiled is True
        assert result.type_correct is True
        assert result.param_accuracy == 1.0
        assert result.bbox_match is True
        assert result.failure_category is None
        assert result.case_id == "test_draw_001"

    def test_drawing_pipeline_failure(self, runner, drawing_case):
        """Drawing case: pipeline raises RuntimeError."""
        with patch.object(
            runner,
            "_run_drawing_case",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Pipeline returned None — code generation failed"),
        ):
            result = asyncio.run(runner._run_single(drawing_case))

        assert result.compiled is False
        assert result.failure_category is not None
        assert "generation failed" in result.error_detail.lower()

    def test_drawing_invalid_geometry(self, runner, drawing_case):
        """Drawing case: pipeline succeeds but geometry validation fails."""
        mock_geo = MagicMock(is_valid=False, volume=0.0, bbox=None, error="Invalid solid")

        with (
            patch.object(runner, "_run_drawing_case", new_callable=AsyncMock, return_value="# code"),
            patch("backend.core.validators.validate_step_geometry", return_value=mock_geo),
        ):
            result = asyncio.run(runner._run_single(drawing_case))

        assert result.compiled is False
        assert result.failure_category == FailureCategory.CODE_EXECUTION
        assert "Invalid solid" in result.error_detail

    def test_drawing_bbox_mismatch_triggers_dimension_deviation(self, runner, drawing_case):
        """Drawing case: compiled but bbox way off -> DIMENSION_DEVIATION."""
        mock_geo = MagicMock(is_valid=True, volume=500.0, bbox=(200.0, 200.0, 200.0), error="")

        with (
            patch.object(runner, "_run_drawing_case", new_callable=AsyncMock, return_value="# code"),
            patch("backend.core.validators.validate_step_geometry", return_value=mock_geo),
        ):
            result = asyncio.run(runner._run_single(drawing_case))

        assert result.compiled is True
        assert result.bbox_match is False
        assert result.param_accuracy < 0.5
        assert result.failure_category == FailureCategory.DIMENSION_DEVIATION

    def test_text_success(self, runner, text_case):
        """Text case: SpecCompiler succeeds, geometry valid."""
        mock_geo = MagicMock(is_valid=True, volume=500.0, bbox=(50.0, 80.0, 50.0), error="")

        with (
            patch.object(runner, "_run_text_case", new_callable=AsyncMock),
            patch("backend.core.validators.validate_step_geometry", return_value=mock_geo),
        ):
            result = asyncio.run(runner._run_single(text_case))

        assert result.compiled is True
        assert result.bbox_match is True
        assert result.failure_category is None

    def test_text_compilation_error(self, runner, text_case):
        """Text case: SpecCompiler raises CompilationError."""
        with patch.object(
            runner,
            "_run_text_case",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Both template and LLM paths failed. compilation error"),
        ):
            result = asyncio.run(runner._run_single(text_case))

        assert result.compiled is False
        # "template" in error message → classified as STRUCTURAL_ERROR
        assert result.failure_category == FailureCategory.STRUCTURAL_ERROR

    def test_duration_is_positive(self, runner, drawing_case):
        """Ensure duration_s is always set."""
        with patch.object(
            runner,
            "_run_drawing_case",
            new_callable=AsyncMock,
            side_effect=RuntimeError("fail"),
        ):
            result = asyncio.run(runner._run_single(drawing_case))

        assert result.duration_s >= 0


# ---------------------------------------------------------------------------
# Runner: full run()
# ---------------------------------------------------------------------------


class TestFullRun:
    def test_run_with_dataset(self, tmp_path):
        """Full run() over a multi-case dataset."""
        mock_geo = MagicMock(is_valid=True, volume=1000.0, bbox=(50.0, 80.0, 50.0), error="")

        dataset = tmp_path / "dataset"
        dataset.mkdir()
        for i in range(3):
            case_data = {
                "case_id": f"case_{i:03d}",
                "drawing_path": "test.png",
                "expected_spec": {
                    "part_type": "rotational",
                    "base_body": {"method": "revolve", "profile": [{"diameter": 50, "height": 80}]},
                },
                "expected_bbox": {"xlen": 50, "ylen": 80, "zlen": 50},
            }
            (dataset / f"case_{i:03d}.json").write_text(json.dumps(case_data))

        runner = BenchmarkRunner(reports_dir=str(tmp_path / "reports"))

        with (
            patch.object(runner, "_run_drawing_case", new_callable=AsyncMock, return_value="# code"),
            patch("backend.core.validators.validate_step_geometry", return_value=mock_geo),
        ):
            report = asyncio.run(runner.run(str(dataset)))

        assert len(report.results) == 3
        assert report.metrics.compile_rate == 1.0
        assert report.metrics.type_accuracy == 1.0
        assert report.metrics.bbox_match_rate == 1.0
        assert report.dataset == "dataset"
        # Verify report was saved
        assert (tmp_path / "reports").exists()

    def test_run_empty_dataset(self, tmp_path):
        """run() on empty directory returns empty report."""
        dataset = tmp_path / "empty"
        dataset.mkdir()

        runner = BenchmarkRunner(reports_dir=str(tmp_path / "reports"))
        report = asyncio.run(runner.run(str(dataset)))

        assert len(report.results) == 0
        assert report.metrics.compile_rate == 0.0

    def test_run_missing_dataset(self, tmp_path):
        """run() on nonexistent directory raises FileNotFoundError."""
        runner = BenchmarkRunner(reports_dir=str(tmp_path / "reports"))
        with pytest.raises(FileNotFoundError):
            asyncio.run(runner.run(str(tmp_path / "nonexistent")))

    def test_run_mixed_cases(self, tmp_path):
        """Full run() with both drawing and text cases."""
        mock_geo = MagicMock(is_valid=True, volume=500.0, bbox=(50.0, 80.0, 50.0), error="")

        dataset = tmp_path / "mixed"
        dataset.mkdir()

        drawing_case = {
            "case_id": "case_draw",
            "drawing_path": "test.png",
            "expected_spec": {"part_type": "rotational"},
            "expected_bbox": {"xlen": 50, "ylen": 80, "zlen": 50},
        }
        text_case = {
            "case_id": "case_text",
            "input_type": "text",
            "input_text": "圆柱",
            "template_name": "cylinder",
            "params": {"diameter": 50},
            "expected_spec": {"part_type": "rotational"},
            "expected_bbox": {"xlen": 50, "ylen": 80, "zlen": 50},
        }
        (dataset / "case_draw.json").write_text(json.dumps(drawing_case))
        (dataset / "case_text.json").write_text(json.dumps(text_case))

        runner = BenchmarkRunner(reports_dir=str(tmp_path / "reports"))

        with (
            patch.object(runner, "_run_drawing_case", new_callable=AsyncMock, return_value="# code"),
            patch.object(runner, "_run_text_case", new_callable=AsyncMock),
            patch("backend.core.validators.validate_step_geometry", return_value=mock_geo),
        ):
            report = asyncio.run(runner.run(str(dataset)))

        assert len(report.results) == 2
        assert all(r.compiled for r in report.results)


# ---------------------------------------------------------------------------
# Metrics aggregation (via BenchmarkMetrics.from_results)
# ---------------------------------------------------------------------------


class TestMetricsAggregation:
    def test_from_results(self):
        results = [
            BenchmarkResult(
                case_id="c1", compiled=True, type_correct=True,
                param_accuracy=0.8, bbox_match=True, duration_s=1.0, tokens_used=100,
            ),
            BenchmarkResult(
                case_id="c2", compiled=True, type_correct=False,
                param_accuracy=0.6, bbox_match=False, duration_s=2.0, tokens_used=200,
            ),
            BenchmarkResult(
                case_id="c3", compiled=False, type_correct=False,
                param_accuracy=0.0, bbox_match=False, duration_s=0.5, tokens_used=50,
            ),
        ]
        metrics = BenchmarkMetrics.from_results(results)

        assert metrics.compile_rate == pytest.approx(2 / 3)
        assert metrics.type_accuracy == pytest.approx(1 / 3)
        assert metrics.param_accuracy_p50 == 0.6
        assert metrics.bbox_match_rate == pytest.approx(1 / 3)
        assert metrics.avg_duration_s == pytest.approx(3.5 / 3)
        assert metrics.avg_tokens == round(350 / 3)

    def test_from_empty_results(self):
        metrics = BenchmarkMetrics.from_results([])
        assert metrics.compile_rate == 0.0
        assert metrics.param_accuracy_p50 == 0.0


# ---------------------------------------------------------------------------
# Load cases from disk
# ---------------------------------------------------------------------------


class TestLoadCases:
    def test_load_cases_from_benchmarks_v1(self):
        """Verify the actual benchmarks/v1/ directory loads without error."""
        runner = BenchmarkRunner()
        cases = runner.load_cases("benchmarks/v1")

        assert len(cases) >= 7
        ids = {c.case_id for c in cases}
        assert "case_001_cylinder" in ids
        assert "case_006_text_cylinder" in ids

        text_cases = [c for c in cases if c.input_type == "text"]
        assert len(text_cases) >= 2

        drawing_cases = [c for c in cases if c.input_type == "drawing"]
        assert len(drawing_cases) >= 5
