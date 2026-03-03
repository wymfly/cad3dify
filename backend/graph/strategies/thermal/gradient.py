"""GradientThermalStrategy — layer-by-layer thermal gradient analysis.

Computes cross-section area at each layer height and identifies
thermal gradient hotspots where area changes rapidly.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import trimesh

from backend.graph.descriptor import NodeStrategy

logger = logging.getLogger(__name__)


class GradientThermalStrategy(NodeStrategy):
    """Layer-by-layer cross-section thermal gradient analysis."""

    def analyze(
        self, mesh: trimesh.Trimesh, layer_height: float = 0.2
    ) -> dict[str, Any]:
        """Compute per-layer cross-section areas and thermal gradients."""
        z_min, z_max = mesh.bounds[0][2], mesh.bounds[1][2]
        height = z_max - z_min

        n_layers = max(1, int(height / layer_height))
        step = max(1, n_layers // 200)
        sample_heights = [z_min + (i * layer_height) for i in range(0, n_layers, step)]

        layers: list[dict[str, Any]] = []
        prev_area = 0.0
        max_gradient = 0.0

        for z in sample_heights:
            try:
                section = mesh.section(
                    plane_origin=[0, 0, z],
                    plane_normal=[0, 0, 1],
                )
                if section is not None:
                    planar, _ = section.to_planar()
                    area = float(planar.area)
                else:
                    area = 0.0
            except Exception:
                area = 0.0

            gradient = (
                abs(area - prev_area) / max(prev_area, 1e-6) if prev_area > 0 else 0
            )
            max_gradient = max(max_gradient, gradient)

            layers.append(
                {
                    "z": round(z, 2),
                    "area_mm2": round(area, 2),
                    "gradient": round(gradient, 4),
                }
            )
            prev_area = area

        if max_gradient > 1.0:
            risk_level = "high"
        elif max_gradient > 0.5:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_level": risk_level,
            "max_gradient": round(max_gradient, 4),
            "layers": layers,
            "n_layers_total": n_layers,
            "n_layers_sampled": len(layers),
            "recommendations": self._gradient_recommendations(max_gradient),
        }

    @staticmethod
    def _gradient_recommendations(max_gradient: float) -> list[str]:
        recs = []
        if max_gradient > 1.0:
            recs.append("截面积变化剧烈，建议在渐变处增加过渡特征")
            recs.append("降低打印速度并增加冷却时间")
        elif max_gradient > 0.5:
            recs.append("中等截面变化，建议适度降低打印速度")
        else:
            recs.append("截面变化平缓，热风险低")
        return recs

    async def execute(self, ctx: Any) -> None:
        """Execute gradient thermal analysis."""
        import asyncio

        asset = ctx.get_asset("final_mesh")
        mesh = await asyncio.to_thread(trimesh.load, asset.path, force="mesh")

        await ctx.dispatch_progress(1, 2, "层级热梯度分析中")

        report = await asyncio.to_thread(self.analyze, mesh)

        ctx.put_data("thermal_report", report)
        ctx.put_data("thermal_simulation_status", "completed")

        await ctx.dispatch_progress(2, 2, f"热梯度分析完成: {report['risk_level']}")
