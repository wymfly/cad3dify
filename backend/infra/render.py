from __future__ import annotations

import logging
import os
import tempfile

import cadquery as cq
from cadquery import exporters
from reportlab.graphics import renderPM
from svglib.svglib import svg2rlg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Standard views with CadQuery SVG export projection directions
# ---------------------------------------------------------------------------

STANDARD_VIEWS: dict[str, dict] = {
    "front": {"direction": (0, -1, 0)},      # looking from front
    "top": {"direction": (0, 0, 1)},          # looking from top
    "side": {"direction": (1, 0, 0)},         # looking from right side
    "isometric": {"direction": (1, -1, 1)},   # isometric view
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_and_export_image(cat_filepath: str, output_filepath: str) -> None:
    """Render a CAD file and export it as a PNG file.

    Args:
        cat_filepath: Path to the CAD file (STEP format).
        output_filepath: Path to the output PNG file.
    """
    cad = cq.importers.importStep(cat_filepath)
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=True) as f:
        exporters.export(cad, f.name)
        drawing = svg2rlg(f.name)

    renderPM.drawToFile(drawing, output_filepath, fmt="PNG")


def render_multi_view(
    step_filepath: str,
    output_dir: str,
    views: list[str] | None = None,
) -> dict[str, str]:
    """Render STEP file from multiple standard viewpoints.

    Args:
        step_filepath: Path to input STEP file.
        output_dir: Directory to save rendered images.
        views: List of view names to render. None = all standard views.

    Returns:
        Dict mapping view name to output file path.

    Raises:
        ValueError: If any requested view name is not in STANDARD_VIEWS.
    """
    # Determine which views to render
    if views is None:
        requested_views = list(STANDARD_VIEWS.keys())
    else:
        unknown = [v for v in views if v not in STANDARD_VIEWS]
        if unknown:
            raise ValueError(
                f"Unknown view(s): {unknown}. "
                f"Available: {list(STANDARD_VIEWS.keys())}"
            )
        requested_views = views

    # Load STEP file once
    cad = cq.importers.importStep(step_filepath)

    os.makedirs(output_dir, exist_ok=True)

    result: dict[str, str] = {}

    for view_name in requested_views:
        params = STANDARD_VIEWS[view_name]
        direction = params["direction"]

        svg_path = os.path.join(output_dir, f"{view_name}.svg")
        png_path = os.path.join(output_dir, f"{view_name}.png")

        # Export SVG with projection direction
        exporters.export(
            cad,
            svg_path,
            exportType=exporters.ExportTypes.SVG,
            opt={"projectionDir": direction},
        )

        # Attempt SVG → PNG conversion; fall back to SVG if unavailable
        try:
            drawing = svg2rlg(svg_path)
            renderPM.drawToFile(drawing, png_path, fmt="PNG")
            if os.path.exists(png_path):
                result[view_name] = png_path
            else:
                # Conversion ran but produced no file (e.g. stubbed deps)
                result[view_name] = svg_path
        except Exception:
            logger.debug(
                "SVG→PNG conversion failed for view '%s', using SVG fallback",
                view_name,
            )
            result[view_name] = svg_path

    return result
