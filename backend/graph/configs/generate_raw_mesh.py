"""Configuration for generate_raw_mesh node."""

from __future__ import annotations

from pydantic import Field

from backend.graph.configs.base import BaseNodeConfig


class GenerateRawMeshConfig(BaseNodeConfig):
    """generate_raw_mesh node configuration.

    Supports 3 local GPU server strategies:
    - triposg (default): SDF-based, watertight, fastest
    - trellis2: SLat-based, texture support
    - hunyuan3d: Hybrid, high detail
    """

    strategy: str = "triposg"

    # TripoSG (local, :8081)
    triposg_endpoint: str | None = Field(
        default=None, json_schema_extra={"x-scope": "system"},
    )

    # TRELLIS.2 (local, :8082)
    trellis2_endpoint: str | None = Field(
        default=None, json_schema_extra={"x-scope": "system"},
    )

    # Hunyuan3D-2.1 (local, :8080)
    hunyuan3d_endpoint: str | None = Field(
        default=None, json_schema_extra={"x-scope": "system"},
    )

    # Common
    timeout: int = 330  # GPU server 300s + 30s network margin
    output_format: str = "glb"
