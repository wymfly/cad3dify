"""Tests for PaddleOCR engine wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.core.ocr_assist import OCRResult
from backend.core.ocr_engine import _bbox_from_polygon, get_ocr_fn


class TestBboxFromPolygon:
    def test_rectangle(self) -> None:
        poly = [[10.0, 20.0], [100.0, 20.0], [100.0, 50.0], [10.0, 50.0]]
        assert _bbox_from_polygon(poly) == (10, 20, 100, 50)

    def test_float_rounding(self) -> None:
        poly = [[10.5, 20.9], [99.1, 20.9], [99.1, 49.7], [10.5, 49.7]]
        assert _bbox_from_polygon(poly) == (10, 20, 99, 49)

    def test_rotated_polygon(self) -> None:
        """Polygon corners not in standard order — should still give correct bbox."""
        poly = [[50.0, 10.0], [100.0, 50.0], [50.0, 90.0], [0.0, 50.0]]
        assert _bbox_from_polygon(poly) == (0, 10, 100, 90)


class TestGetOcrFn:
    def test_returns_empty_when_unavailable(self) -> None:
        """When PaddleOCR import fails, returned fn should produce []."""
        with patch.dict("sys.modules", {"paddleocr": None}):
            import importlib

            import backend.core.ocr_engine as mod

            # Reset global state
            mod._paddle_ocr = None
            importlib.reload(mod)
            fn = mod.get_ocr_fn()
            assert fn(b"fake image") == []

    def test_ocr_fn_returns_list_on_success(self) -> None:
        """When PaddleOCR is mocked, returned fn should produce OCRResult list."""
        # Create mock PaddleOCR class
        mock_paddle_instance = MagicMock()
        mock_paddle_instance.ocr.return_value = [
            [
                [
                    [[10.0, 20.0], [100.0, 20.0], [100.0, 40.0], [10.0, 40.0]],
                    ("Ø50", 0.95),
                ],
                [
                    [[10.0, 60.0], [100.0, 60.0], [100.0, 80.0], [10.0, 80.0]],
                    ("30mm", 0.88),
                ],
            ]
        ]
        mock_paddle_cls = MagicMock(return_value=mock_paddle_instance)

        mock_module = MagicMock()
        mock_module.PaddleOCR = mock_paddle_cls

        import backend.core.ocr_engine as mod

        mod._paddle_ocr = None

        with patch.dict("sys.modules", {"paddleocr": mock_module}):
            import importlib

            importlib.reload(mod)
            fn = mod.get_ocr_fn()

        result = fn(b"fake image bytes")
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], OCRResult)
        assert result[0].text == "Ø50"
        assert result[0].confidence == 0.95
        assert result[0].bbox == (10, 20, 100, 40)
        assert result[1].text == "30mm"

    def test_ocr_fn_empty_result(self) -> None:
        """When PaddleOCR returns empty result, fn should return []."""
        mock_paddle_instance = MagicMock()
        mock_paddle_instance.ocr.return_value = [None]
        mock_paddle_cls = MagicMock(return_value=mock_paddle_instance)

        mock_module = MagicMock()
        mock_module.PaddleOCR = mock_paddle_cls

        import backend.core.ocr_engine as mod

        mod._paddle_ocr = None

        with patch.dict("sys.modules", {"paddleocr": mock_module}):
            import importlib

            importlib.reload(mod)
            fn = mod.get_ocr_fn()

        assert fn(b"empty image") == []

    def test_ocr_fn_cleans_temp_file(self) -> None:
        """Temp file should be cleaned up after OCR."""
        from pathlib import Path

        mock_paddle_instance = MagicMock()
        mock_paddle_instance.ocr.return_value = [[]]
        mock_paddle_cls = MagicMock(return_value=mock_paddle_instance)

        mock_module = MagicMock()
        mock_module.PaddleOCR = mock_paddle_cls

        import backend.core.ocr_engine as mod

        mod._paddle_ocr = None

        with patch.dict("sys.modules", {"paddleocr": mock_module}):
            import importlib

            importlib.reload(mod)
            fn = mod.get_ocr_fn()

        fn(b"test bytes")

        # Check the temp file was passed to ocr and then cleaned up
        call_args = mock_paddle_instance.ocr.call_args
        tmp_path = call_args[0][0]
        assert not Path(tmp_path).exists()
