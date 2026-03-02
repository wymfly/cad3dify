"""Tests for benchmark framework — metrics, failure classification, and reporting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.benchmark.metrics import (
    BenchmarkMetrics,
    BenchmarkResult,
    FailureCategory,
    classify_failure,
)
from backend.benchmark.reporter import BenchmarkReporter


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------


class TestFailureClassification:
    def test_compile_error_maps_to_code_execution(self):
        assert classify_failure(compile_error="NameError: name 'cq' is not defined") == FailureCategory.CODE_EXECUTION

    def test_type_mismatch_maps_to_type_recognition(self):
        assert classify_failure(type_mismatch=True) == FailureCategory.TYPE_RECOGNITION

    def test_param_error_maps_to_dimension_deviation(self):
        assert classify_failure(param_error="diameter off by 50%") == FailureCategory.DIMENSION_DEVIATION

    def test_annotation_miss_maps_correctly(self):
        assert classify_failure(annotation_miss=True) == FailureCategory.ANNOTATION_MISS

    def test_structural_error_maps_correctly(self):
        assert classify_failure(structural_error="missing bore feature") == FailureCategory.STRUCTURAL_ERROR

    def test_no_failure_returns_none(self):
        assert classify_failure() is None

    def test_multiple_errors_returns_first_priority(self):
        # compile_error has higher priority than param_error
        result = classify_failure(compile_error="SyntaxError", param_error="diameter off")
        assert result == FailureCategory.CODE_EXECUTION


# ---------------------------------------------------------------------------
# Metrics calculation
# ---------------------------------------------------------------------------


class TestMetricsCalculation:
    def test_from_results_basic(self):
        results = [
            BenchmarkResult(
                case_id="case_001", compiled=True, type_correct=True,
                param_accuracy=0.95, bbox_match=True, duration_s=10.0, tokens_used=500,
            ),
            BenchmarkResult(
                case_id="case_002", compiled=True, type_correct=False,
                param_accuracy=0.80, bbox_match=False, duration_s=15.0, tokens_used=800,
            ),
            BenchmarkResult(
                case_id="case_003", compiled=False, type_correct=False,
                param_accuracy=0.0, bbox_match=False, duration_s=5.0, tokens_used=300,
            ),
        ]
        metrics = BenchmarkMetrics.from_results(results)
        assert metrics.compile_rate == pytest.approx(2 / 3)
        assert metrics.type_accuracy == pytest.approx(1 / 3)
        assert metrics.bbox_match_rate == pytest.approx(1 / 3)
        assert metrics.avg_duration_s == pytest.approx(10.0)
        assert metrics.avg_tokens == 533  # (500+800+300)/3 = 533

    def test_param_accuracy_p50_is_median(self):
        results = [
            BenchmarkResult(case_id="a", compiled=True, type_correct=True, param_accuracy=0.90, bbox_match=True, duration_s=1, tokens_used=100),
            BenchmarkResult(case_id="b", compiled=True, type_correct=True, param_accuracy=0.50, bbox_match=True, duration_s=1, tokens_used=100),
            BenchmarkResult(case_id="c", compiled=True, type_correct=True, param_accuracy=0.70, bbox_match=True, duration_s=1, tokens_used=100),
        ]
        metrics = BenchmarkMetrics.from_results(results)
        assert metrics.param_accuracy_p50 == pytest.approx(0.70)

    def test_empty_results(self):
        metrics = BenchmarkMetrics.from_results([])
        assert metrics.compile_rate == 0.0
        assert metrics.type_accuracy == 0.0
        assert metrics.param_accuracy_p50 == 0.0
        assert metrics.bbox_match_rate == 0.0
        assert metrics.avg_duration_s == 0.0
        assert metrics.avg_tokens == 0

    def test_all_pass(self):
        results = [
            BenchmarkResult(case_id="x", compiled=True, type_correct=True, param_accuracy=1.0, bbox_match=True, duration_s=8, tokens_used=400),
        ]
        metrics = BenchmarkMetrics.from_results(results)
        assert metrics.compile_rate == 1.0
        assert metrics.type_accuracy == 1.0
        assert metrics.bbox_match_rate == 1.0


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------


class TestReporter:
    def _make_sample_results(self) -> list[BenchmarkResult]:
        return [
            BenchmarkResult(case_id="case_001", compiled=True, type_correct=True, param_accuracy=0.95, bbox_match=True, duration_s=10.0, tokens_used=500),
            BenchmarkResult(case_id="case_002", compiled=True, type_correct=False, param_accuracy=0.80, bbox_match=False, duration_s=15.0, tokens_used=800, failure_category=FailureCategory.TYPE_RECOGNITION),
            BenchmarkResult(case_id="case_003", compiled=False, type_correct=False, param_accuracy=0.0, bbox_match=False, duration_s=5.0, tokens_used=300, failure_category=FailureCategory.CODE_EXECUTION),
        ]

    def test_markdown_report_contains_metrics(self):
        results = self._make_sample_results()
        metrics = BenchmarkMetrics.from_results(results)
        reporter = BenchmarkReporter()
        md = reporter.to_markdown(metrics, results, dataset="v1")
        assert "编译通过率" in md
        assert "类型准确率" in md
        assert "v1" in md

    def test_markdown_report_contains_failure_breakdown(self):
        results = self._make_sample_results()
        metrics = BenchmarkMetrics.from_results(results)
        reporter = BenchmarkReporter()
        md = reporter.to_markdown(metrics, results, dataset="v1")
        assert "CODE_EXECUTION" in md or "代码执行" in md
        assert "TYPE_RECOGNITION" in md or "类型识别" in md

    def test_json_report_export(self, tmp_path: Path):
        results = self._make_sample_results()
        metrics = BenchmarkMetrics.from_results(results)
        reporter = BenchmarkReporter()
        path = str(tmp_path / "report.json")
        reporter.to_json(metrics, results, path, dataset="v1")
        with open(path) as f:
            data = json.load(f)
        assert data["dataset"] == "v1"
        assert "metrics" in data
        assert data["metrics"]["compile_rate"] == pytest.approx(2 / 3)
        assert len(data["results"]) == 3

    def test_json_report_has_failure_stats(self, tmp_path: Path):
        results = self._make_sample_results()
        metrics = BenchmarkMetrics.from_results(results)
        reporter = BenchmarkReporter()
        path = str(tmp_path / "report.json")
        reporter.to_json(metrics, results, path, dataset="v1")
        with open(path) as f:
            data = json.load(f)
        assert "failure_breakdown" in data
        # Should have 2 failure categories
        assert len(data["failure_breakdown"]) == 2


# ---------------------------------------------------------------------------
# Runner — case loading
# ---------------------------------------------------------------------------


class TestRunner:
    def test_load_cases_from_v1_dataset(self):
        from backend.benchmark.runner import BenchmarkRunner

        runner = BenchmarkRunner()
        cases = runner.load_cases("benchmarks/v1")
        assert len(cases) == 7
        assert cases[0].case_id == "case_001_cylinder"
        assert cases[4].case_id == "case_005_bracket"
        assert cases[5].case_id == "case_006_text_cylinder"
        assert cases[6].case_id == "case_007_text_plate"

    def test_load_cases_missing_dir_raises(self):
        from backend.benchmark.runner import BenchmarkRunner

        runner = BenchmarkRunner()
        with pytest.raises(FileNotFoundError):
            runner.load_cases("benchmarks/nonexistent")


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


class TestBenchmarkAPI:
    def test_history_endpoint(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        resp = client.get("/api/v1/benchmark/history")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_report_not_found(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        resp = client.get("/api/v1/benchmark/history/nonexistent_id")
        assert resp.status_code == 404
