"""Token usage tracker — records per-stage LLM input/output tokens and timing."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class StageStats:
    """Usage statistics for a single pipeline stage."""

    name: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_s: float = 0.0


class TokenTracker:
    """Accumulates token usage across pipeline stages."""

    def __init__(self) -> None:
        self._stages: list[StageStats] = []
        self._start_time: float = time.time()

    def record(
        self,
        stage_name: str,
        *,
        input_tokens: int,
        output_tokens: int,
        duration_s: float,
    ) -> None:
        """Record usage for one stage."""
        self._stages.append(
            StageStats(
                name=stage_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_s=duration_s,
            )
        )

    def get_stats(self) -> dict[str, Any]:
        """Return aggregated statistics."""
        return {
            "total_input_tokens": sum(s.input_tokens for s in self._stages),
            "total_output_tokens": sum(s.output_tokens for s in self._stages),
            "total_duration_s": sum(s.duration_s for s in self._stages),
            "wall_time_s": time.time() - self._start_time,
            "stages": [
                {
                    "name": s.name,
                    "input_tokens": s.input_tokens,
                    "output_tokens": s.output_tokens,
                    "duration_s": s.duration_s,
                }
                for s in self._stages
            ],
        }

    def export_json(self, path: str) -> None:
        """Write stats to a JSON file."""
        with open(path, "w") as f:
            json.dump(self.get_stats(), f, indent=2)
