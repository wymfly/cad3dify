"""ParametricTemplate data model — Pydantic + YAML storage.

Defines the schema for parametric CadQuery code templates that can be
stored as YAML files and loaded at runtime.  Each template contains:

- metadata (name, part_type, description)
- typed parameter definitions with validation rules
- constraint expressions
- a CadQuery code template with Jinja-style placeholders
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# ParamDefinition
# ---------------------------------------------------------------------------


class ParamDefinition(BaseModel):
    """Single parameter definition for a parametric template.

    Attributes:
        name: Machine-readable identifier (e.g. ``"outer_diameter"``).
        display_name: Human-readable label (e.g. ``"外径"``).
        unit: Physical unit string (``"mm"``, ``"deg"``, …).
        param_type: One of ``float``, ``int``, ``bool``, ``str``.
        range_min: Minimum allowed value (inclusive).  ``None`` = no lower bound.
        range_max: Maximum allowed value (inclusive).  ``None`` = no upper bound.
        default: Default value used when the caller omits this parameter.
        depends_on: Name of another parameter this one logically depends on.
    """

    name: str
    display_name: str
    unit: str = ""
    param_type: str = "float"  # float | int | bool | str
    range_min: Optional[float] = None
    range_max: Optional[float] = None
    default: Optional[Any] = None
    depends_on: Optional[str] = None

    def validate_value(self, value: Any) -> bool:
        """Return *True* if *value* satisfies range constraints.

        Non-numeric types (bool / str) always pass the range check.
        """
        if self.param_type in ("bool", "str"):
            return True
        if self.range_min is not None and value < self.range_min:
            return False
        if self.range_max is not None and value > self.range_max:
            return False
        return True


# ---------------------------------------------------------------------------
# ParametricTemplate
# ---------------------------------------------------------------------------


class ParametricTemplate(BaseModel):
    """Parametric CadQuery code template stored as YAML.

    Attributes:
        name: Unique machine-readable identifier (e.g. ``"flange_basic"``).
        display_name: Human-readable title (e.g. ``"基础法兰盘"``).
        part_type: Part category — must match ``PartType`` enum values.
        description: Free-text description of the template.
        params: Ordered list of parameter definitions.
        constraints: Human-readable constraint expressions
            (e.g. ``"bore_diameter < outer_diameter"``).
        code_template: CadQuery Python source with ``{{ param }}`` placeholders.
    """

    name: str
    display_name: str
    part_type: str
    description: str = ""
    params: list[ParamDefinition] = []
    constraints: list[str] = []
    code_template: str = ""

    # -- param helpers -------------------------------------------------------

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Validate *params* against all parameter definitions.

        Missing parameters are filled with their defaults before checking.
        Returns a list of human-readable error strings (empty = all OK).
        """
        errors: list[str] = []
        merged = self.get_defaults()
        merged.update(params)
        for p in self.params:
            val = merged.get(p.name)
            if val is not None and not p.validate_value(val):
                errors.append(
                    f"Parameter '{p.name}' value {val} out of range "
                    f"[{p.range_min}, {p.range_max}]"
                )
        return errors

    def get_defaults(self) -> dict[str, Any]:
        """Return a dict of ``{param_name: default}`` for all params with defaults."""
        return {p.name: p.default for p in self.params if p.default is not None}

    # -- YAML serialization --------------------------------------------------

    @classmethod
    def from_yaml_string(cls, yaml_str: str) -> ParametricTemplate:
        """Deserialize a template from a YAML string."""
        data = yaml.safe_load(yaml_str)
        return cls.model_validate(data)

    def to_yaml_string(self) -> str:
        """Serialize the template to a YAML string.

        ``None`` values are excluded to keep the output concise.
        """
        return yaml.dump(
            self.model_dump(exclude_none=True),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------


def load_template(path: Path) -> ParametricTemplate:
    """Load a single ``ParametricTemplate`` from a YAML file."""
    text = path.read_text(encoding="utf-8")
    return ParametricTemplate.from_yaml_string(text)


def load_all_templates(directory: Path) -> list[ParametricTemplate]:
    """Load all ``*.yaml`` templates from *directory*, sorted by filename."""
    templates: list[ParametricTemplate] = []
    for f in sorted(directory.glob("*.yaml")):
        templates.append(load_template(f))
    return templates
