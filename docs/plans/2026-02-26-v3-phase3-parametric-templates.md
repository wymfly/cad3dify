# Phase 3: 参数化模板 + 知识库管理 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 参数化模板系统覆盖 7 种零件类型，模板精度 < 1%；知识库可视化管理；向量检索增强示例匹配。

**Architecture:** 新增 ParametricTemplate 数据模型（Pydantic + YAML），TemplateEngine 使用 Jinja2 渲染 CadQuery 代码。模板以 YAML 文件存储在 `backend/knowledge/templates/` 下，API 提供 CRUD 管理。Feature 模型从 `list[dict]` 升级为 Pydantic union type。知识库扩充到 ~40 个 TaggedExample。向量检索使用 sentence-transformers embedding + numpy cosine similarity（轻量替代 pgvector，保留 Jaccard fallback）。

**Tech Stack:** Python 3.10+, Pydantic v2, Jinja2, PyYAML, CadQuery 2.4, FastAPI, React 19 + Ant Design 6, sentence-transformers (optional)

**依赖图:**
```
T1 (Feature model) ────────────────────────────────┐
T2 (Template model) → T3 (Engine) → T4 (Templates) ├─ 最终集成
                       T3 (Engine) → T5 (API)       │
                                      T5 → T8 (前端) │
T6 (知识库扩充) ────────────────────────────────────┤
T7 (向量检索) ─────────────────────────────────────┘
```

**并行批次:**
- Batch 1: T1, T2, T6, T7（全部独立）
- Batch 2: T3（依赖 T2）
- Batch 3: T4, T5（依赖 T3）
- Batch 4: T8（依赖 T5）

---

## Task 1: Feature 结构化模型（对应 OpenSpec T3.1）

**Files:**
- Modify: `backend/knowledge/part_types.py:65-73`
- Modify: `backend/core/modeling_strategist.py:37-42`
- Modify: `backend/knowledge/examples/*.py`（features 中引用 type 的地方保持兼容）
- Test: `tests/test_feature_model.py`（新建）

### Step 1: Write the failing tests

```python
# tests/test_feature_model.py
"""Tests for structured Feature model."""

from __future__ import annotations

import pytest

from backend.knowledge.part_types import (
    ChamferSpec,
    DrawingSpec,
    Feature,
    FilletSpec,
    HolePatternSpec,
    KeywaySpec,
    PartType,
    BaseBodySpec,
)


class TestFeatureModel:
    def test_hole_pattern_feature(self) -> None:
        """HolePatternSpec can be created as a Feature."""
        feat = Feature(
            type="hole_pattern",
            spec=HolePatternSpec(count=6, diameter=10, pcd=70),
        )
        assert feat.type == "hole_pattern"
        assert feat.spec.count == 6

    def test_fillet_feature(self) -> None:
        feat = Feature(type="fillet", spec=FilletSpec(radius=3))
        assert feat.type == "fillet"
        assert feat.spec.radius == 3

    def test_chamfer_feature(self) -> None:
        feat = Feature(type="chamfer", spec=ChamferSpec(size=1.5))
        assert feat.type == "chamfer"

    def test_keyway_feature(self) -> None:
        feat = Feature(
            type="keyway",
            spec=KeywaySpec(width=8, depth=4, length=30),
        )
        assert feat.type == "keyway"

    def test_generic_feature_dict(self) -> None:
        """Untyped features fall back to GenericFeature with a dict payload."""
        feat = Feature(type="custom_groove", spec={"width": 5, "depth": 2})
        assert feat.type == "custom_groove"

    def test_drawing_spec_with_typed_features(self) -> None:
        spec = DrawingSpec(
            part_type=PartType.ROTATIONAL,
            description="法兰盘",
            base_body=BaseBodySpec(method="revolve"),
            features=[
                Feature(type="hole_pattern", spec=HolePatternSpec(count=6, diameter=10, pcd=70)),
                Feature(type="fillet", spec=FilletSpec(radius=3)),
            ],
        )
        assert len(spec.features) == 2
        assert spec.features[0].type == "hole_pattern"

    def test_drawing_spec_backward_compat_dict(self) -> None:
        """DrawingSpec still accepts plain dicts via validator."""
        spec = DrawingSpec(
            part_type=PartType.PLATE,
            description="板件",
            base_body=BaseBodySpec(method="extrude"),
            features=[{"type": "hole_pattern", "count": 4, "diameter": 8}],
        )
        assert len(spec.features) == 1
        assert spec.features[0].type == "hole_pattern"

    def test_feature_to_dict(self) -> None:
        """Feature round-trips through JSON."""
        feat = Feature(type="fillet", spec=FilletSpec(radius=3))
        d = feat.model_dump()
        assert d["type"] == "fillet"
        feat2 = Feature.model_validate(d)
        assert feat2.spec.radius == 3

    def test_to_prompt_text_with_features(self) -> None:
        """to_prompt_text renders typed features."""
        spec = DrawingSpec(
            part_type=PartType.ROTATIONAL,
            description="轴",
            base_body=BaseBodySpec(method="revolve"),
            features=[
                Feature(type="fillet", spec=FilletSpec(radius=2, locations=["base"])),
            ],
        )
        text = spec.to_prompt_text()
        assert "fillet" in text.lower() or "圆角" in text


class TestExtractFeatures:
    def test_extract_from_typed_features(self) -> None:
        """Strategist extracts feature tags from typed Feature objects."""
        from backend.core.modeling_strategist import _extract_features_from_spec

        spec = DrawingSpec(
            part_type=PartType.ROTATIONAL,
            description="法兰盘",
            base_body=BaseBodySpec(method="revolve"),
            features=[
                Feature(type="hole_pattern", spec=HolePatternSpec(count=6, diameter=10, pcd=70)),
                Feature(type="fillet", spec=FilletSpec(radius=3)),
            ],
        )
        tags = _extract_features_from_spec(spec)
        assert "revolve" in tags
        assert "hole_pattern" in tags
        assert "fillet" in tags
```

### Step 2: Run tests to verify they fail

```bash
pytest tests/test_feature_model.py -v
```

Expected: FAIL — `Feature`, `KeywaySpec` not importable.

### Step 3: Implement Feature model

Modify `backend/knowledge/part_types.py`:

1. Add `KeywaySpec`, `SlotSpec`, `GenericFeatureSpec` models
2. Add `Feature` model (Pydantic) with `type: str` + `spec: Union[HolePatternSpec, FilletSpec, ChamferSpec, KeywaySpec, SlotSpec, dict]`
3. Change `DrawingSpec.features` from `list[dict]` to `list[Feature]`
4. Add a Pydantic `field_validator` for backward compatibility: plain dicts get wrapped into `Feature`
5. Update `to_prompt_text()` to render typed features

```python
# New models to add to part_types.py

class KeywaySpec(BaseModel):
    """键槽规格"""
    width: float
    depth: float
    length: float


class SlotSpec(BaseModel):
    """槽规格"""
    width: float
    depth: float
    length: Optional[float] = None


class Feature(BaseModel):
    """结构化特征 — 支持类型化 spec 或 dict fallback"""
    type: str
    spec: HolePatternSpec | FilletSpec | ChamferSpec | KeywaySpec | SlotSpec | dict = {}

    @model_validator(mode="before")
    @classmethod
    def _from_flat_dict(cls, values: Any) -> Any:
        """Convert a flat dict like {"type": "fillet", "radius": 3} to Feature."""
        if isinstance(values, dict) and "spec" not in values:
            feat_type = values.pop("type", "unknown")
            return {"type": feat_type, "spec": values}
        return values
```

Then update `DrawingSpec.features`:
```python
features: list[Feature] = []
```

### Step 4: Update `_extract_features_from_spec` in `modeling_strategist.py`

```python
def _extract_features_from_spec(spec: DrawingSpec) -> set[str]:
    features: set[str] = set()
    if spec.base_body.method:
        features.add(spec.base_body.method)
    if spec.base_body.bore is not None:
        features.add("bore")
    for feat in spec.features:
        if feat.type:
            features.add(feat.type)
    return features
```

Key change: `feat.type` instead of `feat.get("type", "")` — typed access.

