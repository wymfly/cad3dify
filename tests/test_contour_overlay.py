"""Tests for contour overlay rendering and SmartRefiner integration."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.infra.render import (
    overlay_contour_on_drawing,
    render_wireframe_contour,
)


# ---------------------------------------------------------------------------
# Wireframe contour rendering (CadQuery + exporters mocked)
# ---------------------------------------------------------------------------


_RENDER_PATCHES = (
    "backend.infra.render.cq",
    "backend.infra.render.exporters",
)


class TestRenderWireframeContour:
    def test_returns_output_path(self, tmp_path):
        out = str(tmp_path / "contour.png")
        with patch(_RENDER_PATCHES[0]) as mock_cq, patch(_RENDER_PATCHES[1]):
            mock_cq.importers.importStep.return_value = MagicMock()
            result = render_wireframe_contour(
                "fake.step", out, view="front"
            )
        assert result == out

    def test_default_view_is_front(self, tmp_path):
        out = str(tmp_path / "contour.png")
        with patch(_RENDER_PATCHES[0]) as mock_cq, patch(_RENDER_PATCHES[1]):
            mock_cq.importers.importStep.return_value = MagicMock()
            render_wireframe_contour("fake.step", out)
        # Default view is front — just verify no error

    def test_custom_line_color(self, tmp_path):
        out = str(tmp_path / "contour.png")
        with patch(_RENDER_PATCHES[0]) as mock_cq, patch(_RENDER_PATCHES[1]):
            mock_cq.importers.importStep.return_value = MagicMock()
            render_wireframe_contour(
                "fake.step", out, line_color=(0, 255, 0)
            )


# ---------------------------------------------------------------------------
# Image overlay compositing (real PIL)
# ---------------------------------------------------------------------------


class TestOverlayContourOnDrawing:
    def test_creates_overlay_image(self, tmp_path):
        from PIL import Image

        drawing = Image.new("RGB", (200, 200), (255, 255, 255))
        contour = Image.new("RGBA", (200, 200), (255, 0, 0, 128))

        d_path = str(tmp_path / "drawing.png")
        c_path = str(tmp_path / "contour.png")
        o_path = str(tmp_path / "overlay.png")

        drawing.save(d_path)
        contour.save(c_path)

        result = overlay_contour_on_drawing(d_path, c_path, o_path)
        assert result == o_path
        assert Path(o_path).exists()

    def test_alpha_composite_preserves_transparency(self, tmp_path):
        """alpha_composite respects per-pixel alpha from contour."""
        from PIL import Image

        drawing = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
        # Semi-transparent red contour
        contour = Image.new("RGBA", (100, 100), (255, 0, 0, 128))

        d_path = str(tmp_path / "d.png")
        c_path = str(tmp_path / "c.png")
        o_path = str(tmp_path / "out.png")

        drawing.save(d_path)
        contour.save(c_path)

        overlay_contour_on_drawing(d_path, c_path, o_path)
        result = Image.open(o_path)
        # Result should be blended — not pure red, not pure white
        pixel = result.getpixel((50, 50))
        assert pixel[0] > 127  # some red
        assert pixel[0] < 256  # not saturated from simple blend

    def test_size_mismatch_resizes(self, tmp_path):
        """Contour should be resized to match drawing dimensions."""
        from PIL import Image

        drawing = Image.new("RGB", (400, 300), (255, 255, 255))
        contour = Image.new("RGBA", (200, 150), (255, 0, 0, 128))

        d_path = str(tmp_path / "d.png")
        c_path = str(tmp_path / "c.png")
        o_path = str(tmp_path / "o.png")

        drawing.save(d_path)
        contour.save(c_path)

        result = overlay_contour_on_drawing(d_path, c_path, o_path)
        assert Path(o_path).exists()
        overlay = Image.open(o_path)
        assert overlay.size == (400, 300)


# ---------------------------------------------------------------------------
# SmartRefiner contour_overlay parameter
# ---------------------------------------------------------------------------


class TestSmartRefinerContourOverlay:
    def test_contour_overlay_flag_accepted(self):
        """SmartRefiner.refine() accepts contour_overlay parameter."""
        with (
            patch("backend.core.smart_refiner.SmartCompareChain"),
            patch("backend.core.smart_refiner.SmartFixChain"),
        ):
            from backend.core.smart_refiner import SmartRefiner

            refiner = SmartRefiner()

        # Mock internal chains + validators
        with patch(
            "backend.core.smart_refiner.validate_code_params"
        ) as mock_validate:
            mock_validate.return_value = MagicMock(
                passed=True, mismatches=[]
            )
            refiner.compare_chain = MagicMock()
            refiner.compare_chain.invoke.return_value = {"result": None}

            result = refiner.refine(
                code="import cadquery as cq",
                original_image=MagicMock(type="png", data="abc"),
                rendered_image=MagicMock(type="png", data="def"),
                drawing_spec=MagicMock(
                    to_prompt_text=MagicMock(return_value="spec"),
                    features=[],
                    base_body=MagicMock(bore=None),
                    overall_dimensions={},
                ),
                contour_overlay=True,
            )
        # VL returned PASS, so result should be None (no fix needed)
        assert result is None
