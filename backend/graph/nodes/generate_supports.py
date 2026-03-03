"""generate_supports -- support strategy configuration (delegated to slicer).

Design decision: support generation is delegated to slice_to_gcode
(PrusaSlicer/OrcaSlicer built-in tree supports). This node configures
support parameters based on orientation_optimizer output.
"""

from __future__ import annotations

import logging

from backend.graph.configs.generate_supports import GenerateSupportsConfig
from backend.graph.context import NodeContext
from backend.graph.registry import register_node

logger = logging.getLogger(__name__)


@register_node(
    name="generate_supports",
    display_name="支撑策略",
    requires=["final_mesh"],
    produces=[],
    input_types=["organic"],
    config_model=GenerateSupportsConfig,
    non_fatal=True,
    description="配置支撑策略并委托给切片器执行（PrusaSlicer 内置树状支撑）",
)
async def generate_supports_node(ctx: NodeContext) -> None:
    """Configure support parameters for downstream slice_to_gcode."""
    if not ctx.has_asset("final_mesh"):
        logger.info("generate_supports: no final_mesh, skipping")
        ctx.put_data("generate_supports_status", "skipped_no_input")
        return

    orientation_result = ctx.get_data("orientation_result")

    support_type = ctx.config.support_type
    support_density = ctx.config.support_density

    if support_type == "auto":
        if orientation_result:
            support_type = "tree"
        else:
            support_type = "linear"

    ctx.put_data(
        "support_config",
        {
            "support_type": support_type,
            "support_density": support_density,
        },
    )
    ctx.put_data("generate_supports_status", "delegated_to_slicer")

    logger.info(
        "generate_supports: configured %s supports (density=%d%%) for slicer",
        support_type,
        support_density,
    )
