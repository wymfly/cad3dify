"""Rollback mechanism for SmartRefiner -- prevents quality degradation.

Tracks code snapshots and geometry scores across refinement rounds.
If a refinement degrades the score by more than the threshold,
automatically rolls back to the previous version.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger


@dataclass
class RollbackTracker:
    """Track refinement quality and rollback on degradation.

    Parameters
    ----------
    threshold:
        Maximum allowed fractional degradation (0.10 = 10%).
        Degradation *strictly greater than* this value triggers a rollback.
    """

    threshold: float = 0.10  # 10% degradation triggers rollback
    current_code: str | None = None
    current_score: float = 0.0
    rollback_count: int = 0

    def save(self, code: str, score: float) -> None:
        """Save a code snapshot with its quality score."""
        self.current_code = code
        self.current_score = score
        logger.debug(
            f"RollbackTracker: saved snapshot (score={score:.1f})"
        )

    def check_and_update(
        self, new_code: str, new_score: float
    ) -> tuple[bool, str | None]:
        """Check if new code degrades quality beyond threshold.

        Returns ``(should_rollback, previous_code)``.

        * If ``should_rollback`` is ``True``, the tracker reverts to the
          previous state and ``previous_code`` contains the old code.
        * If ``should_rollback`` is ``False``, the tracker accepts the new
          code and ``previous_code`` is ``None``.

        Rules
        -----
        1. If ``current_score <= 0`` (no meaningful baseline) -> accept.
        2. Degradation = ``(current_score - new_score) / current_score``.
        3. If degradation > threshold -> rollback (increment
           ``rollback_count``, keep old state).
        4. Otherwise -> accept (update ``current_code`` and
           ``current_score``).
        """
        # No meaningful baseline -- accept unconditionally.
        if self.current_score <= 0:
            logger.info(
                f"RollbackTracker: no meaningful baseline "
                f"(score={self.current_score:.1f}), accepting new code "
                f"(new_score={new_score:.1f})"
            )
            self.current_code = new_code
            self.current_score = new_score
            return False, None

        degradation = (self.current_score - new_score) / self.current_score

        if degradation > self.threshold:
            # Quality dropped too much -- rollback.
            self.rollback_count += 1
            logger.warning(
                f"RollbackTracker: ROLLBACK #{self.rollback_count} -- "
                f"score {self.current_score:.1f} -> {new_score:.1f} "
                f"(degradation={degradation:.1%} > threshold={self.threshold:.1%})"
            )
            return True, self.current_code

        # Acceptable change -- update.
        logger.info(
            f"RollbackTracker: accepted -- "
            f"score {self.current_score:.1f} -> {new_score:.1f} "
            f"(degradation={degradation:.1%})"
        )
        self.current_code = new_code
        self.current_score = new_score
        return False, None
