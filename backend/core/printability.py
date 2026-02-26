"""Printability checker — validates geometry against print technology constraints.

Operates on pre-computed ``geometry_info`` dicts so the checker is decoupled
from the CAD kernel.  Three built-in preset profiles are provided for
FDM, SLA, and SLS technologies.
"""

from __future__ import annotations

from typing import Optional

from backend.models.printability import (
    PrintabilityResult,
    PrintIssue,
    PrintProfile,
)

# ---------------------------------------------------------------------------
# Preset profiles
# ---------------------------------------------------------------------------

PRESET_PROFILES: dict[str, PrintProfile] = {
    "fdm_standard": PrintProfile(
        name="fdm_standard",
        technology="FDM",
        min_wall_thickness=0.8,
        max_overhang_angle=45.0,
        min_hole_diameter=2.0,
        min_rib_thickness=0.8,
        build_volume=(220, 220, 250),
    ),
    "sla_standard": PrintProfile(
        name="sla_standard",
        technology="SLA",
        min_wall_thickness=0.3,
        max_overhang_angle=30.0,
        min_hole_diameter=0.5,
        min_rib_thickness=0.3,
        build_volume=(145, 145, 175),
    ),
    "sls_standard": PrintProfile(
        name="sls_standard",
        technology="SLS",
        min_wall_thickness=0.7,
        max_overhang_angle=90.0,  # SLS is self-supporting
        min_hole_diameter=1.5,
        min_rib_thickness=0.7,
        build_volume=(300, 300, 300),
    ),
}


# ---------------------------------------------------------------------------
# PrintabilityChecker
# ---------------------------------------------------------------------------


class PrintabilityChecker:
    """Check pre-computed geometry info against a print profile.

    The checker does **not** operate on CAD geometry directly.  Instead it
    receives a ``geometry_info`` dict with pre-extracted measurements:

    - ``bounding_box``: ``{"x": float, "y": float, "z": float}`` in mm
    - ``min_wall_thickness``: minimum wall thickness in mm
    - ``max_overhang_angle``: maximum overhang angle in degrees
    - ``min_hole_diameter``: minimum hole diameter in mm
    - ``min_rib_thickness``: minimum rib thickness in mm
    - ``volume_cm3``: part volume in cm³

    Missing fields are silently skipped (no issue generated).
    """

    def check(
        self,
        geometry_info: dict,
        profile: str | PrintProfile = "fdm_standard",
    ) -> PrintabilityResult:
        """Run all printability checks and return an aggregated result.

        Parameters:
            geometry_info: Pre-computed geometry measurements.
            profile: Profile name (string key into ``PRESET_PROFILES``) or
                a ``PrintProfile`` instance.

        Raises:
            ValueError: If *profile* is a string that does not match any
                preset profile name.
        """
        prof = self._resolve_profile(profile)

        issues: list[PrintIssue] = []

        for issue in (
            self._check_wall_thickness(
                geometry_info.get("min_wall_thickness"),
                prof.min_wall_thickness,
            ),
            self._check_overhang(
                geometry_info.get("max_overhang_angle"),
                prof.max_overhang_angle,
            ),
            self._check_hole_diameter(
                geometry_info.get("min_hole_diameter"),
                prof.min_hole_diameter,
            ),
            self._check_rib_thickness(
                geometry_info.get("min_rib_thickness"),
                prof.min_rib_thickness,
            ),
            self._check_build_volume(
                geometry_info.get("bounding_box"),
                prof.build_volume,
            ),
        ):
            if issue is not None:
                issues.append(issue)

        printable = all(i.severity != "error" for i in issues)

        bbox = geometry_info.get("bounding_box")
        volume = geometry_info.get("volume_cm3")

        return PrintabilityResult(
            printable=printable,
            profile=prof.name,
            issues=issues,
            material_volume_cm3=volume,
            bounding_box=bbox,
        )

    # -- individual checks ---------------------------------------------------

    @staticmethod
    def _check_wall_thickness(
        value: Optional[float],
        threshold: float,
    ) -> Optional[PrintIssue]:
        if value is None:
            return None
        if value < threshold:
            return PrintIssue(
                check="wall_thickness",
                severity="error",
                message=(
                    f"Wall thickness {value:.2f} mm is below "
                    f"minimum {threshold:.2f} mm"
                ),
                value=value,
                threshold=threshold,
                suggestion=(
                    "Increase wall thickness or switch to a higher-"
                    "resolution print technology (e.g. SLA)."
                ),
            )
        return None

    @staticmethod
    def _check_overhang(
        value: Optional[float],
        threshold: float,
    ) -> Optional[PrintIssue]:
        if value is None:
            return None
        if value > threshold:
            return PrintIssue(
                check="overhang",
                severity="warning",
                message=(
                    f"Overhang angle {value:.1f}\u00b0 exceeds "
                    f"maximum {threshold:.1f}\u00b0"
                ),
                value=value,
                threshold=threshold,
                suggestion=(
                    "Add support structures, reorient the part, or "
                    "consider SLS printing (no supports needed)."
                ),
            )
        return None

    @staticmethod
    def _check_hole_diameter(
        value: Optional[float],
        threshold: float,
    ) -> Optional[PrintIssue]:
        if value is None:
            return None
        if value < threshold:
            return PrintIssue(
                check="hole_diameter",
                severity="error",
                message=(
                    f"Hole diameter {value:.2f} mm is below "
                    f"minimum {threshold:.2f} mm"
                ),
                value=value,
                threshold=threshold,
                suggestion=(
                    "Enlarge the hole or drill it in post-processing."
                ),
            )
        return None

    @staticmethod
    def _check_rib_thickness(
        value: Optional[float],
        threshold: float,
    ) -> Optional[PrintIssue]:
        if value is None:
            return None
        if value < threshold:
            return PrintIssue(
                check="rib_thickness",
                severity="warning",
                message=(
                    f"Rib thickness {value:.2f} mm is below "
                    f"minimum {threshold:.2f} mm"
                ),
                value=value,
                threshold=threshold,
                suggestion=(
                    "Thicken ribs or remove thin features."
                ),
            )
        return None

    @staticmethod
    def _check_build_volume(
        bbox: Optional[dict[str, float]],
        build_volume: tuple[float, float, float],
    ) -> Optional[PrintIssue]:
        if bbox is None:
            return None
        bx, by, bz = build_volume
        exceeded: list[str] = []
        if bbox.get("x", 0) > bx:
            exceeded.append(f"X ({bbox['x']:.1f} > {bx:.1f})")
        if bbox.get("y", 0) > by:
            exceeded.append(f"Y ({bbox['y']:.1f} > {by:.1f})")
        if bbox.get("z", 0) > bz:
            exceeded.append(f"Z ({bbox['z']:.1f} > {bz:.1f})")
        if exceeded:
            return PrintIssue(
                check="build_volume",
                severity="error",
                message=(
                    f"Part exceeds build volume: {', '.join(exceeded)}"
                ),
                suggestion=(
                    "Scale down the part or use a larger printer."
                ),
            )
        return None

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _resolve_profile(profile: str | PrintProfile) -> PrintProfile:
        if isinstance(profile, PrintProfile):
            return profile
        if profile not in PRESET_PROFILES:
            available = ", ".join(sorted(PRESET_PROFILES))
            raise ValueError(
                f"Unknown profile '{profile}'. "
                f"Available presets: {available}"
            )
        return PRESET_PROFILES[profile]
