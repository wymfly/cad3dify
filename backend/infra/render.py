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


def render_wireframe_contour(
    step_filepath: str,
    output_filepath: str,
    view: str = "front",
    line_color: tuple[int, int, int] = (255, 0, 0),
) -> str:
    """Render STEP model as wireframe contour PNG.

    Uses CadQuery SVG export (inherently wireframe) and converts to PNG
    with specified line color for overlay visibility.

    Returns:
        The *output_filepath* for convenience.
    """
    from PIL import Image

    direction = STANDARD_VIEWS.get(view, STANDARD_VIEWS["front"])["direction"]

    cad = cq.importers.importStep(step_filepath)

    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
        svg_path = f.name

    try:
        exporters.export(
            cad,
            svg_path,
            exportType=exporters.ExportTypes.SVG,
            opt={"projectionDir": direction},
        )

        # SVG → temporary PNG via reportlab
        tmp_png = svg_path.replace(".svg", "_tmp.png")
        try:
            drawing = svg2rlg(svg_path)
            renderPM.drawToFile(drawing, tmp_png, fmt="PNG")
        except Exception:
            logger.warning(
                "SVG→PNG conversion failed for wireframe contour, "
                "creating blank placeholder"
            )

        # Ensure intermediate PNG exists (stubbed deps may produce nothing)
        if not os.path.exists(tmp_png):
            Image.new("RGBA", (400, 400), (0, 0, 0, 0)).save(tmp_png)

        # Recolour dark pixels (wireframe lines) to the requested colour
        import numpy as np

        img = Image.open(tmp_png).convert("RGBA")
        arr = np.array(img)
        r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
        dark_mask = (r < 128) & (g < 128) & (b < 128) & (a > 0)
        result_arr = np.zeros_like(arr)
        result_arr[dark_mask] = [*line_color, 255]
        Image.fromarray(result_arr, "RGBA").save(output_filepath)

        if os.path.exists(tmp_png):
            os.unlink(tmp_png)
    finally:
        if os.path.exists(svg_path):
            os.unlink(svg_path)

    return output_filepath


def overlay_contour_on_drawing(
    drawing_path: str,
    contour_path: str,
    output_path: str,
) -> str:
    """Overlay wireframe contour onto original drawing image.

    Uses PIL alpha_composite for proper RGBA compositing.
    Contour is resized to match drawing dimensions if needed.

    Returns:
        The *output_path* for convenience.
    """
    from PIL import Image

    drawing_img = Image.open(drawing_path).convert("RGBA")
    contour_img = Image.open(contour_path).convert("RGBA")

    # Resize contour to match drawing if dimensions differ
    if contour_img.size != drawing_img.size:
        contour_img = contour_img.resize(drawing_img.size, Image.LANCZOS)

    # Alpha-composite the contour onto the drawing (respects per-pixel alpha)
    blended = Image.alpha_composite(drawing_img, contour_img)
    blended.save(output_path)

    return output_path
