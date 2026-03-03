"""thermal_simulation — DfAM thermal risk assessment.

Degraded design: rules-based + gradient analysis instead of full FEA.
"""

from __future__ import annotations

import logging

from backend.graph.configs.thermal_simulation import ThermalSimulationConfig
from backend.graph.context import NodeContext
from backend.graph.registry import register_node
from backend.graph.strategies.thermal.gradient import GradientThermalStrategy
from backend.graph.strategies.thermal.rules import RulesThermalStrategy

logger = logging.getLogger(__name__)


@register_node(
    name="thermal_simulation",
    display_name="热风险评估",
    requires=["final_mesh"],
    produces=[],
    input_types=["organic"],
    config_model=ThermalSimulationConfig,
    strategies={
        "rules": RulesThermalStrategy,
        "gradient": GradientThermalStrategy,
    },
    default_strategy="rules",
    fallback_chain=["gradient", "rules"],
    non_fatal=True,
    description="基于几何规则和截面梯度的热风险评估（降级版 FEA）",
)
async def thermal_simulation_node(ctx: NodeContext) -> None:
    """Execute thermal risk assessment via strategy dispatch."""
    if not ctx.has_asset("final_mesh"):
        logger.info("thermal_simulation: no final_mesh, skipping")
        ctx.put_data("thermal_simulation_status", "skipped_no_input")
        return

    if ctx.config.strategy == "auto":
        await ctx.execute_with_fallback()
    else:
        strategy = ctx.get_strategy()
        await strategy.execute(ctx)
