"""Vertex-level DfAM analysis — wall thickness + overhang angle."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VertexAnalysisResult:
    """Per-vertex analysis results."""

    wall_thickness: np.ndarray  # float64, mm, shape=(n_vertices,)
    overhang_angle: np.ndarray  # float64, degrees, shape=(n_vertices,)
    risk_wall: np.ndarray  # float64, [0,1], 0=danger 1=safe
    risk_overhang: np.ndarray  # float64, [0,1], 0=danger 1=safe
    stats: dict[str, Any] = field(default_factory=dict)


class VertexAnalyzer:
    """Analyze mesh vertices for DfAM metrics.

    Parameters:
        build_direction: Build direction vector, default +Z.
        build_plate_tolerance: Z threshold below which bottom faces
            are considered resting on the build plate (mm).
    """

    SENTINEL_THICKNESS = 999.0  # mm — no opposing surface found

    def __init__(
        self,
        build_direction: tuple[float, float, float] = (0, 0, 1),
        build_plate_tolerance: float = 0.5,
    ) -> None:
        self.build_direction = np.array(build_direction, dtype=np.float64)
        self.build_plate_tolerance = build_plate_tolerance

    def analyze(
        self,
        mesh_path: str,
        min_wall_threshold: float = 1.0,
        max_overhang_threshold: float = 45.0,
        safe_multiple: float = 3.0,
        max_vertices: int = 50_000,
    ) -> VertexAnalysisResult:
        """Run vertex-level wall thickness + overhang analysis.

        Implemented in Task 1.
        """
        raise NotImplementedError("Implemented in Task 1")
