"""Benchmark runner — iterate over a dataset, run the pipeline, collect metrics.

Usage (CLI):
    python -m backend.benchmark.runner --dataset benchmarks/v1/

Usage (programmatic):
    runner = BenchmarkRunner()
    report = await runner.run("benchmarks/v1/")
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator

from .metrics import BenchmarkMetrics, BenchmarkResult, FailureCategory, classify_failure
from .reporter import BenchmarkReporter


# ---------------------------------------------------------------------------
# Benchmark case (loaded from JSON)
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkCase:
    """A single benchmark test case loaded from the dataset."""

    case_id: str
    drawing_path: str
    expected_spec: dict = field(default_factory=dict)
    expected_bbox: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, path: str) -> BenchmarkCase:
        with open(path) as f:
            data = json.load(f)
        base_dir = str(Path(path).parent)
        drawing_path = data.get("drawing_path", "")
        if drawing_path and not Path(drawing_path).is_absolute():
            drawing_path = str(Path(base_dir) / drawing_path)
        return cls(
            case_id=data["case_id"],
            drawing_path=drawing_path,
            expected_spec=data.get("expected_spec", {}),
            expected_bbox=data.get("expected_bbox", {}),
        )


# ---------------------------------------------------------------------------
# Report container
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkReport:
    """Full benchmark run report."""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    dataset: str = ""
    metrics: BenchmarkMetrics = field(default_factory=BenchmarkMetrics)
    results: list[BenchmarkResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class BenchmarkRunner:
    """Load dataset, run pipeline on each case, aggregate results."""

    def __init__(self, reports_dir: str = "benchmark_reports") -> None:
        self._reports_dir = Path(reports_dir)
        self._reporter = BenchmarkReporter()

    def load_cases(self, dataset_dir: str) -> list[BenchmarkCase]:
        """Load all case JSON files from *dataset_dir*."""
        dpath = Path(dataset_dir)
        if not dpath.exists():
            raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")
        case_files = sorted(dpath.glob("case_*.json"))
        return [BenchmarkCase.from_json(str(f)) for f in case_files]

    async def run(
        self,
        dataset_dir: str,
        *,
        workers: int = 4,
    ) -> BenchmarkReport:
        """Run the full benchmark and return a report."""
        cases = self.load_cases(dataset_dir)
        dataset_name = Path(dataset_dir).name

        results: list[BenchmarkResult] = []
        for case in cases:
            result = await self._run_single(case)
            results.append(result)

        metrics = BenchmarkMetrics.from_results(results)
        report = BenchmarkReport(
            dataset=dataset_name,
            metrics=metrics,
            results=results,
        )

        self._save_report(report)
        return report

    async def run_streaming(
        self,
        dataset_dir: str,
        *,
        workers: int = 4,
    ) -> AsyncGenerator[dict, None]:
        """Run benchmark yielding progress events for SSE streaming."""
        cases = self.load_cases(dataset_dir)
        dataset_name = Path(dataset_dir).name
        total = len(cases)

        yield {"event": "started", "total": total, "dataset": dataset_name}

        results: list[BenchmarkResult] = []
        for i, case in enumerate(cases):
            yield {"event": "progress", "current": i + 1, "total": total, "case_id": case.case_id}
            result = await self._run_single(case)
            results.append(result)
            yield {
                "event": "case_complete",
                "case_id": case.case_id,
                "compiled": result.compiled,
                "param_accuracy": result.param_accuracy,
            }

        metrics = BenchmarkMetrics.from_results(results)
        report = BenchmarkReport(dataset=dataset_name, metrics=metrics, results=results)
        self._save_report(report)

        yield {
            "event": "complete",
            "run_id": report.run_id,
            "metrics": metrics.model_dump(),
        }

    async def _run_single(self, case: BenchmarkCase) -> BenchmarkResult:
        """Run the pipeline on a single case.

        Currently returns a placeholder result.
        Full pipeline integration will be added in Phase 2.
        """
        start = time.monotonic()

        # TODO: integrate actual V2 pipeline call
        # For now, return a placeholder that acknowledges the case exists
        duration = time.monotonic() - start

        return BenchmarkResult(
            case_id=case.case_id,
            compiled=False,
            type_correct=False,
            param_accuracy=0.0,
            bbox_match=False,
            duration_s=duration,
            tokens_used=0,
            failure_category=FailureCategory.CODE_EXECUTION,
            error_detail="Pipeline integration pending",
        )

    def _save_report(self, report: BenchmarkReport) -> None:
        """Persist report to disk as JSON + Markdown."""
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        base = self._reports_dir / report.run_id

        self._reporter.to_json(
            report.metrics, report.results, str(base.with_suffix(".json")),
            dataset=report.dataset,
        )

        md = self._reporter.to_markdown(report.metrics, report.results, dataset=report.dataset)
        base.with_suffix(".md").write_text(md)

    def list_reports(self) -> list[dict]:
        """List all saved reports (for history endpoint)."""
        if not self._reports_dir.exists():
            return []
        reports = []
        for f in sorted(self._reports_dir.glob("*.json"), reverse=True):
            with open(f) as fh:
                data = json.load(fh)
            reports.append({
                "run_id": f.stem,
                "dataset": data.get("dataset", ""),
                "timestamp": data.get("timestamp", ""),
                "total_cases": data.get("total_cases", 0),
                "metrics": data.get("metrics", {}),
            })
        return reports

    def get_report(self, run_id: str) -> dict | None:
        """Load a specific report by run_id."""
        path = self._reports_dir / f"{run_id}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Run benchmark evaluation")
    parser.add_argument("--dataset", required=True, help="Path to dataset directory")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    async def _main() -> None:
        runner = BenchmarkRunner()
        report = await runner.run(args.dataset, workers=args.workers)
        print(f"Benchmark complete: {report.run_id}")
        print(f"  Compile rate: {report.metrics.compile_rate:.1%}")
        print(f"  Type accuracy: {report.metrics.type_accuracy:.1%}")
        print(f"  Param accuracy (P50): {report.metrics.param_accuracy_p50:.1%}")
        print(f"  BBox match rate: {report.metrics.bbox_match_rate:.1%}")

    asyncio.run(_main())
