"""Configuration for boolean_assemble node."""

from __future__ import annotations

from backend.graph.configs.base import BaseNodeConfig


class BooleanAssembleConfig(BaseNodeConfig):
    """boolean_assemble node configuration.

    Controls manifold3d voxel repair gate and boolean cut behavior.
    """

    strategy: str = "manifold3d"
    voxel_resolution: int = 128
    skip_on_non_manifold: bool = False  # False = repair failure raises exception
