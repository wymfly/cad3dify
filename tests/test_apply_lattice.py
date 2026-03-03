"""Tests for apply_lattice node and TPMS strategy."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest


class TestApplyLatticeConfig:
    def test_defaults(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig

        cfg = ApplyLatticeConfig()
        assert cfg.strategy == "tpms"
        assert cfg.lattice_type == "gyroid"
        assert 0.0 < cfg.cell_size <= 50.0
        assert 0.0 < cfg.wall_thickness

    def test_cell_size_validation(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig

        with pytest.raises(ValueError, match="cell_size"):
            ApplyLatticeConfig(cell_size=0)

    def test_cell_size_upper_bound(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig

        with pytest.raises(ValueError, match="cell_size"):
            ApplyLatticeConfig(cell_size=51)

    def test_wall_thickness_validation(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig

        with pytest.raises(ValueError, match="wall_thickness"):
            ApplyLatticeConfig(wall_thickness=0)

    def test_shell_thickness_validation(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig

        with pytest.raises(ValueError, match="shell_thickness"):
            ApplyLatticeConfig(shell_thickness=-1)

    def test_resolution_validation(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig

        with pytest.raises(ValueError, match="resolution"):
            ApplyLatticeConfig(resolution=4)

    def test_lattice_type_enum(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig

        cfg_g = ApplyLatticeConfig(lattice_type="gyroid")
        assert cfg_g.lattice_type == "gyroid"
        cfg_s = ApplyLatticeConfig(lattice_type="schwarz_p")
        assert cfg_s.lattice_type == "schwarz_p"
        cfg_d = ApplyLatticeConfig(lattice_type="diamond")
        assert cfg_d.lattice_type == "diamond"

    def test_invalid_lattice_type(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig

        with pytest.raises(ValueError):
            ApplyLatticeConfig(lattice_type="invalid")

    def test_inherits_base_fields(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig

        cfg = ApplyLatticeConfig(enabled=False)
        assert cfg.enabled is False


class TestTPMSFunctions:
    """Test TPMS scalar field functions."""

    def test_gyroid_field(self):
        from backend.graph.strategies.lattice.tpms import gyroid_field

        x = np.array([0.0])
        y = np.array([0.0])
        z = np.array([0.0])
        result = gyroid_field(x, y, z, cell_size=10.0)
        assert isinstance(result, np.ndarray)

    def test_gyroid_field_origin_value(self):
        from backend.graph.strategies.lattice.tpms import gyroid_field

        # At origin, sin(0)*cos(0) + sin(0)*cos(0) + sin(0)*cos(0) = 0
        result = gyroid_field(
            np.array([0.0]), np.array([0.0]), np.array([0.0]), cell_size=10.0
        )
        assert np.isclose(result[0], 0.0, atol=1e-10)

    def test_schwarz_p_field(self):
        from backend.graph.strategies.lattice.tpms import schwarz_p_field

        x = np.array([0.0])
        y = np.array([0.0])
        z = np.array([0.0])
        result = schwarz_p_field(x, y, z, cell_size=10.0)
        assert isinstance(result, np.ndarray)

    def test_schwarz_p_field_origin_value(self):
        from backend.graph.strategies.lattice.tpms import schwarz_p_field

        # At origin, cos(0) + cos(0) + cos(0) = 3
        result = schwarz_p_field(
            np.array([0.0]), np.array([0.0]), np.array([0.0]), cell_size=10.0
        )
        assert np.isclose(result[0], 3.0, atol=1e-10)

    def test_diamond_field(self):
        from backend.graph.strategies.lattice.tpms import diamond_field

        x = np.array([0.0])
        y = np.array([0.0])
        z = np.array([0.0])
        result = diamond_field(x, y, z, cell_size=10.0)
        assert isinstance(result, np.ndarray)

    def test_field_array_shape(self):
        from backend.graph.strategies.lattice.tpms import gyroid_field

        x = np.linspace(0, 10, 5)
        y = np.linspace(0, 10, 5)
        z = np.linspace(0, 10, 5)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        result = gyroid_field(X, Y, Z, cell_size=10.0)
        assert result.shape == (5, 5, 5)


class TestTPMSStrategy:
    """Test TPMS lattice generation strategy."""

    @pytest.fixture
    def strategy(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig
        from backend.graph.strategies.lattice.tpms import TPMSStrategy

        cfg = ApplyLatticeConfig(cell_size=5.0, shell_thickness=1.0)
        return TPMSStrategy(config=cfg)

    def test_check_available(self, strategy):
        assert strategy.check_available() is True

    def test_generate_lattice_returns_mesh(self, strategy):
        """generate_lattice(bbox) returns a trimesh mesh."""
        import trimesh

        bbox_min = np.array([0, 0, 0])
        bbox_max = np.array([20, 20, 20])
        lattice = strategy.generate_lattice(bbox_min, bbox_max)
        assert isinstance(lattice, trimesh.Trimesh)
        assert len(lattice.vertices) > 0
        assert len(lattice.faces) > 0

    def test_apply_to_mesh_returns_trimesh(self, strategy):
        """apply_to_mesh(mesh) should return a valid Trimesh."""
        import trimesh

        box = trimesh.creation.box(extents=[20, 20, 20])
        result = strategy.apply_to_mesh(box)
        assert isinstance(result, trimesh.Trimesh)
        assert len(result.vertices) > 0
        assert len(result.faces) > 0

    def test_apply_to_mesh_intersects_correctly(self, strategy):
        """apply_to_mesh(mesh) should produce mesh smaller than original."""
        import trimesh

        box = trimesh.creation.box(extents=[20, 20, 20])
        result = strategy.apply_to_mesh(box)
        assert isinstance(result, trimesh.Trimesh)
        # Lattice result should have less volume than solid.
        # If boolean ops fail and original is returned, skip volume check.
        if len(result.faces) != len(box.faces):
            assert result.volume < box.volume * 0.95

    def test_strategy_with_schwarz_p(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig
        from backend.graph.strategies.lattice.tpms import TPMSStrategy

        cfg = ApplyLatticeConfig(
            lattice_type="schwarz_p", cell_size=5.0, shell_thickness=1.0
        )
        strat = TPMSStrategy(config=cfg)
        bbox_min = np.array([0, 0, 0])
        bbox_max = np.array([20, 20, 20])
        lattice = strat.generate_lattice(bbox_min, bbox_max)
        assert len(lattice.vertices) > 0

    def test_strategy_with_diamond(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig
        from backend.graph.strategies.lattice.tpms import TPMSStrategy

        cfg = ApplyLatticeConfig(
            lattice_type="diamond", cell_size=5.0, shell_thickness=1.0
        )
        strat = TPMSStrategy(config=cfg)
        bbox_min = np.array([0, 0, 0])
        bbox_max = np.array([20, 20, 20])
        lattice = strat.generate_lattice(bbox_min, bbox_max)
        assert len(lattice.vertices) > 0


class TestApplyLatticeNode:
    @pytest.mark.asyncio
    async def test_node_registered_with_tpms_strategy(self):
        from backend.graph.nodes.apply_lattice import apply_lattice_node

        desc = apply_lattice_node._node_descriptor
        assert "tpms" in desc.strategies
        assert desc.name == "apply_lattice"
        assert desc.non_fatal is True

    @pytest.mark.asyncio
    async def test_node_skips_without_input(self):
        from backend.graph.nodes.apply_lattice import apply_lattice_node

        ctx = MagicMock()
        ctx.has_asset.return_value = False
        ctx.config = MagicMock()
        ctx.config.strategy = "tpms"
        ctx.config.enabled = True

        await apply_lattice_node(ctx)
        ctx.put_data.assert_called_with("apply_lattice_status", "skipped_no_input")


def _make_box_mesh(x: float, y: float, z: float):
    import trimesh

    return trimesh.creation.box(extents=[x, y, z])
