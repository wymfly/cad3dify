"""Mesh provider abstraction layer for 3D generation APIs.

Note: TripoProvider has been removed. The new pipeline uses local GPU
server strategies (TripoSG, TRELLIS.2, Hunyuan3D) exclusively.
"""
from backend.infra.mesh_providers.base import MeshProvider
from backend.infra.mesh_providers.hunyuan import HunyuanProvider

__all__ = ["MeshProvider", "HunyuanProvider"]
