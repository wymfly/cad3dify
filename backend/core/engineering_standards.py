"""Engineering standards knowledge base.

Provides lookup, parameter recommendation, and constraint checking
for bolts, flanges, tolerances, keyways, and gears based on
national/international standards (GB/T, ISO, DIN).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class StandardEntry(BaseModel):
    """A single standard entry (e.g. one bolt size, one flange DN)."""

    category: str  # "bolt", "flange", "tolerance", "keyway", "gear"
    name: str  # "M10", "DN50", "H7/h6"
    params: dict[str, Any]  # standard parameters


class ParamRecommendation(BaseModel):
    """A parameter recommendation derived from standards."""

    param_name: str
    value: float
    unit: str = "mm"
    reason: str
    source: str = ""


class ConstraintViolation(BaseModel):
    """A constraint violation found during parameter checking."""

    constraint: str
    message: str
    severity: str = "error"  # "error" | "warning"


# ---------------------------------------------------------------------------
# YAML category → file mapping
# ---------------------------------------------------------------------------

_CATEGORY_FILES: dict[str, str] = {
    "bolt": "bolts.yaml",
    "flange": "flanges.yaml",
    "tolerance": "tolerances.yaml",
    "keyway": "keyways.yaml",
    "gear": "gears.yaml",
}

_DEFAULT_STANDARDS_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "standards"


# ---------------------------------------------------------------------------
# EngineeringStandards
# ---------------------------------------------------------------------------


class EngineeringStandards:
    """Engineering standards knowledge base.

    Loads standard data from YAML files and provides:
    - Category listing and entry lookup
    - Parameter recommendation based on known values
    - Constraint checking for engineering consistency
    """

    def __init__(self, standards_dir: Optional[Path] = None) -> None:
        self._dir = standards_dir or _DEFAULT_STANDARDS_DIR
        self._cache: dict[str, list[StandardEntry]] = {}
        self._load_all()

    # -- loading -------------------------------------------------------------

    def _load_all(self) -> None:
        """Load all YAML standard files into the cache."""
        for category, filename in _CATEGORY_FILES.items():
            filepath = self._dir / filename
            if filepath.exists():
                self._cache[category] = self._load_file(category, filepath)

    @staticmethod
    def _load_file(category: str, filepath: Path) -> list[StandardEntry]:
        """Parse a single YAML standards file into a list of entries."""
        raw = yaml.safe_load(filepath.read_text(encoding="utf-8"))
        entries: list[StandardEntry] = []
        for item in raw.get("standards", []):
            entries.append(
                StandardEntry(
                    category=category,
                    name=item["name"],
                    params=item["params"],
                )
            )
        return entries

    # -- queries -------------------------------------------------------------

    def list_categories(self) -> list[str]:
        """Return all loaded category names."""
        return sorted(self._cache.keys())

    def get_category(self, category: str) -> list[StandardEntry]:
        """Return all entries for *category*, or empty list if unknown."""
        return list(self._cache.get(category, []))

    def get_entry(self, category: str, name: str) -> Optional[StandardEntry]:
        """Look up a single entry by category + name."""
        for entry in self._cache.get(category, []):
            if entry.name == name:
                return entry
        return None

    # -- recommend_params ----------------------------------------------------

    def recommend_params(
        self,
        part_type: str,
        known_params: dict[str, float],
    ) -> list[ParamRecommendation]:
        """Recommend missing parameters based on standards.

        Dispatches to part-type-specific recommenders.
        """
        recommenders: dict[str, Any] = {
            "rotational": self._recommend_flange,
            "gear": self._recommend_gear,
            "rotational_stepped": self._recommend_keyway,
        }
        fn = recommenders.get(part_type)
        if fn is None:
            return []

        recs = fn(known_params)
        # Also try bolt recommendation for any part type with bolt_size
        recs.extend(self._recommend_bolt(known_params))
        return recs

    def _recommend_flange(
        self, known: dict[str, float]
    ) -> list[ParamRecommendation]:
        """Given outer_diameter, find the closest flange and recommend params."""
        od = known.get("outer_diameter")
        if od is None:
            return []

        best: Optional[StandardEntry] = None
        best_diff = float("inf")
        for entry in self._cache.get("flange", []):
            entry_od = entry.params.get("outer_diameter", 0)
            diff = abs(entry_od - od)
            if diff < best_diff:
                best_diff = diff
                best = entry

        if best is None:
            return []

        recs: list[ParamRecommendation] = []
        source = f"GB/T 9119 {best.name}"
        mapping = {
            "thickness": ("thickness", "标准法兰厚度"),
            "pcd": ("pcd", "标准螺栓分布圆直径"),
            "hole_count": ("hole_count", "标准螺栓孔数量"),
            "hole_diameter": ("hole_diameter", "标准螺栓孔直径"),
            "bore_diameter": ("bore_diameter", "标准通孔直径"),
        }
        for param_name, (key, reason) in mapping.items():
            if param_name not in known and key in best.params:
                recs.append(
                    ParamRecommendation(
                        param_name=param_name,
                        value=float(best.params[key]),
                        reason=f"{reason} ({best.name})",
                        source=source,
                    )
                )
        return recs

    def _recommend_bolt(
        self, known: dict[str, float]
    ) -> list[ParamRecommendation]:
        """Given bolt_size (as nominal diameter), recommend through_hole."""
        bolt_size = known.get("bolt_size")
        if bolt_size is None:
            return []

        # Find matching bolt by nominal diameter
        for entry in self._cache.get("bolt", []):
            nom = entry.params.get("nominal_diameter", 0)
            if abs(nom - bolt_size) < 0.1:
                recs: list[ParamRecommendation] = []
                source = f"GB/T 5277 {entry.name}"
                if "through_hole" not in known:
                    recs.append(
                        ParamRecommendation(
                            param_name="through_hole",
                            value=float(entry.params["through_hole"]),
                            reason=f"{entry.name} 标准通孔直径",
                            source=source,
                        )
                    )
                if "counterbore_dia" not in known:
                    recs.append(
                        ParamRecommendation(
                            param_name="counterbore_dia",
                            value=float(entry.params["counterbore_dia"]),
                            reason=f"{entry.name} 标准沉孔直径",
                            source=source,
                        )
                    )
                return recs
        return []

    def _recommend_gear(
        self, known: dict[str, float]
    ) -> list[ParamRecommendation]:
        """Given module, recommend gear tooth range and geometry."""
        module = known.get("module")
        if module is None:
            return []

        # Find closest standard module
        best: Optional[StandardEntry] = None
        best_diff = float("inf")
        for entry in self._cache.get("gear", []):
            m = entry.params.get("module", 0)
            diff = abs(m - module)
            if diff < best_diff:
                best_diff = diff
                best = entry

        if best is None:
            return []

        recs: list[ParamRecommendation] = []
        source = f"GB/T 1357 m{best.params['module']}"
        if "min_teeth" not in known:
            recs.append(
                ParamRecommendation(
                    param_name="min_teeth",
                    value=float(best.params["min_teeth"]),
                    reason=f"模数 {best.params['module']} 最小齿数",
                    source=source,
                )
            )
        if "pressure_angle" not in known:
            recs.append(
                ParamRecommendation(
                    param_name="pressure_angle",
                    value=float(best.params["pressure_angle"]),
                    unit="deg",
                    reason="标准压力角",
                    source=source,
                )
            )
        return recs

    def _recommend_keyway(
        self, known: dict[str, float]
    ) -> list[ParamRecommendation]:
        """Given shaft_diameter, recommend key width and depth."""
        shaft_d = known.get("shaft_diameter")
        if shaft_d is None:
            return []

        for entry in self._cache.get("keyway", []):
            d_min = entry.params.get("shaft_diameter_min", 0)
            d_max = entry.params.get("shaft_diameter_max", 0)
            if d_min <= shaft_d <= d_max:
                recs: list[ParamRecommendation] = []
                source = f"GB/T 1096 {entry.name}"
                if "key_width" not in known:
                    recs.append(
                        ParamRecommendation(
                            param_name="key_width",
                            value=float(entry.params["key_width"]),
                            reason=f"轴径 {shaft_d}mm 标准键宽",
                            source=source,
                        )
                    )
                if "shaft_groove_depth" not in known:
                    recs.append(
                        ParamRecommendation(
                            param_name="shaft_groove_depth",
                            value=float(entry.params["shaft_groove_depth"]),
                            reason=f"轴径 {shaft_d}mm 标准键槽深度",
                            source=source,
                        )
                    )
                return recs
        return []

    # -- check_constraints ---------------------------------------------------

    def check_constraints(
        self,
        part_type: str,
        params: dict[str, float],
    ) -> list[ConstraintViolation]:
        """Check engineering constraints for given parameters.

        Returns a list of violations (empty = all OK).
        """
        violations: list[ConstraintViolation] = []

        # Universal constraints
        violations.extend(self._check_basic_geometry(params))

        # Part-type-specific
        checkers: dict[str, Any] = {
            "rotational": self._check_flange_constraints,
            "gear": self._check_gear_constraints,
        }
        fn = checkers.get(part_type)
        if fn is not None:
            violations.extend(fn(params))

        return violations

    @staticmethod
    def _check_basic_geometry(
        params: dict[str, float],
    ) -> list[ConstraintViolation]:
        """Check universal geometry constraints."""
        violations: list[ConstraintViolation] = []

        od = params.get("outer_diameter")
        bore = params.get("bore_diameter")
        if od is not None and bore is not None and bore >= od:
            violations.append(
                ConstraintViolation(
                    constraint="bore_diameter < outer_diameter",
                    message=f"通孔直径 ({bore}) 必须小于外径 ({od})",
                )
            )

        wt = params.get("wall_thickness")
        if wt is not None and wt < 1.0:
            violations.append(
                ConstraintViolation(
                    constraint="wall_thickness >= 1.0",
                    message=f"壁厚 ({wt}) 不应小于 1.0mm",
                    severity="warning",
                )
            )

        return violations

    @staticmethod
    def _check_flange_constraints(
        params: dict[str, float],
    ) -> list[ConstraintViolation]:
        """Check flange-specific constraints."""
        violations: list[ConstraintViolation] = []

        od = params.get("outer_diameter")
        pcd = params.get("pcd")
        hole_diameter = params.get("hole_diameter")
        hole_count = params.get("hole_count")

        if od is not None and pcd is not None:
            if pcd >= od:
                violations.append(
                    ConstraintViolation(
                        constraint="pcd < outer_diameter",
                        message=f"螺栓分布圆直径 ({pcd}) 必须小于外径 ({od})",
                    )
                )

        if pcd is not None and hole_diameter is not None and hole_count is not None:
            if hole_count > 0:
                max_hole_dia = pcd * math.pi / hole_count
                if hole_diameter >= max_hole_dia:
                    violations.append(
                        ConstraintViolation(
                            constraint="hole_diameter < pcd * pi / hole_count",
                            message=(
                                f"螺栓孔直径 ({hole_diameter}) 过大，"
                                f"在 PCD={pcd} 上排列 {int(hole_count)} 个孔会重叠"
                            ),
                        )
                    )

        return violations

    @staticmethod
    def _check_gear_constraints(
        params: dict[str, float],
    ) -> list[ConstraintViolation]:
        """Check gear-specific constraints."""
        violations: list[ConstraintViolation] = []

        module = params.get("module")
        teeth = params.get("teeth")

        if module is not None and teeth is not None:
            if teeth < 12:
                violations.append(
                    ConstraintViolation(
                        constraint="teeth >= 12",
                        message=f"齿数 ({int(teeth)}) 不应少于 12（根切风险）",
                        severity="warning",
                    )
                )

        if module is not None and module <= 0:
            violations.append(
                ConstraintViolation(
                    constraint="module > 0",
                    message=f"模数 ({module}) 必须大于 0",
                )
            )

        return violations
