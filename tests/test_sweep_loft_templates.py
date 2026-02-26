"""Tests for sweep/loft/compound boolean templates."""
import pytest
from pathlib import Path

from backend.core.template_engine import TemplateEngine


TEMPLATES_DIR = Path(__file__).parent.parent / "backend" / "knowledge" / "templates"


@pytest.fixture
def engine():
    return TemplateEngine.from_directory(TEMPLATES_DIR)


class TestPipeBendTemplate:
    def test_loads(self, engine):
        matches = engine.find_matches("general")
        names = [t.name for t in matches]
        assert "general_pipe_bend" in names

    def test_default_valid(self, engine):
        errors = engine.validate("general_pipe_bend", {})
        assert errors == []

    def test_renders_sweep(self, engine):
        code = engine.render("general_pipe_bend", {}, "out.step")
        assert "sweep" in code
        assert "import cadquery" in code

    def test_wall_thickness_constraint(self, engine):
        errors = engine.validate(
            "general_pipe_bend",
            {"outer_diameter": 30, "wall_thickness": 20},
        )
        assert len(errors) > 0

    def test_bend_radius_constraint(self, engine):
        errors = engine.validate(
            "general_pipe_bend",
            {"outer_diameter": 30, "bend_radius": 10},
        )
        assert len(errors) > 0


class TestLoftTransitionTemplate:
    def test_loads(self, engine):
        matches = engine.find_matches("general")
        names = [t.name for t in matches]
        assert "general_loft_transition" in names

    def test_default_valid(self, engine):
        errors = engine.validate("general_loft_transition", {})
        assert errors == []

    def test_renders_loft(self, engine):
        code = engine.render("general_loft_transition", {}, "out.step")
        assert "loft" in code

    def test_solid_version(self, engine):
        code = engine.render(
            "general_loft_transition",
            {"wall_thickness": 0},
            "out.step",
        )
        assert "shell" not in code

    def test_hollow_version(self, engine):
        code = engine.render(
            "general_loft_transition",
            {"wall_thickness": 3},
            "out.step",
        )
        assert "shell" in code


class TestCompoundBooleanTemplate:
    def test_loads(self, engine):
        matches = engine.find_matches("general")
        names = [t.name for t in matches]
        assert "general_compound_boolean" in names

    def test_default_valid(self, engine):
        errors = engine.validate("general_compound_boolean", {})
        assert errors == []

    def test_renders_boolean_ops(self, engine):
        code = engine.render("general_compound_boolean", {}, "out.step")
        assert "union" in code
        assert "cutThruAll" in code or "cutBlind" in code

    def test_boss_diameter_constraint(self, engine):
        errors = engine.validate(
            "general_compound_boolean",
            {"base_width": 50, "boss_diameter": 60},
        )
        assert len(errors) > 0

    def test_hole_vs_boss_constraint(self, engine):
        errors = engine.validate(
            "general_compound_boolean",
            {"boss_diameter": 20, "hole_diameter": 25},
        )
        assert len(errors) > 0
