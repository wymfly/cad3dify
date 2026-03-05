"""generate_raw_mesh — strategized 3D mesh generation node.

Strategy-based node supporting 3 local GPU server models:
TripoSG (default), TRELLIS.2, Hunyuan3D-2.1.
"""

from __future__ import annotations

import logging

from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig
from backend.graph.context import NodeContext
from backend.graph.registry import register_node
from backend.graph.strategies.generate.hunyuan3d import Hunyuan3DGenerateStrategy
from backend.graph.strategies.generate.trellis2 import TRELLIS2GenerateStrategy
from backend.graph.strategies.generate.triposg import TripoSGGenerateStrategy

logger = logging.getLogger(__name__)

_STRATEGIES = {
    "triposg": TripoSGGenerateStrategy,
    "trellis2": TRELLIS2GenerateStrategy,
    "hunyuan3d": Hunyuan3DGenerateStrategy,
}


@register_node(
    name="generate_raw_mesh",
    display_name="网格生成",
    requires=["confirmed_params"],
    produces=["raw_mesh"],
    input_types=["organic"],
    config_model=GenerateRawMeshConfig,
    strategies=_STRATEGIES,
    default_strategy="triposg",
    description="通过本地 GPU 服务器 3D 生成模型创建原始网格",
)
async def generate_raw_mesh_node(ctx: NodeContext) -> None:
    """Execute 3D mesh generation via strategy dispatch.

    - "auto" -> remapped to "triposg" (default strategy)
    - Explicit strategy name -> direct dispatch
    - No fallback_chain — user explicitly chooses, failure = error
    """
    if ctx.config.strategy == "auto":
        ctx.config.strategy = "triposg"

    strategy = ctx.get_strategy()
    await strategy.execute(ctx)
