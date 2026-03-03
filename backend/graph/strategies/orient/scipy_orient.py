"""ScipyOrientStrategy — continuous orientation optimization.

Uses scipy.optimize.differential_evolution to search SO(3) rotation space,
parameterized as Euler angles (alpha, beta, gamma).
Reuses BasicOrientStrategy.evaluate_orientation() as the objective function.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import trimesh
from scipy.optimize import differential_evolution
from scipy.spatial.transform import Rotation

from backend.graph.descriptor import NodeStrategy
from backend.graph.strategies.orient.basic import BasicOrientStrategy

logger = logging.getLogger(__name__)


class ScipyOrientStrategy(NodeStrategy):
    """Continuous orientation optimization via differential evolution."""

    def check_available(self) -> bool:
        """Check if scipy is importable."""
        try:
            import scipy.optimize  # noqa: F401

            return True
        except ImportError:
            return False

    def optimize(self, mesh: trimesh.Trimesh) -> tuple[np.ndarray, float]:
        """Find optimal orientation via continuous optimization.

        Returns: (4x4 rotation matrix, best score)
        """
        # Reuse basic strategy's scoring function
        basic = BasicOrientStrategy(config=self.config)

        def objective(angles: np.ndarray) -> float:
            alpha, beta, gamma = angles
            rot = Rotation.from_euler("xyz", [alpha, beta, gamma], degrees=True)
            transform = np.eye(4)
            transform[:3, :3] = rot.as_matrix()
            return basic.evaluate_orientation(mesh, transform)

        # Search over Euler angles
        bounds = [(-180, 180), (-90, 90), (-180, 180)]
        result = differential_evolution(
            objective,
            bounds=bounds,
            maxiter=self.config.scipy_max_iter,
            popsize=self.config.scipy_popsize,
            seed=42,
            tol=1e-4,
        )

        best_angles = result.x
        rot = Rotation.from_euler("xyz", best_angles, degrees=True)
        best_rotation = np.eye(4)
        best_rotation[:3, :3] = rot.as_matrix()

        return best_rotation, float(result.fun)

    async def execute(self, ctx: Any) -> None:
        """Execute scipy orientation optimization."""
        import asyncio

        asset = ctx.get_asset("final_mesh")
        mesh = await asyncio.to_thread(trimesh.load, asset.path, force="mesh")

        await ctx.dispatch_progress(1, 3, "Scipy 方向优化中")

        best_rotation, best_score = await asyncio.to_thread(self.optimize, mesh)

        await ctx.dispatch_progress(2, 3, "应用最优方向")

        mesh.apply_transform(best_rotation)
        z_offset = -mesh.bounds[0][2]
        if abs(z_offset) > 1e-6:
            mesh.apply_translation([0, 0, z_offset])

        import tempfile
        from pathlib import Path

        output_dir = Path(tempfile.gettempdir()) / "cadpilot" / "orient"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"{ctx.job_id}_oriented.glb")
        await asyncio.to_thread(mesh.export, output_path)

        ctx.put_asset(
            "oriented_mesh",
            output_path,
            "mesh",
            metadata={
                "strategy": "scipy",
                "score": round(best_score, 4),
                "rotation_matrix": best_rotation[:3, :3].tolist(),
            },
        )
        ctx.put_data(
            "orientation_result",
            {
                "strategy": "scipy",
                "score": round(best_score, 4),
            },
        )

        await ctx.dispatch_progress(
            3, 3, f"Scipy 方向优化完成 (score={best_score:.2f})"
        )
