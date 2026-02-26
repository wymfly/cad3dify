"""Tests for ParametricTemplate data model + YAML loader (Phase 3 Task 3.2).

Validates:
- ParamDefinition creation and validate_value (pass / fail / edge)
- ParamDefinition with depends_on
- ParamDefinition for non-numeric types (bool / str)
- ParametricTemplate creation
- validate_params — valid, out of range, missing (uses defaults)
- get_defaults
- from_yaml_string / to_yaml_string
- YAML round-trip (load → save → load produces same result)
- load_template from file (tmp_path)
- load_all_templates from directory (tmp_path)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.models.template import (
    ParamDefinition,
    ParametricTemplate,
    load_all_templates,
    load_template,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_YAML = """\
name: flange_basic
display_name: 基础法兰盘
part_type: ROTATIONAL_STEPPED
description: 带螺栓孔的基础法兰盘
params:
  - name: outer_diameter
    display_name: 外径
    unit: mm
    param_type: float
    range_min: 20
    range_max: 500
    default: 100
  - name: bore_diameter
    display_name: 内孔直径
    unit: mm
    param_type: float
    range_min: 5
    range_max: 200
    default: 30
  - name: thickness
    display_name: 厚度
    unit: mm
    param_type: float
    range_min: 5
    range_max: 100
    default: 15
  - name: bolt_count
    display_name: 螺栓数量
    param_type: int
    range_min: 3
    range_max: 24
    default: 6
  - name: bolt_diameter
    display_name: 螺栓孔直径
    unit: mm
    param_type: float
    range_min: 3
    range_max: 30
    default: 10
    depends_on: bolt_count
constraints:
  - "bore_diameter < outer_diameter"
  - "bolt_diameter < (outer_diameter - bore_diameter) / 2"
code_template: |
  import cadquery as cq
  result = (
      cq.Workplane("XY")
      .circle({{ outer_diameter }} / 2)
      .circle({{ bore_diameter }} / 2)
      .extrude({{ thickness }})
  )
