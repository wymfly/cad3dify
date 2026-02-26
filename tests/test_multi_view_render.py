"""Tests for multi-view rendering."""
from __future__ import annotations

import pytest
from pathlib import Path


class TestMultiViewConfig:
    """Test that standard view definitions are correct."""

    def test_standard_views_defined(self) -> None:
        from backend.infra.render import STANDARD_VIEWS

        assert len(STANDARD_VIEWS) == 4
        assert "front" in STANDARD_VIEWS
        assert "top" in STANDARD_VIEWS
        assert "side" in STANDARD_VIEWS
        assert "isometric" in STANDARD_VIEWS

    def test_each_view_has_camera_params(self) -> None:
        from backend.infra.render import STANDARD_VIEWS

        for name, params in STANDARD_VIEWS.items():
            assert "direction" in params, f"View '{name}' missing direction"
            assert len(params["direction"]) == 3

    def test_direction_values_are_numeric(self) -> None:
        from backend.infra.render import STANDARD_VIEWS

        for name, params in STANDARD_VIEWS.items():
            for component in params["direction"]:
                assert isinstance(component, (int, float)), (
                    f"View '{name}' direction component {component} is not numeric"
                )


class TestRenderMultiView:
    """Integration tests requiring real CadQuery (not stubbed)."""

    def test_renders_four_views(self, tmp_path: Path) -> None:
        import cadquery as cq

        step_path = str(tmp_path / "test.step")
        result = cq.Workplane("XY").box(100, 50, 30)
        cq.exporters.export(result, step_path)

        from backend.infra.render import render_multi_view

        images = render_multi_view(step_path, str(tmp_path))
        assert len(images) == 4
        for view_name, img_path in images.items():
            assert Path(img_path).exists(), f"View '{view_name}' image not created"

    def test_single_view_filter(self, tmp_path: Path) -> None:
        import cadquery as cq

        step_path = str(tmp_path / "test.step")
        result = cq.Workplane("XY").box(100, 50, 30)
        cq.exporters.export(result, step_path)

        from backend.infra.render import render_multi_view

        images = render_multi_view(step_path, str(tmp_path), views=["front"])
        assert len(images) == 1
        assert "front" in images
        assert Path(images["front"]).exists()

    def test_multiple_view_filter(self, tmp_path: Path) -> None:
        import cadquery as cq

        step_path = str(tmp_path / "test.step")
        result = cq.Workplane("XY").box(80, 40, 20)
        cq.exporters.export(result, step_path)

        from backend.infra.render import render_multi_view

        images = render_multi_view(step_path, str(tmp_path), views=["front", "top"])
        assert len(images) == 2
        assert "front" in images
        assert "top" in images

    def test_invalid_view_name_raises(self, tmp_path: Path) -> None:
        import cadquery as cq

        step_path = str(tmp_path / "test.step")
        result = cq.Workplane("XY").box(50, 50, 50)
        cq.exporters.export(result, step_path)

        from backend.infra.render import render_multi_view

        with pytest.raises(ValueError, match="Unknown view"):
            render_multi_view(step_path, str(tmp_path), views=["nonexistent"])

    def test_output_files_are_nonempty(self, tmp_path: Path) -> None:
        import cadquery as cq

        step_path = str(tmp_path / "test.step")
        result = cq.Workplane("XY").box(100, 50, 30)
        cq.exporters.export(result, step_path)

        from backend.infra.render import render_multi_view

        images = render_multi_view(step_path, str(tmp_path))
        for view_name, img_path in images.items():
            size = Path(img_path).stat().st_size
            assert size > 0, f"View '{view_name}' file is empty"
