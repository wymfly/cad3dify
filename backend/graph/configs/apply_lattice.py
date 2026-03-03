"""Configuration for apply_lattice node."""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator

from backend.graph.configs.base import BaseNodeConfig


class ApplyLatticeConfig(BaseNodeConfig):
    """apply_lattice node configuration."""

    strategy: str = "tpms"

    lattice_type: Literal["gyroid", "schwarz_p", "diamond"] = "gyroid"
    cell_size: float = 8.0  # mm
    wall_thickness: float = 0.8  # mm
    shell_thickness: float = 2.0  # mm

    resolution: int = 64  # Grid resolution per axis

    @field_validator("cell_size")
    @classmethod
    def _validate_cell_size(cls, v: float) -> float:
        if v <= 0 or v > 50:
            raise ValueError(f"cell_size must be in (0, 50], got {v}")
        return v

    @field_validator("wall_thickness")
    @classmethod
    def _validate_wall_thickness(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"wall_thickness must be > 0, got {v}")
        return v

    @field_validator("shell_thickness")
    @classmethod
    def _validate_shell_thickness(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"shell_thickness must be >= 0, got {v}")
        return v

    @field_validator("resolution")
    @classmethod
    def _validate_resolution(cls, v: int) -> int:
        if v < 8:
            raise ValueError(f"resolution must be >= 8, got {v}")
        return v
