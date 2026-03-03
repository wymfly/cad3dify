"""apply_lattice — TPMS lattice filling for lightweight internal structure.

Generates a Triply Periodic Minimal Surface (Gyroid/Schwarz-P/Diamond)
and applies it to the mesh interior via boolean intersection.
"""

from __future__ import annotations

import logging

from backend.graph.configs.apply_lattice import ApplyLatticeConfig
from backend.graph.context import NodeContext
from backend.graph.registry import register_node
from backend.graph.strategies.lattice.tpms import TPMSStrategy

logger = logging.getLogger(__name__)


@register_node(
    name="apply_lattice",
    display_name="晶格填充",
    requires=["final_mesh"],
    produces=["lattice_mesh"],
    input_types=["organic"],
    config_model=ApplyLatticeConfig,
    strategies={
        "tpms": TPMSStrategy,
    },
    default_strategy="tpms",
    fallback_chain=["tpms"],
    non_fatal=True,
    description="TPMS 晶格填充（Gyroid/Schwarz-P/Diamond），轻量化内部结构",
)
async def apply_lattice_node(ctx: NodeContext) -> None:
    """Execute lattice filling via strategy dispatch.

    non_fatal=True: lattice failure should not block the pipeline.
    """
    if not ctx.has_asset("final_mesh"):
        logger.info("apply_lattice: no final_mesh, skipping")
        ctx.put_data("apply_lattice_status", "skipped_no_input")
        return

    if ctx.config.strategy == "auto":
        await ctx.execute_with_fallback()
    else:
        strategy = ctx.get_strategy()
        await strategy.execute(ctx)
