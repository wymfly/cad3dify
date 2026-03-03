"""generate_raw_mesh — strategized 3D mesh generation node.

Strategy-based node supporting 4 models: Hunyuan3D, Tripo3D, SPAR3D, TRELLIS.

Each model is a separate strategy with dual deployment support
(SaaS API and/or local HTTP endpoint).
"""

from __future__ import annotations

import logging

from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig
from backend.graph.context import NodeContext
from backend.graph.registry import register_node
from backend.graph.strategies.generate.hunyuan3d import Hunyuan3DGenerateStrategy
from backend.graph.strategies.generate.spar3d import SPAR3DGenerateStrategy
from backend.graph.strategies.generate.trellis import TRELLISGenerateStrategy
from backend.graph.strategies.generate.tripo3d import Tripo3DGenerateStrategy

logger = logging.getLogger(__name__)


@register_node(
    name="generate_raw_mesh",
    display_name="网格生成",
    requires=["confirmed_params"],
    produces=["raw_mesh"],
    input_types=["organic"],
    config_model=GenerateRawMeshConfig,
    strategies={
        "hunyuan3d": Hunyuan3DGenerateStrategy,
        "tripo3d": Tripo3DGenerateStrategy,
        "spar3d": SPAR3DGenerateStrategy,
        "trellis": TRELLISGenerateStrategy,
    },
    fallback_chain=["hunyuan3d", "tripo3d", "spar3d", "trellis"],
    default_strategy="hunyuan3d",
    description="通过 3D 生成模型创建原始网格，支持 4 种模型策略 + 自动 fallback",
)
async def generate_raw_mesh_node(ctx: NodeContext) -> None:
    """Execute 3D mesh generation via strategy dispatch.

    For auto mode, uses ctx.execute_with_fallback() which iterates
    fallback_chain (hunyuan3d -> tripo3d -> spar3d -> trellis).
    For explicit strategy, calls get_strategy().execute() directly.
    """
    if ctx.config.strategy == "auto":
        await ctx.execute_with_fallback()
    else:
        strategy = ctx.get_strategy()
        await strategy.execute(ctx)
