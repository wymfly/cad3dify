"""Benchmark report generation — Markdown and JSON formats."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .metrics import BenchmarkMetrics, BenchmarkResult, FailureCategory


class BenchmarkReporter:
    """Generate benchmark reports in Markdown and JSON."""

    def to_markdown(
        self,
        metrics: BenchmarkMetrics,
        results: list[BenchmarkResult],
        *,
        dataset: str = "unknown",
    ) -> str:
        """Generate a Markdown report string."""
        lines: list[str] = []
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"# 评测报告 — {dataset}")
        lines.append(f"\n生成时间: {ts}")
        lines.append(f"数据集: {dataset} ({len(results)} cases)")

        # Metrics summary
        lines.append("\n## 指标摘要\n")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 编译通过率 | {metrics.compile_rate:.1%} |")
        lines.append(f"| 类型准确率 | {metrics.type_accuracy:.1%} |")
        lines.append(f"| 参数准确率 (P50) | {metrics.param_accuracy_p50:.1%} |")
        lines.append(f"| 包围盒匹配率 | {metrics.bbox_match_rate:.1%} |")
        lines.append(f"| 平均耗时 | {metrics.avg_duration_s:.1f}s |")
        lines.append(f"| 平均 Token | {metrics.avg_tokens} |")

        # Failure breakdown
        failure_counts = self._count_failures(results)
        if failure_counts:
            lines.append("\n## 失败分类\n")
            lines.append("| 类别 | 次数 | 占比 |")
            lines.append("|------|------|------|")
            total_failures = sum(failure_counts.values())
            for category, count in failure_counts.most_common():
                pct = count / total_failures if total_failures else 0
                lines.append(f"| {category} | {count} | {pct:.0%} |")

        # Per-case results
        lines.append("\n## 逐 Case 结果\n")
        lines.append("| Case | 编译 | 类型 | 参数准确率 | 包围盒 | 耗时 | 失败类别 |")
        lines.append("|------|------|------|-----------|--------|------|---------|")
        for r in results:
            compiled = "✓" if r.compiled else "✗"
            type_ok = "✓" if r.type_correct else "✗"
            bbox_ok = "✓" if r.bbox_match else "✗"
            fail = r.failure_category.value if r.failure_category else "—"
            lines.append(
                f"| {r.case_id} | {compiled} | {type_ok} | {r.param_accuracy:.0%} "
                f"| {bbox_ok} | {r.duration_s:.1f}s | {fail} |"
            )

        return "\n".join(lines)

    def to_json(
        self,
        metrics: BenchmarkMetrics,
        results: list[BenchmarkResult],
        path: str,
        *,
        dataset: str = "unknown",
    ) -> None:
        """Export report as JSON to *path*."""
        failure_counts = self._count_failures(results)
        report: dict[str, Any] = {
            "dataset": dataset,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_cases": len(results),
            "metrics": metrics.model_dump(),
            "failure_breakdown": {
                cat: count for cat, count in failure_counts.most_common()
            },
            "results": [r.model_dump() for r in results],
        }
        with open(path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _count_failures(results: list[BenchmarkResult]) -> Counter[str]:
        """Count failures by category, sorted by frequency."""
        counts: Counter[str] = Counter()
        for r in results:
            if r.failure_category is not None:
                counts[r.failure_category.value] += 1
        return counts
