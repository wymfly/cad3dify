"""Configuration for generate_supports node."""

from __future__ import annotations

from typing import Literal

from backend.graph.configs.base import BaseNodeConfig


class GenerateSupportsConfig(BaseNodeConfig):
    """generate_supports node configuration."""

    support_type: Literal["auto", "tree", "linear", "none"] = "auto"
    support_density: int = 15  # %, support infill density
