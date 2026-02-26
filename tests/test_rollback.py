"""Tests for refinement rollback mechanism."""

from __future__ import annotations

import pytest

from backend.core.rollback import RollbackTracker


# ---------------------------------------------------------------------------
# TestRollbackTracker
# ---------------------------------------------------------------------------


class TestRollbackTracker:
    def test_initial_state_empty(self) -> None:
        """Fresh tracker has no snapshot and zero rollback count."""
        tracker = RollbackTracker()
        assert tracker.current_code is None
        assert tracker.current_score == 0.0
        assert tracker.rollback_count == 0

    def test_save_snapshot(self) -> None:
        """save() stores code and score."""
        tracker = RollbackTracker()
        tracker.save("code_v1", 80.0)
        assert tracker.current_code == "code_v1"
        assert tracker.current_score == 80.0

    def test_no_rollback_on_improvement(self) -> None:
        """Score improves -> accept new code, no rollback."""
        tracker = RollbackTracker()
        tracker.save("code_v1", 80.0)
        should_rollback, _ = tracker.check_and_update("code_v2", 85.0)
        assert should_rollback is False
        assert tracker.current_code == "code_v2"
        assert tracker.current_score == 85.0

    def test_rollback_on_degradation(self) -> None:
        """80 -> 60 is 25% drop, exceeds 10% threshold -> rollback."""
        tracker = RollbackTracker(threshold=0.10)
        tracker.save("code_v1", 80.0)
        should_rollback, prev_code = tracker.check_and_update("code_v2", 60.0)
        assert should_rollback is True
        assert prev_code == "code_v1"
        assert tracker.rollback_count == 1
        assert tracker.current_code == "code_v1"  # reverted
        assert tracker.current_score == 80.0  # reverted

    def test_no_rollback_on_small_degradation(self) -> None:
        """80 -> 75 is 6.25% drop, below 10% threshold -> accept."""
        tracker = RollbackTracker(threshold=0.10)
        tracker.save("code_v1", 80.0)
        should_rollback, _ = tracker.check_and_update("code_v2", 75.0)
        assert should_rollback is False
        assert tracker.current_code == "code_v2"

    def test_zero_score_baseline_no_division_error(self) -> None:
        """Baseline score = 0 -> accept any new code (no meaningful baseline)."""
        tracker = RollbackTracker()
        tracker.save("code_v1", 0.0)
        should_rollback, _ = tracker.check_and_update("code_v2", 50.0)
        assert should_rollback is False

    def test_negative_score_baseline_accepts(self) -> None:
        """Baseline score < 0 -> accept new code (no meaningful baseline)."""
        tracker = RollbackTracker()
        tracker.save("code_v1", -5.0)
        should_rollback, _ = tracker.check_and_update("code_v2", 10.0)
        assert should_rollback is False

    def test_exact_threshold_boundary(self) -> None:
        """Degradation exactly at threshold -> no rollback (strict >)."""
        tracker = RollbackTracker(threshold=0.10)
        tracker.save("code_v1", 100.0)
        # 100 -> 90 is exactly 10% drop = threshold, should NOT rollback
        should_rollback, _ = tracker.check_and_update("code_v2", 90.0)
        assert should_rollback is False
        assert tracker.current_code == "code_v2"

    def test_multiple_rollbacks_accumulate(self) -> None:
        """rollback_count increments on each rollback."""
        tracker = RollbackTracker(threshold=0.10)
        tracker.save("code_v1", 80.0)

        # First rollback
        tracker.check_and_update("bad_v2", 50.0)
        assert tracker.rollback_count == 1

        # Second rollback (state still at code_v1/80.0)
        tracker.check_and_update("bad_v3", 40.0)
        assert tracker.rollback_count == 2
        assert tracker.current_code == "code_v1"

    def test_rollback_then_improvement(self) -> None:
        """After rollback, a good update succeeds."""
        tracker = RollbackTracker(threshold=0.10)
        tracker.save("code_v1", 80.0)

        # Rollback
        should_rollback, _ = tracker.check_and_update("bad_v2", 50.0)
        assert should_rollback is True
        assert tracker.current_code == "code_v1"

        # Now improve
        should_rollback, _ = tracker.check_and_update("good_v3", 90.0)
        assert should_rollback is False
        assert tracker.current_code == "good_v3"
        assert tracker.current_score == 90.0

    def test_check_and_update_returns_none_when_accepted(self) -> None:
        """When code is accepted, prev_code in return tuple is None."""
        tracker = RollbackTracker()
        tracker.save("code_v1", 80.0)
        should_rollback, prev_code = tracker.check_and_update("code_v2", 85.0)
        assert should_rollback is False
        assert prev_code is None

    def test_custom_threshold(self) -> None:
        """Custom threshold = 0.05 triggers on smaller drops."""
        tracker = RollbackTracker(threshold=0.05)
        tracker.save("code_v1", 100.0)
        # 100 -> 93 is 7% drop, exceeds 5%
        should_rollback, _ = tracker.check_and_update("code_v2", 93.0)
        assert should_rollback is True
        assert tracker.rollback_count == 1

    def test_no_snapshot_accepts_any(self) -> None:
        """No prior save -> check_and_update accepts and stores."""
        tracker = RollbackTracker()
        should_rollback, prev_code = tracker.check_and_update("code_v1", 75.0)
        assert should_rollback is False
        assert prev_code is None
        assert tracker.current_code == "code_v1"
        assert tracker.current_score == 75.0
