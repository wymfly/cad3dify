"""Tests for generate_raw_mesh node registration and strategy dispatch."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGenerateRawMeshConfig:

    def test_default_strategy_is_triposg(self):
        from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig
        config = GenerateRawMeshConfig()
        assert config.strategy == "triposg"

    def test_timeout_default_330(self):
        from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig
        config = GenerateRawMeshConfig()
        assert config.timeout == 330

    def test_has_three_endpoints(self):
        from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig
        config = GenerateRawMeshConfig()
        assert hasattr(config, "triposg_endpoint")
        assert hasattr(config, "trellis2_endpoint")
        assert hasattr(config, "hunyuan3d_endpoint")

    def test_no_legacy_fields(self):
        """tripo3d_api_key, spar3d_endpoint, hunyuan3d_api_key removed."""
        from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig
        config = GenerateRawMeshConfig()
        assert not hasattr(config, "tripo3d_api_key")
        assert not hasattr(config, "spar3d_endpoint")
        assert not hasattr(config, "hunyuan3d_api_key")


class TestAutoStrategyMapping:

    @pytest.mark.asyncio
    async def test_auto_maps_to_triposg(self):
        """strategy='auto' should behave as 'triposg'."""
        from backend.graph.nodes.generate_raw_mesh import generate_raw_mesh_node

        ctx = MagicMock()
        ctx.config = MagicMock(strategy="auto")
        mock_strategy = AsyncMock()
        ctx.get_strategy = MagicMock(return_value=mock_strategy)

        await generate_raw_mesh_node(ctx)

        assert ctx.config.strategy == "triposg"
        mock_strategy.execute.assert_awaited_once_with(ctx)

    @pytest.mark.asyncio
    async def test_invalid_strategy_raises(self):
        """Unknown strategy name raises KeyError."""
        from backend.graph.nodes.generate_raw_mesh import generate_raw_mesh_node

        ctx = MagicMock()
        ctx.config = MagicMock(strategy="nonexistent")
        ctx.get_strategy = MagicMock(side_effect=KeyError("nonexistent"))

        with pytest.raises((KeyError, ValueError)):
            await generate_raw_mesh_node(ctx)
