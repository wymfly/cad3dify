"""Printability data models — print profiles, issues, and check results.

Defines the schema for 3D printing feasibility checks:
- PrintProfile: printer technology constraints (wall thickness, overhang, etc.)
- PrintIssue: a single printability problem found during checking
- PrintabilityResult: aggregated check outcome
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# PrintProfile
# ---------------------------------------------------------------------------


class PrintProfile(BaseModel):
    """Printer technology profile with manufacturing constraints.

    Attributes:
        name: Machine-readable identifier (e.g. ``"fdm_standard"``).
        technology: Printing technology — ``"FDM"``, ``"SLA"``, or ``"SLS"``.
        min_wall_thickness: Minimum printable wall thickness in mm.
        max_overhang_angle: Maximum unsupported overhang angle in degrees.
        min_hole_diameter: Minimum printable hole diameter in mm.
        min_rib_thickness: Minimum printable rib/fin thickness in mm.
        build_volume: Printer build volume as ``(x, y, z)`` in mm.
    """

    name: str
    technology: str
    min_wall_thickness: float
    max_overhang_angle: float
    min_hole_diameter: float
    min_rib_thickness: float
    build_volume: tuple[float, float, float]


# ---------------------------------------------------------------------------
# PrintIssue
# ---------------------------------------------------------------------------


class PrintIssue(BaseModel):
    """A single printability problem detected during checking.

    Attributes:
        check: Check category — one of ``"wall_thickness"``,
            ``"overhang"``, ``"hole_diameter"``, ``"rib_thickness"``,
            ``"build_volume"``.
        severity: ``"error"`` (cannot print), ``"warning"`` (risky),
            or ``"info"`` (informational).
        message: Human-readable description of the issue.
        value: Actual measured value (if applicable).
        threshold: Profile threshold that was violated (if applicable).
        suggestion: Recommended remediation action.
    """

    check: str
    severity: str
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    suggestion: str = ""


# ---------------------------------------------------------------------------
# PrintabilityResult
# ---------------------------------------------------------------------------


class PrintabilityResult(BaseModel):
    """Aggregated printability check result.

    Attributes:
        printable: ``True`` if no *error*-severity issues were found.
        profile: Name of the print profile used for checking.
        issues: List of detected printability issues.
        material_volume_cm3: Part volume in cm³ (from geometry info).
        bounding_box: Part bounding box dimensions in mm.
    """

    printable: bool
    profile: str
    issues: list[PrintIssue]
    material_volume_cm3: Optional[float] = None
    bounding_box: Optional[dict[str, float]] = None
