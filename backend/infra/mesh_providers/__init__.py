"""Mesh provider abstraction layer for 3D generation APIs.

Note: AutoProvider has been removed. The new pipeline uses strategy-based
fallback in generate_raw_mesh node (see backend.graph.nodes.generate_raw_mesh).
"""
from backend.infra.mesh_providers.base import MeshProvider
from backend.infra.mesh_providers.hunyuan import HunyuanProvider
from backend.infra.mesh_providers.tripo import TripoProvider

__all__ = ["MeshProvider", "TripoProvider", "HunyuanProvider"]