### Step 5: Run all tests

```bash
pytest tests/ -v
```

Expected: ALL PASS (240+ existing tests + new tests).

### Step 6: Commit

```bash
git add backend/knowledge/part_types.py backend/core/modeling_strategist.py tests/test_feature_model.py
git commit -m "feat: structured Feature model — list[dict] → list[Feature] (Phase 3 Task 3.1)"
```

---

## Task 2: ParametricTemplate 数据模型（对应 OpenSpec T3.2）

**Files:**
- Create: `backend/models/template.py`
- Create: `tests/test_template_model.py`

### Step 1: Write the failing tests

```python
# tests/test_template_model.py
"""Tests for ParametricTemplate data model and YAML loader."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


class TestParamDefinition:
    def test_basic_param(self) -> None:
        from backend.models.template import ParamDefinition

        p = ParamDefinition(
            name="diameter",
            display_name="直径",
            unit="mm",
            param_type="float",
            range_min=10,
            range_max=500,
            default=100,
        )
        assert p.name == "diameter"
        assert p.unit == "mm"
        assert p.validate_value(100) is True
        assert p.validate_value(5) is False  # below range_min
        assert p.validate_value(600) is False  # above range_max

    def test_int_param(self) -> None:
        from backend.models.template import ParamDefinition

        p = ParamDefinition(
            name="bolt_count",
            display_name="螺栓数",
            param_type="int",
            range_min=0,
            range_max=12,
            default=6,
        )
        assert p.validate_value(6) is True
        assert p.validate_value(13) is False

    def test_depends_on(self) -> None:
        from backend.models.template import ParamDefinition

        p = ParamDefinition(
            name="pcd",
            display_name="螺栓孔分布圆直径",
            unit="mm",
            param_type="float",
            depends_on="diameter",
        )
        assert p.depends_on == "diameter"


class TestParametricTemplate:
    def test_create_template(self) -> None:
        from backend.models.template import ParamDefinition, ParametricTemplate

        tmpl = ParametricTemplate(
            name="flange_disk",
            display_name="法兰盘",
            part_type="rotational",
            description="标准法兰盘模板",
            params=[
                ParamDefinition(name="diameter", display_name="直径", unit="mm",
                                param_type="float", range_min=20, range_max=500, default=100),
                ParamDefinition(name="height", display_name="高度", unit="mm",
                                param_type="float", range_min=5, range_max=100, default=20),
            ],
            constraints=["height < diameter"],
            code_template="import cadquery as cq\nresult = cq.Workplane('XY').circle({{ diameter }}/2).extrude({{ height }})\ncq.exporters.export(result, '{{ output_filename }}')",
        )
        assert tmpl.name == "flange_disk"
        assert len(tmpl.params) == 2

    def test_validate_params_pass(self) -> None:
        from backend.models.template import ParamDefinition, ParametricTemplate

        tmpl = ParametricTemplate(
            name="test",
            display_name="测试",
            part_type="plate",
            description="test",
            params=[
                ParamDefinition(name="width", display_name="宽", unit="mm",
                                param_type="float", range_min=10, range_max=200, default=50),
            ],
            code_template="...",
        )
        errors = tmpl.validate_params({"width": 50})
        assert errors == []

    def test_validate_params_out_of_range(self) -> None:
        from backend.models.template import ParamDefinition, ParametricTemplate

        tmpl = ParametricTemplate(
            name="test",
            display_name="测试",
            part_type="plate",
            description="test",
            params=[
                ParamDefinition(name="width", display_name="宽", unit="mm",
                                param_type="float", range_min=10, range_max=200, default=50),
            ],
            code_template="...",
        )
        errors = tmpl.validate_params({"width": 5})
        assert len(errors) > 0
        assert "width" in errors[0]

    def test_validate_params_missing(self) -> None:
        from backend.models.template import ParamDefinition, ParametricTemplate

        tmpl = ParametricTemplate(
            name="test",
            display_name="测试",
            part_type="plate",
            description="test",
            params=[
                ParamDefinition(name="width", display_name="宽", unit="mm",
                                param_type="float", range_min=10, range_max=200, default=50),
            ],
            code_template="...",
        )
        # Missing 'width' — should use default, so no error
        errors = tmpl.validate_params({})
        assert errors == []

    def test_get_defaults(self) -> None:
        from backend.models.template import ParamDefinition, ParametricTemplate

        tmpl = ParametricTemplate(
            name="test",
            display_name="测试",
            part_type="plate",
            description="test",
            params=[
                ParamDefinition(name="w", display_name="宽", param_type="float", default=50),
                ParamDefinition(name="h", display_name="高", param_type="float", default=10),
            ],
            code_template="...",
        )
        defaults = tmpl.get_defaults()
        assert defaults == {"w": 50, "h": 10}


class TestYamlRoundTrip:
    def test_load_from_yaml_string(self) -> None:
        from backend.models.template import ParametricTemplate

        yaml_str = textwrap.dedent("""\
            name: simple_disk
            display_name: 简单圆盘
            part_type: rotational
            description: 基本圆盘模板
            params:
              - name: diameter
                display_name: 直径
                unit: mm
                param_type: float
                range_min: 20
                range_max: 500
                default: 100
              - name: height
                display_name: 高度
                unit: mm
                param_type: float
                range_min: 5
                range_max: 100
                default: 20
            constraints:
              - "height < diameter"
            code_template: |
              import cadquery as cq
              result = cq.Workplane("XY").circle({{ diameter }}/2).extrude({{ height }})
              cq.exporters.export(result, "{{ output_filename }}")
        """)
        tmpl = ParametricTemplate.from_yaml_string(yaml_str)
        assert tmpl.name == "simple_disk"
        assert len(tmpl.params) == 2
        assert tmpl.params[0].range_min == 20

    def test_to_yaml_string(self) -> None:
        from backend.models.template import ParamDefinition, ParametricTemplate

        tmpl = ParametricTemplate(
            name="test",
            display_name="测试",
            part_type="plate",
            description="test template",
            params=[
                ParamDefinition(name="w", display_name="宽", param_type="float", default=50),
            ],
            code_template="...",
        )
        yaml_str = tmpl.to_yaml_string()
        assert "name: test" in yaml_str
        assert "display_name:" in yaml_str

    def test_load_from_yaml_file(self, tmp_path: Path) -> None:
        from backend.models.template import ParametricTemplate, load_template

        yaml_content = textwrap.dedent("""\
            name: file_test
            display_name: 文件测试
            part_type: general
            description: from file
            params: []
            code_template: "pass"
        """)
        f = tmp_path / "test_template.yaml"
        f.write_text(yaml_content, encoding="utf-8")

        tmpl = load_template(f)
        assert tmpl.name == "file_test"

    def test_load_all_templates_from_dir(self, tmp_path: Path) -> None:
        from backend.models.template import load_all_templates

        for i in range(3):
            (tmp_path / f"t{i}.yaml").write_text(
                f"name: t{i}\ndisplay_name: 模板{i}\npart_type: general\n"
                f"description: test\nparams: []\ncode_template: pass\n",
                encoding="utf-8",
            )
        templates = load_all_templates(tmp_path)
        assert len(templates) == 3
```

### Step 2: Run tests to verify they fail

```bash
pytest tests/test_template_model.py -v
```

Expected: FAIL — `backend.models.template` does not exist.

### Step 3: Implement ParametricTemplate

Create `backend/models/template.py`:

