"""TPMSStrategy -- Triply Periodic Minimal Surface lattice generation.

Generates TPMS (Gyroid/Schwarz-P/Diamond) scalar fields, extracts
iso-surfaces via marching cubes, and intersects with the input mesh
using boolean operations.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import trimesh

from backend.graph.descriptor import NodeStrategy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TPMS scalar field functions
# ---------------------------------------------------------------------------


def gyroid_field(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    cell_size: float,
) -> np.ndarray:
    """Gyroid: sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x)."""
    k = 2 * np.pi / cell_size
    return (
        np.sin(k * x) * np.cos(k * y)
        + np.sin(k * y) * np.cos(k * z)
        + np.sin(k * z) * np.cos(k * x)
    )


def schwarz_p_field(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    cell_size: float,
) -> np.ndarray:
    """Schwarz-P: cos(x) + cos(y) + cos(z)."""
    k = 2 * np.pi / cell_size
    return np.cos(k * x) + np.cos(k * y) + np.cos(k * z)


def diamond_field(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    cell_size: float,
) -> np.ndarray:
    """Diamond (Schwarz-D)."""
    k = 2 * np.pi / cell_size
    sx, sy, sz = np.sin(k * x), np.sin(k * y), np.sin(k * z)
    cx, cy, cz = np.cos(k * x), np.cos(k * y), np.cos(k * z)
    return sx * sy * sz + sx * cy * cz + cx * sy * cz + cx * cy * sz


_TPMS_FIELDS = {
    "gyroid": gyroid_field,
    "schwarz_p": schwarz_p_field,
    "diamond": diamond_field,
}


# ---------------------------------------------------------------------------
# TPMSStrategy
# ---------------------------------------------------------------------------


class TPMSStrategy(NodeStrategy):
    """TPMS lattice generation via marching cubes + boolean intersection."""

    def check_available(self) -> bool:
        """Check if skimage (scikit-image) is importable."""
        try:
            from skimage.measure import marching_cubes  # noqa: F401

            return True
        except ImportError:
            return False

    def generate_lattice(
        self,
        bbox_min: np.ndarray,
        bbox_max: np.ndarray,
    ) -> trimesh.Trimesh:
        """Generate a TPMS lattice mesh within the given bounding box."""
        from skimage.measure import marching_cubes

        config = self.config
        field_fn = _TPMS_FIELDS[config.lattice_type]
        resolution = config.resolution

        x = np.linspace(float(bbox_min[0]), float(bbox_max[0]), resolution)
        y = np.linspace(float(bbox_min[1]), float(bbox_max[1]), resolution)
        z = np.linspace(float(bbox_min[2]), float(bbox_max[2]), resolution)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        raw_field = field_fn(X, Y, Z, config.cell_size)

        # abs-field band approach for solid wall thickness
        abs_field = np.abs(raw_field)
        field_range = float(np.max(abs_field))
        if field_range < 1e-6:
            field_range = 1.0
        level = config.wall_thickness / config.cell_size * field_range

        spacing = (
            (bbox_max[0] - bbox_min[0]) / (resolution - 1),
            (bbox_max[1] - bbox_min[1]) / (resolution - 1),
            (bbox_max[2] - bbox_min[2]) / (resolution - 1),
        )

        verts, faces, _, _ = marching_cubes(abs_field, level=level, spacing=spacing)
        verts += bbox_min

        return trimesh.Trimesh(vertices=verts, faces=faces)

    def apply_to_mesh(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Apply TPMS lattice to mesh interior via boolean intersection."""
        bbox_min = mesh.bounds[0]
        bbox_max = mesh.bounds[1]

        lattice = self.generate_lattice(bbox_min, bbox_max)

        try:
            result = mesh.intersection(lattice)
            if isinstance(result, trimesh.Trimesh) and len(result.faces) > 0:
                return result
        except Exception as exc:
            logger.warning("Boolean intersection failed: %s, returning original", exc)

        return mesh

    async def execute(self, ctx: Any) -> None:
        """Execute TPMS lattice application."""
        import asyncio
        import tempfile
        from pathlib import Path

        asset = ctx.get_asset("final_mesh")
        mesh = await asyncio.to_thread(trimesh.load, asset.path, force="mesh")

        await ctx.dispatch_progress(1, 4, f"生成 {self.config.lattice_type} 晶格")

        result = await asyncio.to_thread(self.apply_to_mesh, mesh)

        await ctx.dispatch_progress(3, 4, "导出晶格化网格")

        output_dir = Path(tempfile.gettempdir()) / "cadpilot" / "lattice"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"{ctx.job_id}_lattice.glb")
        await asyncio.to_thread(result.export, output_path)

        ctx.put_asset(
            "lattice_mesh",
            output_path,
            "mesh",
            metadata={
                "lattice_type": self.config.lattice_type,
                "cell_size": self.config.cell_size,
                "original_volume": round(float(mesh.volume), 2),
                "lattice_volume": round(float(result.volume), 2),
                "volume_reduction": round(
                    1 - float(result.volume) / max(float(mesh.volume), 1e-6),
                    4,
                ),
            },
        )

        await ctx.dispatch_progress(4, 4, "晶格填充完成")
