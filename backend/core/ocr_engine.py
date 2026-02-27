"""PaddleOCR engine wrapper, adapting to ocr_fn: Callable interface.

Provides ``get_ocr_fn()`` which returns a callable matching the
``Callable[[bytes], list[OCRResult]]`` interface expected by
``backend.core.ocr_assist``.

When PaddleOCR is not installed, the returned function produces an
empty list (graceful degradation).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_paddle_ocr: Optional[Any] = None


def _bbox_from_polygon(polygon: list[list[float]]) -> tuple[int, int, int, int]:
    """Convert PaddleOCR polygon [[x,y],...] to (x1, y1, x2, y2) bbox."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))


def get_ocr_fn() -> Callable[[bytes], list[Any]]:
    """Return OCR function matching ``Callable[[bytes], list[OCRResult]]``.

    Returns empty-list function if PaddleOCR is not available.
    """

    def _ocr_unavailable(image_bytes: bytes) -> list[Any]:
        return []

    try:
        from paddleocr import PaddleOCR  # type: ignore[import-untyped]
    except ImportError:
        logger.info("PaddleOCR not available, OCR disabled")
        return _ocr_unavailable

    global _paddle_ocr
    if _paddle_ocr is None:
        _paddle_ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

    def _paddle_ocr_fn(image_bytes: bytes) -> list[Any]:
        import tempfile
        from pathlib import Path

        from backend.core.ocr_assist import OCRResult

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(image_bytes)
            tmp_path = f.name
        try:
            result = _paddle_ocr.ocr(tmp_path, cls=True)  # type: ignore[union-attr]
            if not result or not result[0]:
                return []
            return [
                OCRResult(
                    text=line[1][0],
                    confidence=line[1][1],
                    bbox=_bbox_from_polygon(line[0]),
                )
                for line in result[0]
            ]
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return _paddle_ocr_fn