"""


def _make_param(**overrides: object) -> ParamDefinition:
    """Helper to build a ParamDefinition with sensible defaults."""
    defaults = {
        "name": "outer_diameter",
        "display_name": "外径",
        "unit": "mm",
        "param_type": "float",
        "range_min": 20.0,
        "range_max": 500.0,
        "default": 100.0,
    }
    defaults.update(overrides)
    return ParamDefinition(**defaults)  # type: ignore[arg-type]


def _make_template(**overrides: object) -> ParametricTemplate:
    """Helper to build a ParametricTemplate with sensible defaults."""
    defaults: dict[str, object] = {
        "name": "flange_basic",
        "display_name": "基础法兰盘",
        "part_type": "ROTATIONAL_STEPPED",
        "description": "带螺栓孔的基础法兰盘",
        "params": [
            ParamDefinition(
                name="outer_diameter",
                display_name="外径",
                unit="mm",
                range_min=20,
                range_max=500,
                default=100,
            ),
            ParamDefinition(
                name="bore_diameter",
                display_name="内孔直径",
                unit="mm",
                range_min=5,
                range_max=200,
                default=30,
            ),
        ],
        "constraints": ["bore_diameter < outer_diameter"],
        "code_template": "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)\n",
    }
    defaults.update(overrides)
    return ParametricTemplate(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. ParamDefinition creation and validate_value
# ---------------------------------------------------------------------------


class TestParamDefinitionCreation:
    def test_basic_creation(self) -> None:
        p = _make_param()
        assert p.name == "outer_diameter"
        assert p.display_name == "外径"
        assert p.unit == "mm"
        assert p.param_type == "float"
        assert p.range_min == 20.0
        assert p.range_max == 500.0
        assert p.default == 100.0
        assert p.depends_on is None

    def test_validate_value_in_range(self) -> None:
        p = _make_param(range_min=10, range_max=100)
        assert p.validate_value(50) is True

    def test_validate_value_at_lower_bound(self) -> None:
        p = _make_param(range_min=10, range_max=100)
        assert p.validate_value(10) is True

    def test_validate_value_at_upper_bound(self) -> None:
        p = _make_param(range_min=10, range_max=100)
        assert p.validate_value(100) is True

    def test_validate_value_below_range(self) -> None:
        p = _make_param(range_min=10, range_max=100)
        assert p.validate_value(5) is False

    def test_validate_value_above_range(self) -> None:
        p = _make_param(range_min=10, range_max=100)
        assert p.validate_value(200) is False

    def test_validate_value_no_range(self) -> None:
        p = _make_param(range_min=None, range_max=None)
        assert p.validate_value(999999) is True

    def test_validate_value_only_min(self) -> None:
        p = _make_param(range_min=10, range_max=None)
        assert p.validate_value(5) is False
        assert p.validate_value(10) is True
        assert p.validate_value(999999) is True

    def test_validate_value_only_max(self) -> None:
        p = _make_param(range_min=None, range_max=100)
        assert p.validate_value(-999) is True
        assert p.validate_value(100) is True
        assert p.validate_value(101) is False


# ---------------------------------------------------------------------------
# 2. ParamDefinition with depends_on
# ---------------------------------------------------------------------------


class TestParamDefinitionDependsOn:
    def test_depends_on_set(self) -> None:
        p = _make_param(name="bolt_diameter", depends_on="bolt_count")
        assert p.depends_on == "bolt_count"

    def test_depends_on_default_none(self) -> None:
        p = _make_param()
        assert p.depends_on is None


# ---------------------------------------------------------------------------
# 3. ParamDefinition for non-numeric types
# ---------------------------------------------------------------------------


class TestParamDefinitionNonNumeric:
    def test_bool_param_always_valid(self) -> None:
        p = _make_param(param_type="bool", range_min=None, range_max=None, default=True)
        assert p.validate_value(True) is True
        assert p.validate_value(False) is True

    def test_str_param_always_valid(self) -> None:
        p = _make_param(param_type="str", range_min=None, range_max=None, default="hex")
        assert p.validate_value("hex") is True
        assert p.validate_value("") is True

    def test_int_param_respects_range(self) -> None:
        p = _make_param(param_type="int", range_min=3, range_max=24, default=6)
        assert p.validate_value(6) is True
        assert p.validate_value(2) is False
        assert p.validate_value(25) is False


# ---------------------------------------------------------------------------
# 4. ParametricTemplate creation
# ---------------------------------------------------------------------------


class TestParametricTemplateCreation:
    def test_basic_creation(self) -> None:
        t = _make_template()
        assert t.name == "flange_basic"
        assert t.display_name == "基础法兰盘"
        assert t.part_type == "ROTATIONAL_STEPPED"
        assert len(t.params) == 2
        assert len(t.constraints) == 1
        assert t.code_template != ""

    def test_empty_params_and_constraints(self) -> None:
        t = ParametricTemplate(
            name="empty",
            display_name="空模板",
            part_type="GENERAL",
        )
        assert t.params == []
        assert t.constraints == []
        assert t.code_template == ""
        assert t.description == ""


# ---------------------------------------------------------------------------
# 5. validate_params
# ---------------------------------------------------------------------------


class TestValidateParams:
    def test_valid_params(self) -> None:
        t = _make_template()
        errors = t.validate_params({"outer_diameter": 200, "bore_diameter": 50})
        assert errors == []

    def test_out_of_range_param(self) -> None:
        t = _make_template()
        errors = t.validate_params({"outer_diameter": 9999})
        assert len(errors) == 1
        assert "outer_diameter" in errors[0]
        assert "9999" in errors[0]

    def test_multiple_out_of_range(self) -> None:
        t = _make_template()
        errors = t.validate_params({"outer_diameter": 1, "bore_diameter": 999})
        assert len(errors) == 2

    def test_missing_params_use_defaults(self) -> None:
        t = _make_template()
        # No params provided → defaults are used → should pass
        errors = t.validate_params({})
        assert errors == []

    def test_missing_param_with_no_default_is_ignored(self) -> None:
        """A param with no default and not provided is simply skipped."""
        t = _make_template(
            params=[
                ParamDefinition(
                    name="angle",
                    display_name="角度",
                    unit="deg",
                    range_min=0,
                    range_max=360,
                    # no default
                ),
            ],
        )
        errors = t.validate_params({})
        assert errors == []

    def test_partial_override(self) -> None:
        t = _make_template()
        # Override only one param; the other uses its default
        errors = t.validate_params({"outer_diameter": 250})
        assert errors == []


# ---------------------------------------------------------------------------
# 6. get_defaults
# ---------------------------------------------------------------------------


class TestGetDefaults:
    def test_returns_defaults(self) -> None:
        t = _make_template()
        defaults = t.get_defaults()
        assert defaults == {"outer_diameter": 100, "bore_diameter": 30}

    def test_no_defaults(self) -> None:
        t = _make_template(
            params=[
                ParamDefinition(name="x", display_name="X"),
            ],
        )
        defaults = t.get_defaults()
        assert defaults == {}


# ---------------------------------------------------------------------------
# 7. from_yaml_string / to_yaml_string
# ---------------------------------------------------------------------------


class TestYamlSerialization:
    def test_from_yaml_string(self) -> None:
        t = ParametricTemplate.from_yaml_string(SAMPLE_YAML)
        assert t.name == "flange_basic"
        assert t.display_name == "基础法兰盘"
        assert t.part_type == "ROTATIONAL_STEPPED"
        assert len(t.params) == 5
        assert t.params[0].name == "outer_diameter"
        assert t.params[4].depends_on == "bolt_count"
        assert len(t.constraints) == 2
        assert "cadquery" in t.code_template

    def test_to_yaml_string(self) -> None:
        t = _make_template()
        yaml_str = t.to_yaml_string()
        # Parse back to verify it's valid YAML
        data = yaml.safe_load(yaml_str)
        assert data["name"] == "flange_basic"
        assert data["part_type"] == "ROTATIONAL_STEPPED"
        assert len(data["params"]) == 2

    def test_to_yaml_excludes_none(self) -> None:
        t = _make_template()
        yaml_str = t.to_yaml_string()
        # depends_on is None for both params → should not appear
        assert "depends_on" not in yaml_str


# ---------------------------------------------------------------------------
# 8. YAML round-trip
# ---------------------------------------------------------------------------


class TestYamlRoundTrip:
    def test_round_trip(self) -> None:
        """load → save → load produces semantically identical template."""
        original = ParametricTemplate.from_yaml_string(SAMPLE_YAML)
        yaml_str = original.to_yaml_string()
        restored = ParametricTemplate.from_yaml_string(yaml_str)

        assert original.name == restored.name
        assert original.display_name == restored.display_name
        assert original.part_type == restored.part_type
        assert original.description == restored.description
        assert len(original.params) == len(restored.params)
        for p_orig, p_rest in zip(original.params, restored.params):
            assert p_orig.name == p_rest.name
            assert p_orig.display_name == p_rest.display_name
            assert p_orig.unit == p_rest.unit
            assert p_orig.param_type == p_rest.param_type
            assert p_orig.range_min == p_rest.range_min
            assert p_orig.range_max == p_rest.range_max
            assert p_orig.default == p_rest.default
            assert p_orig.depends_on == p_rest.depends_on
        assert original.constraints == restored.constraints
        assert original.code_template == restored.code_template

    def test_round_trip_model_dump(self) -> None:
        """model_dump equality after round-trip."""
        original = ParametricTemplate.from_yaml_string(SAMPLE_YAML)
        yaml_str = original.to_yaml_string()
        restored = ParametricTemplate.from_yaml_string(yaml_str)
        assert original.model_dump() == restored.model_dump()


# ---------------------------------------------------------------------------
# 9. load_template from file
# ---------------------------------------------------------------------------


class TestLoadTemplate:
    def test_load_from_file(self, tmp_path: Path) -> None:
        p = tmp_path / "flange.yaml"
        p.write_text(SAMPLE_YAML, encoding="utf-8")

        t = load_template(p)
        assert t.name == "flange_basic"
        assert len(t.params) == 5

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_template(tmp_path / "does_not_exist.yaml")


# ---------------------------------------------------------------------------
# 10. load_all_templates from directory
# ---------------------------------------------------------------------------

GEAR_YAML = """\
name: spur_gear
display_name: 直齿轮
part_type: GEAR
description: 标准直齿轮
params:
  - name: module
    display_name: 模数
    param_type: float
    range_min: 0.5
    range_max: 10
    default: 2
  - name: teeth
    display_name: 齿数
    param_type: int
    range_min: 10
    range_max: 200
    default: 24
constraints:
  - "teeth >= 10"
code_template: |
  import cadquery as cq
  result = cq.Workplane("XY").circle({{ module }} * {{ teeth }} / 2).extrude(10)
"""


class TestLoadAllTemplates:
    def test_load_all(self, tmp_path: Path) -> None:
        (tmp_path / "01_flange.yaml").write_text(SAMPLE_YAML, encoding="utf-8")
        (tmp_path / "02_gear.yaml").write_text(GEAR_YAML, encoding="utf-8")

        templates = load_all_templates(tmp_path)
        assert len(templates) == 2
        # Sorted by filename → flange first, gear second
        assert templates[0].name == "flange_basic"
        assert templates[1].name == "spur_gear"

    def test_load_all_empty_directory(self, tmp_path: Path) -> None:
        templates = load_all_templates(tmp_path)
        assert templates == []

    def test_load_all_ignores_non_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "flange.yaml").write_text(SAMPLE_YAML, encoding="utf-8")
        (tmp_path / "readme.md").write_text("# Templates", encoding="utf-8")
        (tmp_path / "data.json").write_text("{}", encoding="utf-8")

        templates = load_all_templates(tmp_path)
        assert len(templates) == 1
        assert templates[0].name == "flange_basic"