```python
"""ParametricTemplate data model — Pydantic + YAML storage.

Templates define parametric CadQuery code generators:
- ParamDefinition: name, type, range, default, dependencies
- ParametricTemplate: params + constraints + Jinja2 code template
- YAML ↔ Pydantic serialization for human-editable storage
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel


class ParamDefinition(BaseModel):
    """Single parameter definition for a template."""

    name: str
    display_name: str
    unit: str = ""
    param_type: str = "float"  # float, int, bool, str
    range_min: Optional[float] = None
    range_max: Optional[float] = None
    default: Optional[Any] = None
    depends_on: Optional[str] = None

    def validate_value(self, value: Any) -> bool:
        if self.range_min is not None and value < self.range_min:
            return False
        if self.range_max is not None and value > self.range_max:
            return False
        return True


class ParametricTemplate(BaseModel):
    """Parametric CadQuery code template stored as YAML."""

    name: str
    display_name: str
    part_type: str
    description: str = ""
    params: list[ParamDefinition] = []
    constraints: list[str] = []
    code_template: str = ""

    def validate_params(self, params: dict[str, Any]) -> list[str]:
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
        return {p.name: p.default for p in self.params if p.default is not None}

    @classmethod
    def from_yaml_string(cls, yaml_str: str) -> ParametricTemplate:
        data = yaml.safe_load(yaml_str)
        return cls.model_validate(data)

    def to_yaml_string(self) -> str:
        return yaml.dump(
            self.model_dump(exclude_none=True),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


def load_template(path: Path) -> ParametricTemplate:
    text = path.read_text(encoding="utf-8")
    return ParametricTemplate.from_yaml_string(text)


def load_all_templates(directory: Path) -> list[ParametricTemplate]:
    templates: list[ParametricTemplate] = []
    for f in sorted(directory.glob("*.yaml")):
        templates.append(load_template(f))
    return templates
```

### Step 4: Run tests

```bash
pytest tests/test_template_model.py -v
```

Expected: ALL PASS.

### Step 5: Run full suite

```bash
pytest tests/ -v
```

Expected: ALL PASS.

### Step 6: Commit

```bash
git add backend/models/template.py tests/test_template_model.py
git commit -m "feat: ParametricTemplate data model + YAML loader (Phase 3 Task 3.2)"
```

---

## Task 3: ParametricTemplateEngine 核心（对应 OpenSpec T3.3）

**Files:**
- Create: `backend/core/template_engine.py`
- Test: `tests/test_template_engine.py`
- Dependency: `pip install jinja2`（添加到 pyproject.toml）

### Step 1: Write the failing tests

```python
# tests/test_template_engine.py
"""Tests for ParametricTemplateEngine — match, render, validate."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from backend.models.template import ParamDefinition, ParametricTemplate


def _make_flange_template() -> ParametricTemplate:
    return ParametricTemplate(
        name="flange_disk",
        display_name="法兰盘",
        part_type="rotational",
        description="标准法兰盘",
        params=[
            ParamDefinition(name="diameter", display_name="直径", unit="mm",
                            param_type="float", range_min=20, range_max=500, default=100),
            ParamDefinition(name="height", display_name="高度", unit="mm",
                            param_type="float", range_min=5, range_max=100, default=20),
        ],
        constraints=["height < diameter"],
        code_template=textwrap.dedent("""\
            import cadquery as cq

            diameter = {{ diameter }}
            height = {{ height }}

            result = cq.Workplane("XY").circle(diameter / 2).extrude(height)
            cq.exporters.export(result, "{{ output_filename }}")
        """),
    )


def _make_plate_template() -> ParametricTemplate:
    return ParametricTemplate(
        name="rect_plate",
        display_name="矩形板",
        part_type="plate",
        description="矩形板",
        params=[
            ParamDefinition(name="length", display_name="长", unit="mm",
                            param_type="float", range_min=10, range_max=500, default=100),
            ParamDefinition(name="width", display_name="宽", unit="mm",
                            param_type="float", range_min=10, range_max=500, default=50),
            ParamDefinition(name="thickness", display_name="厚", unit="mm",
                            param_type="float", range_min=1, range_max=50, default=10),
        ],
        code_template=textwrap.dedent("""\
            import cadquery as cq

            result = cq.Workplane("XY").box({{ length }}, {{ width }}, {{ thickness }})
            cq.exporters.export(result, "{{ output_filename }}")
        """),
    )


class TestTemplateEngineRender:
    def test_render_code(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine(templates=[_make_flange_template()])
        code = engine.render("flange_disk", {"diameter": 120, "height": 25})
        assert "diameter = 120" in code
        assert "height = 25" in code
        assert "cq.exporters.export" in code

    def test_render_uses_defaults(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine(templates=[_make_flange_template()])
        code = engine.render("flange_disk", {})
        assert "diameter = 100" in code  # default
        assert "height = 20" in code  # default

    def test_render_output_filename(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine(templates=[_make_flange_template()])
        code = engine.render("flange_disk", {}, output_filename="test.step")
        assert '"test.step"' in code

    def test_render_unknown_template_raises(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine(templates=[])
        with pytest.raises(KeyError):
            engine.render("nonexistent", {})


class TestTemplateEngineMatch:
    def test_find_match_by_part_type(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine(templates=[_make_flange_template(), _make_plate_template()])
        matches = engine.find_matches("rotational")
        assert len(matches) == 1
        assert matches[0].name == "flange_disk"

    def test_find_match_returns_empty(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine(templates=[_make_flange_template()])
        matches = engine.find_matches("gear")
        assert matches == []

    def test_find_all(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine(templates=[_make_flange_template(), _make_plate_template()])
        assert len(engine.list_templates()) == 2


class TestTemplateEngineValidate:
    def test_validate_valid_params(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine(templates=[_make_flange_template()])
        errors = engine.validate("flange_disk", {"diameter": 100, "height": 20})
        assert errors == []

    def test_validate_out_of_range(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine(templates=[_make_flange_template()])
        errors = engine.validate("flange_disk", {"diameter": 5})
        assert len(errors) > 0

    def test_validate_constraint_violation(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine(templates=[_make_flange_template()])
        errors = engine.validate("flange_disk", {"diameter": 20, "height": 50})
        assert any("constraint" in e.lower() for e in errors)


class TestTemplateEngineLoadFromDir:
    def test_load_from_directory(self, tmp_path: Path) -> None:
        from backend.core.template_engine import TemplateEngine

        yaml_content = textwrap.dedent("""\
            name: dir_test
            display_name: 目录测试
            part_type: general
            description: test
            params: []
            code_template: |
              import cadquery as cq
              result = cq.Workplane("XY").box(10, 10, 10)
              cq.exporters.export(result, "{{ output_filename }}")
        """)
        (tmp_path / "test.yaml").write_text(yaml_content, encoding="utf-8")

        engine = TemplateEngine.from_directory(tmp_path)
        assert len(engine.list_templates()) == 1
```

### Step 2: Run tests to verify they fail

```bash
pytest tests/test_template_engine.py -v
```

Expected: FAIL — `backend.core.template_engine` does not exist.

### Step 3: Add Jinja2 dependency

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
# Verify jinja2 is available (it's a LangChain transitive dep already)
python -c "import jinja2; print(jinja2.__version__)"
```

If not available, add to pyproject.toml `[tool.poetry.dependencies]`:
```
jinja2 = ">=3.1"
```

Also add `conftest.py` stub exclusion if needed — but Jinja2 is NOT stubbed (lightweight pure Python).

### Step 4: Implement TemplateEngine

Create `backend/core/template_engine.py`:

```python
"""ParametricTemplateEngine — match, render, validate.

Core engine for the parametric template system:
- find_matches(part_type): list templates for a given part type
- render(name, params): Jinja2 render CadQuery code from template
- validate(name, params): check param ranges and constraints
"""

from __future__ import annotations

from pathlib import Path

import jinja2

from backend.models.template import ParametricTemplate, load_all_templates


class TemplateEngine:
    """Parametric template engine — lookup, validate, render."""

    def __init__(self, templates: list[ParametricTemplate] | None = None) -> None:
        self._templates: dict[str, ParametricTemplate] = {}
        if templates:
            for t in templates:
                self._templates[t.name] = t

    @classmethod
    def from_directory(cls, path: Path) -> TemplateEngine:
        templates = load_all_templates(path)
        return cls(templates=templates)

    def list_templates(self) -> list[ParametricTemplate]:
        return list(self._templates.values())

    def get_template(self, name: str) -> ParametricTemplate:
        if name not in self._templates:
            raise KeyError(f"Template '{name}' not found")
        return self._templates[name]

    def find_matches(self, part_type: str) -> list[ParametricTemplate]:
        return [t for t in self._templates.values() if t.part_type == part_type]

    def validate(self, name: str, params: dict) -> list[str]:
        tmpl = self.get_template(name)
        errors = tmpl.validate_params(params)
        # Check constraints
        merged = tmpl.get_defaults()
        merged.update(params)
        for constraint in tmpl.constraints:
            try:
                if not eval(constraint, {"__builtins__": {}}, merged):
                    errors.append(f"Constraint violation: {constraint}")
            except Exception:
                errors.append(f"Constraint evaluation error: {constraint}")
        return errors

    def render(
        self,
        name: str,
        params: dict,
        output_filename: str = "output.step",
    ) -> str:
        tmpl = self.get_template(name)
        merged = tmpl.get_defaults()
        merged.update(params)
        merged["output_filename"] = output_filename
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        template = env.from_string(tmpl.code_template)
        return template.render(**merged)
