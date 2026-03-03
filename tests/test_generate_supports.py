"""Tests for generate_supports node (delegated to slice_to_gcode)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestSliceToGcodeConfigExtension:
    def test_support_type_field(self):
        from backend.graph.configs.slice_to_gcode import SliceToGcodeConfig

        cfg = SliceToGcodeConfig(support_type="tree")
        assert cfg.support_type == "tree"

    def test_support_type_default(self):
        from backend.graph.configs.slice_to_gcode import SliceToGcodeConfig

        cfg = SliceToGcodeConfig()
        assert cfg.support_type == "auto"

    def test_support_density(self):
        from backend.graph.configs.slice_to_gcode import SliceToGcodeConfig

        cfg = SliceToGcodeConfig(support_density=20)
        assert cfg.support_density == 20


class TestGenerateSupportsNode:
    @pytest.mark.asyncio
    async def test_node_registered(self):
        from backend.graph.nodes.generate_supports import \
            generate_supports_node

        desc = generate_supports_node._node_descriptor
        assert desc.name == "generate_supports"
        assert desc.non_fatal is True

    @pytest.mark.asyncio
    async def test_passthrough_delegates_to_slicer(self):
        """Node should be a passthrough that sets support config for slice_to_gcode."""
        from backend.graph.configs.generate_supports import \
            GenerateSupportsConfig
        from backend.graph.nodes.generate_supports import \
            generate_supports_node

        ctx = MagicMock()
        ctx.has_asset.return_value = True
        ctx.get_data.return_value = None
        ctx.config = GenerateSupportsConfig(support_type="tree", support_density=15)

        await generate_supports_node(ctx)

        ctx.put_data.assert_any_call(
            "support_config",
            {
                "support_type": "tree",
                "support_density": 15,
            },
        )

    @pytest.mark.asyncio
    async def test_auto_with_orientation_selects_tree(self):
        """Auto support type + orientation result -> tree supports."""
        from backend.graph.configs.generate_supports import \
            GenerateSupportsConfig
        from backend.graph.nodes.generate_supports import \
            generate_supports_node

        ctx = MagicMock()
        ctx.has_asset.return_value = True
        ctx.get_data.return_value = {"orientation": "Z-up", "score": 0.5}
        ctx.config = GenerateSupportsConfig(support_type="auto")

        await generate_supports_node(ctx)
        ctx.put_data.assert_any_call(
            "support_config",
            {
                "support_type": "tree",
                "support_density": 15,
            },
        )

    @pytest.mark.asyncio
    async def test_auto_without_orientation_selects_linear(self):
        """Auto support type + no orientation -> linear supports."""
        from backend.graph.configs.generate_supports import \
            GenerateSupportsConfig
        from backend.graph.nodes.generate_supports import \
            generate_supports_node

        ctx = MagicMock()
        ctx.has_asset.return_value = True
        ctx.get_data.return_value = None
        ctx.config = GenerateSupportsConfig(support_type="auto")

        await generate_supports_node(ctx)
        ctx.put_data.assert_any_call(
            "support_config",
            {
                "support_type": "linear",
                "support_density": 15,
            },
        )

    @pytest.mark.asyncio
    async def test_skips_without_input(self):
        from backend.graph.nodes.generate_supports import \
            generate_supports_node

        ctx = MagicMock()
        ctx.has_asset.return_value = False
        ctx.config = MagicMock()

        await generate_supports_node(ctx)
        ctx.put_data.assert_any_call("generate_supports_status", "skipped_no_input")
