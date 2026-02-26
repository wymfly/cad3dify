"""Tests for PipelineConfig model, presets, and tooltips."""

from __future__ import annotations


def test_pipeline_config_default_is_balanced():
    from backend.models.pipeline_config import PipelineConfig

    config = PipelineConfig()
    assert config.preset == "balanced"


def test_pipeline_config_fast_preset():
    from backend.models.pipeline_config import PRESETS

    fast = PRESETS["fast"]
    assert fast.best_of_n == 1
    assert fast.rag_enabled is False


def test_pipeline_config_precise_preset():
    from backend.models.pipeline_config import PRESETS

    precise = PRESETS["precise"]
    assert precise.best_of_n == 5
    assert precise.ocr_assist is True
    assert precise.multi_model_voting is True


def test_pipeline_config_balanced_preset():
    from backend.models.pipeline_config import PRESETS

    balanced = PRESETS["balanced"]
    assert balanced.best_of_n == 3
    assert balanced.rag_enabled is True
    assert balanced.volume_check is True


def test_tooltip_spec_fields():
    from backend.models.pipeline_config import TooltipSpec

    tip = TooltipSpec(
        title="多路生成",
        description="生成 N 份候选代码并择优",
        when_to_use="复杂零件推荐",
        cost="耗时 ×N",
        default="balanced: N=3",
    )
    assert tip.title == "多路生成"
    assert tip.cost == "耗时 ×N"


def test_get_tooltips_returns_all_fields():
    from backend.models.pipeline_config import get_tooltips

    tooltips = get_tooltips()
    assert "best_of_n" in tooltips
    assert "rag_enabled" in tooltips
    assert "ocr_assist" in tooltips
    assert tooltips["best_of_n"].title != ""


def test_presets_has_three_entries():
    from backend.models.pipeline_config import PRESETS

    assert len(PRESETS) == 3
    assert set(PRESETS.keys()) == {"fast", "balanced", "precise"}