```

### Step 5: Run tests

```bash
pytest tests/test_template_engine.py -v
```

Expected: ALL PASS.

### Step 6: Run full suite

```bash
pytest tests/ -v
```

Expected: ALL PASS.

### Step 7: Commit

```bash
git add backend/core/template_engine.py tests/test_template_engine.py
git commit -m "feat: ParametricTemplateEngine — match, render, validate (Phase 3 Task 3.3)"
```

---

## Task 4: 首批参数化模板 — 7 类型 × 2 变体（对应 OpenSpec T3.4）

**Files:**
- Create: `backend/knowledge/templates/` directory
- Create: 13 YAML template files (one per variant)
- Test: `tests/test_templates_library.py`

**注意:** 此任务代码量大（13 个完整 YAML 模板）。每个模板包含参数定义 + 约束 + Jinja2 CadQuery 代码。模板的 CadQuery 代码验证需要真实 CadQuery 环境。

### Step 1: Write the test framework

```python
# tests/test_templates_library.py
"""Tests for the built-in template library.

Tests split into two groups:
1. Structural tests (no CadQuery required): YAML loads, params valid, code renders
2. CadQuery execution tests (requires CadQuery): rendered code produces valid STEP
"""

from __future__ import annotations

from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).parent.parent / "backend" / "knowledge" / "templates"


