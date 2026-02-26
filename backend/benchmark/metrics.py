"""Benchmark metrics and failure classification.

Defines the 5-metric evaluation framework and failure taxonomy
for classifying why a pipeline run failed.
"""

from __future__ import annotations

import statistics
from enum import Enum
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Failure categories
# ---------------------------------------------------------------------------


class FailureCategory(str, Enum):
    """Root-cause taxonomy for pipeline failures."""

    CODE_EXECUTION = "CODE_EXECUTION"
    TYPE_RECOGNITION = "TYPE_RECOGNITION"
    ANNOTATION_MISS = "ANNOTATION_MISS"
    STRUCTURAL_ERROR = "STRUCTURAL_ERROR"
    DIMENSION_DEVIATION = "DIMENSION_DEVIATION"


# Priority order for classification (first match wins).
_PRIORITY: list[tuple[str, FailureCategory]] = [
    ("compile_error", FailureCategory.CODE_EXECUTION),
    ("type_mismatch", FailureCategory.TYPE_RECOGNITION),
    ("annotation_miss", FailureCategory.ANNOTATION_MISS),
    ("structural_error", FailureCategory.STRUCTURAL_ERROR),
    ("param_error", FailureCategory.DIMENSION_DEVIATION),
]


def classify_failure(
    *,
    compile_error: str | None = None,
    type_mismatch: bool = False,
    annotation_miss: bool = False,
    structural_error: str | None = None,
    param_error: str | None = None,
) -> FailureCategory | None:
    """Classify a failure into one of the 5 categories.

    Returns ``None`` if no failure indicators are present.
    When multiple indicators are set, the highest-priority category wins.
    """
    indicators: dict[str, bool] = {
        "compile_error": bool(compile_error),
        "type_mismatch": type_mismatch,
        "annotation_miss": annotation_miss,
        "structural_error": bool(structural_error),
        "param_error": bool(param_error),
    }
    for key, category in _PRIORITY:
        if indicators.get(key, False):
            return category
    return None


# ---------------------------------------------------------------------------
# Per-case result
# ---------------------------------------------------------------------------


class BenchmarkResult(BaseModel):
    """Result of a single benchmark case."""

    case_id: str
    compiled: bool = False
    type_correct: bool = False
    param_accuracy: float = 0.0
    bbox_match: bool = False
    duration_s: float = 0.0
    tokens_used: int = 0
    failure_category: Optional[FailureCategory] = None
    error_detail: str = ""


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------


class BenchmarkMetrics(BaseModel):
    """Aggregate metrics across all benchmark cases."""

    compile_rate: float = 0.0
    type_accuracy: float = 0.0
    param_accuracy_p50: float = 0.0
    bbox_match_rate: float = 0.0
    avg_duration_s: float = 0.0
    avg_tokens: int = 0

    @classmethod
    def from_results(cls, results: list[BenchmarkResult]) -> BenchmarkMetrics:
        """Compute aggregate metrics from a list of case results."""
        n = len(results)
        if n == 0:
            return cls()

        compile_rate = sum(1 for r in results if r.compiled) / n
        type_accuracy = sum(1 for r in results if r.type_correct) / n
        bbox_match_rate = sum(1 for r in results if r.bbox_match) / n

        param_values = sorted(r.param_accuracy for r in results)
        param_accuracy_p50 = statistics.median(param_values)

        avg_duration_s = statistics.mean(r.duration_s for r in results)
        avg_tokens = round(statistics.mean(r.tokens_used for r in results))

        return cls(
            compile_rate=compile_rate,
            type_accuracy=type_accuracy,
            param_accuracy_p50=param_accuracy_p50,
            bbox_match_rate=bbox_match_rate,
            avg_duration_s=avg_duration_s,
            avg_tokens=avg_tokens,
        )