class TestTemplateLibraryStructure:
    """Structural validation — no CadQuery needed."""

    def test_templates_directory_exists(self) -> None:
        assert TEMPLATES_DIR.is_dir()

    def test_at_least_13_templates(self) -> None:
        from backend.models.template import load_all_templates

        templates = load_all_templates(TEMPLATES_DIR)
        assert len(templates) >= 13

    def test_all_part_types_covered(self) -> None:
        from backend.models.template import load_all_templates

        templates = load_all_templates(TEMPLATES_DIR)
        types = {t.part_type for t in templates}
        expected = {"rotational", "rotational_stepped", "plate", "bracket", "housing", "gear"}
        assert expected.issubset(types)

    def test_each_template_has_params(self) -> None:
        from backend.models.template import load_all_templates

        for tmpl in load_all_templates(TEMPLATES_DIR):
            assert len(tmpl.params) > 0, f"Template '{tmpl.name}' has no params"

    def test_each_template_has_code(self) -> None:
        from backend.models.template import load_all_templates

        for tmpl in load_all_templates(TEMPLATES_DIR):
            assert len(tmpl.code_template) > 50, f"Template '{tmpl.name}' code too short"

    def test_each_template_renders_with_defaults(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine.from_directory(TEMPLATES_DIR)
        for tmpl in engine.list_templates():
            code = engine.render(tmpl.name, {})
            assert "cq.exporters.export" in code, f"Template '{tmpl.name}' missing export"
            assert "import cadquery" in code, f"Template '{tmpl.name}' missing import"

    def test_each_template_defaults_pass_validation(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine.from_directory(TEMPLATES_DIR)
        for tmpl in engine.list_templates():
            errors = engine.validate(tmpl.name, {})
            assert errors == [], f"Template '{tmpl.name}' defaults fail: {errors}"

    def test_rotational_templates(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine.from_directory(TEMPLATES_DIR)
        rotational = engine.find_matches("rotational")
        assert len(rotational) >= 2, "Need >= 2 rotational templates"

    def test_plate_templates(self) -> None:
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine.from_directory(TEMPLATES_DIR)
        plates = engine.find_matches("plate")
        assert len(plates) >= 2, "Need >= 2 plate templates"


class TestTemplateExecution:
    """CadQuery execution tests — skip if CadQuery not installed."""

    @pytest.fixture(autouse=True)
    def _skip_without_cadquery(self) -> None:
        pytest.importorskip("cadquery")

    def test_flange_disk_generates_step(self, tmp_path: Path) -> None:
        import cadquery as cq
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine.from_directory(TEMPLATES_DIR)
        code = engine.render("flange_disk", {"diameter": 100, "height": 20},
                             output_filename=str(tmp_path / "flange.step"))
        exec(code, {"__builtins__": __builtins__})
        assert (tmp_path / "flange.step").exists()

    def test_rect_plate_generates_step(self, tmp_path: Path) -> None:
        import cadquery as cq
        from backend.core.template_engine import TemplateEngine

        engine = TemplateEngine.from_directory(TEMPLATES_DIR)
        code = engine.render("rect_plate", {"length": 100, "width": 50, "thickness": 10},
                             output_filename=str(tmp_path / "plate.step"))
        exec(code, {"__builtins__": __builtins__})
        assert (tmp_path / "plate.step").exists()
```

### Step 2: Create template directory structure

```bash
mkdir -p backend/knowledge/templates
```

### Step 3: Create all 13 YAML templates

实现者需创建以下 13 个模板文件。每个模板包含：
1. 参数定义（name, display_name, unit, type, range, default）
2. 约束规则（constraints）
3. 完整 Jinja2 CadQuery 代码模板

**模板清单：**

| # | 文件名 | 类型 | 描述 |
|---|--------|------|------|
| 1 | `rotational_flange_disk.yaml` | rotational | 法兰盘：圆盘 + 中心孔 + 螺栓孔阵 |
| 2 | `rotational_simple_disk.yaml` | rotational | 简单圆盘：圆盘 + 可选中心孔 |
| 3 | `rotational_stepped_shaft.yaml` | rotational_stepped | 阶梯轴：2-3 阶梯 + 过渡圆角 |
| 4 | `rotational_stepped_flange_shaft.yaml` | rotational_stepped | 法兰轴：轴身 + 法兰 + 螺栓孔 |
| 5 | `plate_rect.yaml` | plate | 矩形板：长宽厚 + 可选角圆角 |
| 6 | `plate_with_holes.yaml` | plate | 带孔板：矩形板 + 网格/自由孔阵 |
| 7 | `bracket_l_shape.yaml` | bracket | L 型支架：底板 + 立板 + 可选加强筋 |
| 8 | `bracket_u_shape.yaml` | bracket | U 型支架：底板 + 两侧板 |
| 9 | `housing_cylinder_shell.yaml` | housing | 圆柱壳：抽壳 + 可选法兰 |
| 10 | `housing_box_shell.yaml` | housing | 箱体壳：矩形抽壳 + 安装凸台 |
| 11 | `gear_spur.yaml` | gear | 直齿圆柱齿轮：模数 + 齿数 + 齿宽 |
| 12 | `general_hollow_tube.yaml` | general | 空心管：外径 + 内径 + 长度 |
| 13 | `general_block_with_holes.yaml` | general | 多孔块体：长方体 + 通孔阵列 |

**示范模板 #1（其余按此模式创建）：**

```yaml
# backend/knowledge/templates/rotational_flange_disk.yaml
name: flange_disk
display_name: 法兰盘
part_type: rotational
description: 标准法兰盘 — 圆盘基体 + 中心通孔 + 圆周螺栓孔阵列，适用于管道连接、轴承座等
params:
  - name: diameter
    display_name: 法兰外径
    unit: mm
    param_type: float
    range_min: 30
    range_max: 500
    default: 100
  - name: height
    display_name: 法兰厚度
    unit: mm
    param_type: float
    range_min: 5
    range_max: 80
    default: 15
  - name: bore_diameter
    display_name: 中心孔直径
    unit: mm
    param_type: float
    range_min: 0
    range_max: 400
    default: 30
  - name: bolt_count
    display_name: 螺栓数量
    unit: ""
    param_type: int
    range_min: 0
    range_max: 24
    default: 6
  - name: bolt_diameter
    display_name: 螺栓孔直径
    unit: mm
    param_type: float
    range_min: 3
    range_max: 30
    default: 10
  - name: pcd
    display_name: 螺栓孔分布圆直径
    unit: mm
    param_type: float
    range_min: 20
    range_max: 480
    default: 70
    depends_on: diameter
  - name: fillet_radius
    display_name: 圆角半径
    unit: mm
    param_type: float
    range_min: 0
    range_max: 20
    default: 0
constraints:
  - "bore_diameter < diameter * 0.8"
  - "pcd > bore_diameter + bolt_diameter"
  - "pcd < diameter - bolt_diameter"
  - "bolt_diameter < height * 2"
code_template: |
  import cadquery as cq
  import math

  # Parameters
  diameter = {{ diameter }}
  height = {{ height }}
  bore_diameter = {{ bore_diameter }}
  bolt_count = {{ bolt_count }}
  bolt_diameter = {{ bolt_diameter }}
  pcd = {{ pcd }}
  fillet_radius = {{ fillet_radius }}

  r_outer = diameter / 2

  # Base body
  {% if bore_diameter > 0 %}
  r_bore = bore_diameter / 2
  profile_pts = [
      (r_bore, 0),
      (r_outer, 0),
      (r_outer, height),
      (r_bore, height),
  ]
  result = cq.Workplane("XZ").polyline(profile_pts).close().revolve(360, (0,0,0), (0,1,0))
  {% else %}
  result = cq.Workplane("XY").circle(r_outer).extrude(height)
  {% endif %}

  # Fillet
  {% if fillet_radius > 0 %}
  try:
      result = result.edges("|Z").fillet(fillet_radius)
  except Exception:
      pass
  {% endif %}

  # Bolt holes
  {% if bolt_count > 0 %}
  for i in range(bolt_count):
      angle = math.radians(i * 360 / bolt_count)
      x = (pcd / 2) * math.cos(angle)
      y = (pcd / 2) * math.sin(angle)
      hole = cq.Workplane("XY").center(x, y).circle(bolt_diameter / 2).extrude(height + 1)
      result = result.cut(hole)
  {% endif %}

  cq.exporters.export(result, "{{ output_filename }}")
```

**示范模板 #5（板件）：**

```yaml
# backend/knowledge/templates/plate_rect.yaml
name: rect_plate
display_name: 矩形板
part_type: plate
description: 基本矩形板件 — 长宽厚 + 可选四角圆角
params:
  - name: length
    display_name: 长度
    unit: mm
    param_type: float
    range_min: 10
    range_max: 1000
    default: 100
  - name: width
    display_name: 宽度
    unit: mm
    param_type: float
    range_min: 10
    range_max: 1000
    default: 60
  - name: thickness
    display_name: 厚度
    unit: mm
    param_type: float
    range_min: 1
    range_max: 100
    default: 10
  - name: corner_radius
    display_name: 四角圆角
    unit: mm
    param_type: float
    range_min: 0
    range_max: 50
    default: 0
constraints:
  - "corner_radius < min(length, width) / 2"
  - "thickness < min(length, width)"
code_template: |
  import cadquery as cq

  length = {{ length }}
  width = {{ width }}
  thickness = {{ thickness }}
  corner_radius = {{ corner_radius }}

  result = cq.Workplane("XY").box(length, width, thickness)

  {% if corner_radius > 0 %}
  try:
      result = result.edges("|Z").fillet(corner_radius)
  except Exception:
      pass
  {% endif %}

  cq.exporters.export(result, "{{ output_filename }}")
```

其余 11 个模板按相同模式创建。每个模板必须：
- 有完整的参数定义（含 range 和 default）
- 有约束规则（至少 1 条）
- 有完整的 CadQuery 代码模板（含 export）
- 使用 Jinja2 条件块处理可选特征
- 用 defaults 渲染后可通过 AST 解析

### Step 4: Run template library tests

```bash
pytest tests/test_templates_library.py -v
```

Expected: Structure tests PASS, Execution tests SKIP (unless CadQuery installed).

### Step 5: Commit

```bash
git add backend/knowledge/templates/ tests/test_templates_library.py
git commit -m "feat: 13 parametric YAML templates across 7 part types (Phase 3 Task 3.4)"
```

---

## Task 5: 模板管理 API（对应 OpenSpec T3.5）

**Files:**
- Create: `backend/api/templates.py`
- Modify: `backend/main.py:26` — register templates router
- Test: `tests/test_templates_api.py`

### Step 1: Write the failing tests

```python
# tests/test_templates_api.py
"""Tests for template management API routes."""

from __future__ import annotations

import textwrap

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path) -> TestClient:
    """Create a TestClient with a temp template directory."""
    # Write one test template
    yaml_content = textwrap.dedent("""\
        name: test_disk
        display_name: 测试圆盘
        part_type: rotational
        description: 测试用模板
        params:
          - name: diameter
            display_name: 直径
            unit: mm
            param_type: float
            range_min: 10
            range_max: 500
            default: 100
        code_template: |
          import cadquery as cq
          result = cq.Workplane("XY").circle({{ diameter }}/2).extrude(10)
          cq.exporters.export(result, "{{ output_filename }}")
    """)
    (tmp_path / "test_disk.yaml").write_text(yaml_content, encoding="utf-8")

    import backend.api.templates as tmpl_module
    tmpl_module._TEMPLATES_DIR = tmp_path  # override for testing

    from backend.main import app
    return TestClient(app)


class TestTemplateListAPI:
    def test_list_templates(self, client: TestClient) -> None:
        resp = client.get("/api/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["name"] == "test_disk"

    def test_list_filter_by_part_type(self, client: TestClient) -> None:
        resp = client.get("/api/templates?part_type=rotational")
        assert resp.status_code == 200
        data = resp.json()
        assert all(t["part_type"] == "rotational" for t in data)

    def test_list_filter_empty(self, client: TestClient) -> None:
        resp = client.get("/api/templates?part_type=nonexistent")
        assert resp.status_code == 200
        assert resp.json() == []


class TestTemplateDetailAPI:
    def test_get_template(self, client: TestClient) -> None:
        resp = client.get("/api/templates/test_disk")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test_disk"
        assert "params" in data
        assert "code_template" in data

    def test_get_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/templates/nonexistent")
        assert resp.status_code == 404


class TestTemplateValidateAPI:
    def test_validate_valid(self, client: TestClient) -> None:
        resp = client.post("/api/templates/test_disk/validate", json={"diameter": 100})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_validate_out_of_range(self, client: TestClient) -> None:
        resp = client.post("/api/templates/test_disk/validate", json={"diameter": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0


class TestTemplateCRUD:
    def test_create_template(self, client: TestClient) -> None:
        new_tmpl = {
            "name": "new_plate",
            "display_name": "新板件",
            "part_type": "plate",
            "description": "测试创建",
            "params": [{"name": "w", "display_name": "宽", "param_type": "float", "default": 50}],
            "code_template": "import cadquery as cq\nresult = cq.Workplane('XY').box({{ w }}, 10, 5)\ncq.exporters.export(result, '{{ output_filename }}')",
        }
        resp = client.post("/api/templates", json=new_tmpl)
        assert resp.status_code == 201
        # Verify it's now listed
        resp2 = client.get("/api/templates/new_plate")
        assert resp2.status_code == 200

    def test_update_template(self, client: TestClient) -> None:
        update = {
            "name": "test_disk",
            "display_name": "更新的圆盘",
            "part_type": "rotational",
            "description": "更新后",
            "params": [{"name": "diameter", "display_name": "直径", "param_type": "float", "default": 200}],
            "code_template": "import cadquery as cq\nresult = cq.Workplane('XY').circle({{ diameter }}/2).extrude(10)\ncq.exporters.export(result, '{{ output_filename }}')",
        }
        resp = client.put("/api/templates/test_disk", json=update)
        assert resp.status_code == 200
        # Verify update
        data = client.get("/api/templates/test_disk").json()
        assert data["display_name"] == "更新的圆盘"

    def test_delete_template(self, client: TestClient) -> None:
        resp = client.delete("/api/templates/test_disk")
        assert resp.status_code == 200
        # Verify deleted
        resp2 = client.get("/api/templates/test_disk")
        assert resp2.status_code == 404
```

### Step 2: Run tests to verify they fail

```bash
pytest tests/test_templates_api.py -v
```

Expected: FAIL — `backend.api.templates` does not exist.

### Step 3: Add `starlette` and `httpx` to conftest stub exceptions if needed

FastAPI's TestClient uses `httpx` internally. Check if `httpx` is stubbed in conftest.py — if yes, remove it from `_STUB_ROOTS`. (Note: httpx IS currently in the stub list. Need to remove it or use a different approach.)

**解决方案：** 在测试文件中先 import httpx，然后再 import fastapi。或者将 `httpx` 从 `_STUB_ROOTS` 中移除并安装真实 httpx（`pip install httpx`）。推荐移除 stub 并安装 httpx，因为 FastAPI TestClient 需要真实 httpx。

### Step 4: Implement template API

Create `backend/api/templates.py`:

```python
"""Template management API — CRUD + validate + preview."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.template_engine import TemplateEngine
from backend.models.template import ParametricTemplate, load_all_templates

router = APIRouter()

# Default templates directory — overridable for testing
_TEMPLATES_DIR = Path(__file__).parent.parent / "knowledge" / "templates"


def _get_engine() -> TemplateEngine:
    return TemplateEngine.from_directory(_TEMPLATES_DIR)


class ValidateRequest(BaseModel):
    pass  # accepts arbitrary params via **kwargs

    model_config = {"extra": "allow"}


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[str]


@router.get("/templates")
async def list_templates(part_type: Optional[str] = None) -> list[dict[str, Any]]:
    engine = _get_engine()
    templates = engine.list_templates()
    if part_type:
        templates = [t for t in templates if t.part_type == part_type]
    return [t.model_dump() for t in templates]


@router.get("/templates/{name}")
async def get_template(name: str) -> dict[str, Any]:
    engine = _get_engine()
    try:
        tmpl = engine.get_template(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
    return tmpl.model_dump()


@router.post("/templates", status_code=201)
async def create_template(body: dict[str, Any]) -> dict[str, Any]:
    tmpl = ParametricTemplate.model_validate(body)
    path = _TEMPLATES_DIR / f"{tmpl.name}.yaml"
    if path.exists():
        raise HTTPException(status_code=409, detail=f"Template '{tmpl.name}' already exists")
    path.write_text(tmpl.to_yaml_string(), encoding="utf-8")
    return tmpl.model_dump()


@router.put("/templates/{name}")
async def update_template(name: str, body: dict[str, Any]) -> dict[str, Any]:
    path = _TEMPLATES_DIR / f"{name}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
    tmpl = ParametricTemplate.model_validate(body)
    path.write_text(tmpl.to_yaml_string(), encoding="utf-8")
    return tmpl.model_dump()


@router.delete("/templates/{name}")
async def delete_template(name: str) -> dict[str, str]:
    path = _TEMPLATES_DIR / f"{name}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
    path.unlink()
    return {"status": "deleted", "name": name}


@router.post("/templates/{name}/validate")
async def validate_params(name: str, body: dict[str, Any]) -> ValidateResponse:
    engine = _get_engine()
    try:
        errors = engine.validate(name, body)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
    return ValidateResponse(valid=len(errors) == 0, errors=errors)
```

Then register in `backend/main.py`:

```python
from backend.api import benchmark, export, generate, health, pipeline, templates
# ...
app.include_router(templates.router, prefix="/api")
```

### Step 5: Run tests

```bash
pytest tests/test_templates_api.py -v
```

Expected: ALL PASS.

### Step 6: Run full suite

```bash
pytest tests/ -v
```

### Step 7: Commit

```bash
git add backend/api/templates.py backend/main.py tests/test_templates_api.py
git commit -m "feat: template management API — CRUD + validate (Phase 3 Task 3.5)"
```

---

## Task 6: 知识库扩充 — ~25 新示例（对应 OpenSpec T3.8）

**Files:**
- Modify: `backend/knowledge/examples/rotational.py` — 补充到 8 个
- Modify: `backend/knowledge/examples/plate.py` — 补充到 6 个
- Modify: `backend/knowledge/examples/bracket.py` — 补充到 6 个
- Modify: `backend/knowledge/examples/housing.py` — 补充到 5 个
- Modify: `backend/knowledge/examples/general.py` — 补充到 5 个（作为 SHELL 替代）
- Test: `tests/test_knowledge_expansion.py`

**当前状态（23 个示例）：**
- rotational: 4 个 → 目标 8 个（+4）
- plate: 4 个 → 目标 6 个（+2）
- bracket: 3 个 → 目标 6 个（+3）
- housing: 3 个 → 目标 5 个（+2）
- gear: 3 个 → 保持
- general: 3 个 → 目标 5 个（+2）

**总计新增：~13 个 TaggedExample**

### Step 1: Write the test

```python
# tests/test_knowledge_expansion.py
"""Tests for knowledge base expansion — verify example counts and quality."""

from __future__ import annotations

import pytest

from backend.knowledge.examples import EXAMPLES_BY_TYPE, get_tagged_examples
from backend.knowledge.part_types import PartType


class TestExampleCounts:
    def test_rotational_has_8(self) -> None:
        examples = get_tagged_examples(PartType.ROTATIONAL)
        assert len(examples) >= 8

    def test_plate_has_6(self) -> None:
        examples = get_tagged_examples(PartType.PLATE)
        assert len(examples) >= 6

    def test_bracket_has_6(self) -> None:
        examples = get_tagged_examples(PartType.BRACKET)
        assert len(examples) >= 6

    def test_housing_has_5(self) -> None:
        examples = get_tagged_examples(PartType.HOUSING)
        assert len(examples) >= 5

    def test_general_has_5(self) -> None:
        examples = get_tagged_examples(PartType.GENERAL)
        assert len(examples) >= 5

    def test_total_at_least_36(self) -> None:
        """全库至少 36 个示例 (23 + 13 新增)。"""
        seen_ids: set[int] = set()
        total = 0
        for examples in EXAMPLES_BY_TYPE.values():
            for ex in examples:
                if id(ex) not in seen_ids:
                    seen_ids.add(id(ex))
                    total += 1
        assert total >= 36


class TestExampleQuality:
    def test_all_have_features(self) -> None:
        """Every example must have at least one feature tag."""
        for part_type, examples in EXAMPLES_BY_TYPE.items():
            for ex in examples:
                assert len(ex.features) > 0, (
                    f"Example '{ex.description}' for {part_type} has no feature tags"
                )

    def test_all_have_export(self) -> None:
        """Every example must contain an export call."""
        for part_type, examples in EXAMPLES_BY_TYPE.items():
            for ex in examples:
                assert "export" in ex.code.lower(), (
                    f"Example '{ex.description}' for {part_type} missing export"
                )

    def test_all_have_import(self) -> None:
        """Every example must import cadquery."""
        for part_type, examples in EXAMPLES_BY_TYPE.items():
            for ex in examples:
                assert "import cadquery" in ex.code, (
                    f"Example '{ex.description}' for {part_type} missing cadquery import"
                )

    def test_unique_descriptions(self) -> None:
        """All descriptions are unique."""
        seen: set[str] = set()
        for examples in EXAMPLES_BY_TYPE.values():
            for ex in examples:
                assert ex.description not in seen, (
                    f"Duplicate description: {ex.description}"
                )
                seen.add(ex.description)
```

### Step 2: Run test to verify count fails

```bash
pytest tests/test_knowledge_expansion.py -v
```

Expected: FAIL — current counts below targets.

### Step 3: Add new examples

实现者需要为每种类型添加新的 TaggedExample。每个示例必须：
1. 有独特的描述（零件规格 + 特征）
2. 有完整的 CadQuery 代码（import + 参数 + 建模 + export）
3. 有准确的 features frozenset（用于 Jaccard 匹配）
4. 代码遵循建模策略（`modeling_strategies.py`）

**新增示例清单（参考）：**

ROTATIONAL (+4):
- 带键槽的法兰盘（revolve + bore + keyway + hole_pattern）
- 薄壁法兰（revolve + bore + fillet，壁厚 < 5mm）
- 圆柱滚子（revolve，无孔，简单）
- 带螺纹孔的端盖（revolve + bore + hole_pattern + chamfer）

PLATE (+2):
- 带沉头孔的安装板（extrude + counterbore + fillet）
- L形切角板（polyline + extrude + hole_pattern）

BRACKET (+3):
- 带加强筋的 L 型支架（extrude + union + rib + fillet）
- 三角支撑架（polyline + extrude + hole_pattern）
- 角钢支架（extrude + union + chamfer）

HOUSING (+2):
- 带安装耳的壳体（extrude + shell + lug + hole_pattern）
- 圆柱壳体带法兰（revolve + shell + hole_pattern）

GENERAL (+2):
- 六角螺母（polygon_extrude + bore）
- T 形块（extrude + union + fillet）

### Step 4: Run tests

```bash
pytest tests/test_knowledge_expansion.py -v
```

Expected: ALL PASS.

### Step 5: Run full suite

```bash
pytest tests/ -v
```

### Step 6: Commit

```bash
git add backend/knowledge/examples/ tests/test_knowledge_expansion.py
git commit -m "feat: expand knowledge base to 36+ examples (Phase 3 Task 3.8)"
```

---

## Task 7: 向量检索增强示例匹配（对应 OpenSpec T3.7）

**Files:**
- Create: `backend/infra/embedding.py`
- Modify: `backend/core/modeling_strategist.py`
- Test: `tests/test_vector_retrieval.py`

**设计决策：** 使用轻量方案替代 pgvector：
- Embedding：sentence-transformers 本地模型（或 OpenAI text-embedding-3-small API）
- 存储：内存 numpy 数组 + JSON 缓存文件
- 检索：cosine similarity（numpy）
- Fallback：保留 Jaccard 当 embedding 不可用时

### Step 1: Write the failing tests

```python
# tests/test_vector_retrieval.py
"""Tests for vector-based example retrieval."""

from __future__ import annotations

import numpy as np
import pytest

from backend.knowledge.part_types import BaseBodySpec, DrawingSpec, PartType


class TestEmbeddingStore:
    def test_store_and_retrieve(self) -> None:
        from backend.infra.embedding import EmbeddingStore

        store = EmbeddingStore()
        store.add("item1", np.array([1.0, 0.0, 0.0]), metadata={"type": "rotational"})
        store.add("item2", np.array([0.0, 1.0, 0.0]), metadata={"type": "plate"})

        results = store.find_similar(np.array([0.9, 0.1, 0.0]), top_k=1)
        assert len(results) == 1
        assert results[0].key == "item1"

    def test_find_similar_top_k(self) -> None:
        from backend.infra.embedding import EmbeddingStore

        store = EmbeddingStore()
        for i in range(10):
            vec = np.zeros(3)
            vec[i % 3] = 1.0
            store.add(f"item{i}", vec)

        results = store.find_similar(np.array([1.0, 0.0, 0.0]), top_k=3)
        assert len(results) == 3

    def test_empty_store(self) -> None:
        from backend.infra.embedding import EmbeddingStore

        store = EmbeddingStore()
        results = store.find_similar(np.array([1.0, 0.0]), top_k=5)
        assert results == []

    def test_filter_by_metadata(self) -> None:
        from backend.infra.embedding import EmbeddingStore

        store = EmbeddingStore()
        store.add("a", np.array([1.0, 0.0]), metadata={"type": "rotational"})
        store.add("b", np.array([0.9, 0.1]), metadata={"type": "plate"})
        store.add("c", np.array([0.8, 0.2]), metadata={"type": "rotational"})

        results = store.find_similar(
            np.array([1.0, 0.0]),
            top_k=5,
            filter_metadata={"type": "rotational"},
        )
        assert all(r.metadata.get("type") == "rotational" for r in results)


class TestSpecToText:
    def test_spec_to_embedding_text(self) -> None:
        from backend.infra.embedding import spec_to_embedding_text

        spec = DrawingSpec(
            part_type=PartType.ROTATIONAL,
            description="法兰盘",
            base_body=BaseBodySpec(method="revolve"),
        )
        text = spec_to_embedding_text(spec)
        assert "rotational" in text.lower()
        assert "法兰盘" in text
        assert "revolve" in text


class TestStrategistWithVector:
    def test_vector_fallback_to_jaccard(self) -> None:
        """When embedding is unavailable, falls back to Jaccard."""
        from backend.core.modeling_strategist import ModelingStrategist

        strategist = ModelingStrategist()
        spec = DrawingSpec(
            part_type=PartType.ROTATIONAL,
            description="法兰盘",
            base_body=BaseBodySpec(method="revolve"),
        )
        ctx = strategist.select(spec, max_examples=3)
        assert len(ctx.examples) <= 3
        # Should still work via Jaccard fallback
        assert ctx.strategy != ""
```

### Step 2: Run tests to verify they fail

```bash
pytest tests/test_vector_retrieval.py -v
```

Expected: FAIL — `backend.infra.embedding` does not exist.

### Step 3: Implement EmbeddingStore

Create `backend/infra/embedding.py`:

```python
"""Lightweight embedding store for vector-based example retrieval.

Uses numpy cosine similarity for in-memory search.
No database dependency — vectors stored as numpy arrays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from backend.knowledge.part_types import DrawingSpec


@dataclass
class SearchResult:
    key: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class EmbeddingStore:
    """In-memory vector store with cosine similarity search."""

    def __init__(self) -> None:
        self._keys: list[str] = []
        self._vectors: list[np.ndarray] = []
        self._metadata: list[dict[str, Any]] = []

    def add(
        self,
        key: str,
        vector: np.ndarray,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self._keys.append(key)
        self._vectors.append(vector / (np.linalg.norm(vector) + 1e-10))
        self._metadata.append(metadata or {})

    def find_similar(
        self,
        query: np.ndarray,
        top_k: int = 5,
        filter_metadata: Optional[dict[str, Any]] = None,
    ) -> list[SearchResult]:
        if not self._vectors:
            return []

        q_norm = query / (np.linalg.norm(query) + 1e-10)
        matrix = np.stack(self._vectors)
        scores = matrix @ q_norm

        results: list[SearchResult] = []
        for idx in np.argsort(scores)[::-1]:
            meta = self._metadata[idx]
            if filter_metadata:
                if not all(meta.get(k) == v for k, v in filter_metadata.items()):
                    continue
            results.append(SearchResult(
                key=self._keys[idx],
                score=float(scores[idx]),
                metadata=meta,
            ))
            if len(results) >= top_k:
                break
        return results

    def __len__(self) -> int:
        return len(self._keys)


def spec_to_embedding_text(spec: DrawingSpec) -> str:
    """Convert a DrawingSpec to text suitable for embedding."""
    parts = [
        spec.part_type.value,
        spec.description,
        spec.base_body.method,
    ]
    for feat in spec.features:
        parts.append(feat.type)
    return " ".join(parts)
```

### Step 4: Update ModelingStrategist to use vector retrieval with Jaccard fallback

Modify `backend/core/modeling_strategist.py`: add an optional `embedding_store` parameter. When available and populated, use vector similarity for example ranking. Fall back to Jaccard when embedding is unavailable.

```python
class ModelingStrategist:
    def __init__(self, embedding_store: EmbeddingStore | None = None) -> None:
        self._embedding_store = embedding_store

    def select(self, spec: DrawingSpec, max_examples: int = 3) -> ModelingContext:
        strategy = get_strategy(spec.part_type)
        if max_examples <= 0:
            return ModelingContext(drawing_spec=spec, strategy=strategy, examples=[])

        # Try vector retrieval first
        if self._embedding_store and len(self._embedding_store) > 0:
            examples = self._select_by_vector(spec, max_examples)
            if examples:
                return ModelingContext(drawing_spec=spec, strategy=strategy, examples=examples)

        # Fallback to Jaccard
        return self._select_by_jaccard(spec, max_examples, strategy)

    def _select_by_jaccard(self, spec, max_examples, strategy):
        # (existing Jaccard logic, extracted from current select())
        ...

    def _select_by_vector(self, spec, max_examples):
        # (new vector logic using embedding_store)
        ...
```

### Step 5: Run tests

```bash
pytest tests/test_vector_retrieval.py -v
pytest tests/ -v
```

Expected: ALL PASS. Existing tests still work (Jaccard fallback).

### Step 6: Commit

```bash
git add backend/infra/embedding.py backend/core/modeling_strategist.py tests/test_vector_retrieval.py
git commit -m "feat: vector retrieval with Jaccard fallback (Phase 3 Task 3.7)"
```

---

## Task 8: 知识库管理前端（对应 OpenSpec T3.6）

**Files:**
- Modify: `frontend/src/pages/Templates/index.tsx`
- Create: `frontend/src/pages/Templates/TemplateList.tsx`
- Create: `frontend/src/pages/Templates/TemplateDetail.tsx`
- Create: `frontend/src/pages/Templates/TemplateEditor.tsx`
- Create: `frontend/src/types/template.ts`
- Modify: `frontend/src/services/api.ts`

**依赖:** Task 5 (API) 必须完成。

### Step 1: Add TypeScript types

Create `frontend/src/types/template.ts`:

```typescript
export interface ParamDefinition {
  name: string;
  display_name: string;
  unit?: string;
  param_type: 'float' | 'int' | 'bool' | 'str';
  range_min?: number;
  range_max?: number;
  default?: number | string | boolean;
  depends_on?: string;
}

export interface ParametricTemplate {
  name: string;
  display_name: string;
  part_type: string;
  description: string;
  params: ParamDefinition[];
  constraints: string[];
  code_template: string;
}

export interface ValidateResponse {
  valid: boolean;
  errors: string[];
}
```

### Step 2: Add API functions

Add to `frontend/src/services/api.ts`:

```typescript
import type { ParametricTemplate, ValidateResponse } from '../types/template';

// Template API
export async function getTemplates(partType?: string): Promise<ParametricTemplate[]> {
  const params = partType ? { part_type: partType } : {};
  const { data } = await api.get<ParametricTemplate[]>('/templates', { params });
  return data;
}

export async function getTemplate(name: string): Promise<ParametricTemplate> {
  const { data } = await api.get<ParametricTemplate>(`/templates/${name}`);
  return data;
}

export async function createTemplate(template: ParametricTemplate): Promise<ParametricTemplate> {
  const { data } = await api.post<ParametricTemplate>('/templates', template);
  return data;
}

export async function updateTemplate(name: string, template: ParametricTemplate): Promise<ParametricTemplate> {
  const { data } = await api.put<ParametricTemplate>(`/templates/${name}`, template);
  return data;
}

export async function deleteTemplate(name: string): Promise<void> {
  await api.delete(`/templates/${name}`);
}

export async function validateTemplateParams(name: string, params: Record<string, unknown>): Promise<ValidateResponse> {
  const { data } = await api.post<ValidateResponse>(`/templates/${name}/validate`, params);
  return data;
}
```

### Step 3: Implement TemplateList component

Create `frontend/src/pages/Templates/TemplateList.tsx`:

```tsx
import { Card, Tag, Input, Select, Row, Col, Empty, Button } from 'antd';
import { PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { useState, useEffect } from 'react';
import type { ParametricTemplate } from '../../types/template';
import { getTemplates } from '../../services/api';

const PART_TYPES = [
  { label: '全部', value: '' },
  { label: '回转体', value: 'rotational' },
  { label: '阶梯回转体', value: 'rotational_stepped' },
  { label: '板件', value: 'plate' },
  { label: '支架', value: 'bracket' },
  { label: '壳体', value: 'housing' },
  { label: '齿轮', value: 'gear' },
  { label: '通用', value: 'general' },
];

interface Props {
  onSelect: (name: string) => void;
  onCreate: () => void;
}

export default function TemplateList({ onSelect, onCreate }: Props) {
  const [templates, setTemplates] = useState<ParametricTemplate[]>([]);
  const [filter, setFilter] = useState('');
  const [search, setSearch] = useState('');

  useEffect(() => {
    getTemplates(filter || undefined).then(setTemplates);
  }, [filter]);

  const filtered = templates.filter(t =>
    !search || t.display_name.includes(search) || t.name.includes(search)
  );

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col flex="auto">
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索模板..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </Col>
        <Col>
          <Select
            options={PART_TYPES}
            value={filter}
            onChange={setFilter}
            style={{ width: 150 }}
          />
        </Col>
        <Col>
          <Button type="primary" icon={<PlusOutlined />} onClick={onCreate}>
            新建模板
          </Button>
        </Col>
      </Row>

      {filtered.length === 0 ? (
        <Empty description="暂无模板" />
      ) : (
        <Row gutter={[16, 16]}>
          {filtered.map(t => (
            <Col key={t.name} xs={24} sm={12} lg={8}>
              <Card
                hoverable
                onClick={() => onSelect(t.name)}
                title={t.display_name}
                extra={<Tag>{t.part_type}</Tag>}
              >
                <p>{t.description}</p>
                <p style={{ color: '#888' }}>
                  {t.params.length} 个参数 · {t.constraints.length} 条约束
                </p>
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
}
```

### Step 4: Implement TemplateDetail component

Create `frontend/src/pages/Templates/TemplateDetail.tsx` — 显示模板详情（参数表 + 代码预览 + 在线验证）。

### Step 5: Implement TemplateEditor component

Create `frontend/src/pages/Templates/TemplateEditor.tsx` — YAML 编辑 + 实时验证。

### Step 6: Update Templates page

Replace `frontend/src/pages/Templates/index.tsx`:

```tsx
import { Typography } from 'antd';
import { useState } from 'react';
import TemplateList from './TemplateList';
import TemplateDetail from './TemplateDetail';
import TemplateEditor from './TemplateEditor';

const { Title } = Typography;

type View = 'list' | 'detail' | 'editor';

export default function Templates() {
  const [view, setView] = useState<View>('list');
  const [selected, setSelected] = useState('');

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>参数化模板库</Title>
      {view === 'list' && (
        <TemplateList
          onSelect={(name) => { setSelected(name); setView('detail'); }}
          onCreate={() => { setSelected(''); setView('editor'); }}
        />
      )}
      {view === 'detail' && (
        <TemplateDetail
          name={selected}
          onBack={() => setView('list')}
          onEdit={() => setView('editor')}
        />
      )}
      {view === 'editor' && (
        <TemplateEditor
          name={selected}
          onBack={() => selected ? setView('detail') : setView('list')}
          onSave={() => setView('list')}
        />
      )}
    </div>
  );
}
```

### Step 7: Build and verify

```bash
cd frontend && npm run build
```

Expected: Build succeeds.

### Step 8: Commit

```bash
git add frontend/src/pages/Templates/ frontend/src/types/template.ts frontend/src/services/api.ts
git commit -m "feat: knowledge base management frontend (Phase 3 Task 3.6)"
```

---

## 执行顺序总结

| 批次 | 任务 | 可并行 |
|------|------|--------|
| Batch 1 | T1 (Feature model), T2 (Template model) | ✅ 并行 |
| Batch 1 | T6 (知识库扩充), T7 (向量检索) | ✅ 并行 |
| Batch 2 | T3 (TemplateEngine) — 依赖 T2 | 串行 |
| Batch 3 | T4 (YAML 模板), T5 (API) — 依赖 T3 | ✅ 并行 |
| Batch 4 | T8 (前端) — 依赖 T5 | 串行 |

**测试验证命令：**
```bash
# 运行全部测试
pytest tests/ -v

# 前端构建
cd frontend && npm run build
```

**总预期新增：**
- ~8 个新文件
- ~13 个 YAML 模板
- ~13 个新 TaggedExample
- ~100+ 新测试
