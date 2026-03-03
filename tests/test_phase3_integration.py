"""Phase 3 integration tests -- verify all nodes register and interop correctly."""

from __future__ import annotations

import pytest


class TestPhase3NodeRegistration:
    """All Phase 3 nodes should be discoverable in the registry."""

    def test_orientation_optimizer_in_registry(self):
        import backend.graph.nodes.orientation_optimizer  # noqa: F401
        from backend.graph.registry import registry

        assert "orientation_optimizer" in registry

    def test_apply_lattice_in_registry(self):
        import backend.graph.nodes.apply_lattice  # noqa: F401
        from backend.graph.registry import registry

        assert "apply_lattice" in registry

    def test_thermal_simulation_in_registry(self):
        import backend.graph.nodes.thermal_simulation  # noqa: F401
        from backend.graph.registry import registry

        assert "thermal_simulation" in registry

    def test_generate_supports_in_registry(self):
        import backend.graph.nodes.generate_supports  # noqa: F401
        from backend.graph.registry import registry

        assert "generate_supports" in registry

    def test_slice_to_gcode_in_registry(self):
        import backend.graph.nodes.slice_to_gcode  # noqa: F401
        from backend.graph.registry import registry

        assert "slice_to_gcode" in registry


class TestPhase3TopologyChain:
    """Verify requires/produces chain is consistent across Phase 3 nodes."""

    def test_orientation_requires_final_mesh(self):
        import backend.graph.nodes.orientation_optimizer  # noqa: F401
        from backend.graph.registry import registry

        desc = registry.get("orientation_optimizer")
        assert "final_mesh" in desc.requires

    def test_orientation_produces_oriented_mesh(self):
        import backend.graph.nodes.orientation_optimizer  # noqa: F401
        from backend.graph.registry import registry

        desc = registry.get("orientation_optimizer")
        assert "oriented_mesh" in desc.produces

    def test_lattice_requires_final_mesh(self):
        import backend.graph.nodes.apply_lattice  # noqa: F401
        from backend.graph.registry import registry

        desc = registry.get("apply_lattice")
        assert "final_mesh" in desc.requires

    def test_lattice_produces_lattice_mesh(self):
        import backend.graph.nodes.apply_lattice  # noqa: F401
        from backend.graph.registry import registry

        desc = registry.get("apply_lattice")
        assert "lattice_mesh" in desc.produces

    def test_thermal_requires_final_mesh(self):
        import backend.graph.nodes.thermal_simulation  # noqa: F401
        from backend.graph.registry import registry

        desc = registry.get("thermal_simulation")
        assert "final_mesh" in desc.requires

    def test_generate_supports_requires_final_mesh(self):
        import backend.graph.nodes.generate_supports  # noqa: F401
        from backend.graph.registry import registry

        desc = registry.get("generate_supports")
        assert "final_mesh" in desc.requires

    def test_slice_to_gcode_accepts_oriented_mesh(self):
        """slice_to_gcode should accept oriented_mesh (Phase 3 output)."""
        import backend.graph.nodes.slice_to_gcode  # noqa: F401
        from backend.graph.registry import registry

        desc = registry.get("slice_to_gcode")
        # requires is [["oriented_mesh", "lattice_mesh", ...]] (OR-group)
        or_group = desc.requires[0]
        assert isinstance(or_group, list)
        assert "oriented_mesh" in or_group

    def test_slice_to_gcode_accepts_lattice_mesh(self):
        """slice_to_gcode should accept lattice_mesh (Phase 3 output)."""
        import backend.graph.nodes.slice_to_gcode  # noqa: F401
        from backend.graph.registry import registry

        desc = registry.get("slice_to_gcode")
        or_group = desc.requires[0]
        assert isinstance(or_group, list)
        assert "lattice_mesh" in or_group

    def test_all_phase3_non_fatal(self):
        """All Phase 3 nodes should be non_fatal."""
        import backend.graph.nodes.apply_lattice  # noqa: F401
        import backend.graph.nodes.generate_supports  # noqa: F401
        import backend.graph.nodes.orientation_optimizer  # noqa: F401
        import backend.graph.nodes.thermal_simulation  # noqa: F401
        from backend.graph.registry import registry

        for name in [
            "orientation_optimizer",
            "apply_lattice",
            "thermal_simulation",
            "generate_supports",
        ]:
            desc = registry.get(name)
            assert desc.non_fatal is True, f"{name} should be non_fatal"


class TestPhase3ConfigDefaults:
    """Config defaults should be sensible for production."""

    def test_orientation_config_defaults(self):
        from backend.graph.configs.orientation_optimizer import \
            OrientationOptimizerConfig

        cfg = OrientationOptimizerConfig()
        assert cfg.strategy == "basic"
        assert cfg.enabled is True
        assert cfg.weight_support_area == 0.4
        assert cfg.weight_height == 0.3
        assert cfg.weight_stability == 0.3

    def test_orientation_config_rejects_negative_weight(self):
        from backend.graph.configs.orientation_optimizer import \
            OrientationOptimizerConfig

        with pytest.raises(Exception):
            OrientationOptimizerConfig(weight_support_area=-1.0)

    def test_lattice_config_defaults(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig

        cfg = ApplyLatticeConfig()
        assert cfg.strategy == "tpms"
        assert cfg.lattice_type == "gyroid"
        assert cfg.cell_size == 8.0
        assert cfg.wall_thickness == 0.8
        assert cfg.shell_thickness == 2.0
        assert cfg.resolution == 64

    def test_lattice_config_rejects_invalid_cell_size(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig

        with pytest.raises(Exception):
            ApplyLatticeConfig(cell_size=0)
        with pytest.raises(Exception):
            ApplyLatticeConfig(cell_size=100)

    def test_thermal_config_defaults(self):
        from backend.graph.configs.thermal_simulation import \
            ThermalSimulationConfig

        cfg = ThermalSimulationConfig()
        assert cfg.strategy == "rules"
        assert cfg.overhang_threshold == 45.0
        assert cfg.aspect_ratio_threshold == 10.0
        assert cfg.large_flat_area_threshold == 100.0

    def test_thermal_config_rejects_invalid_threshold(self):
        from backend.graph.configs.thermal_simulation import \
            ThermalSimulationConfig

        with pytest.raises(Exception):
            ThermalSimulationConfig(overhang_threshold=0)

    def test_generate_supports_config_defaults(self):
        from backend.graph.configs.generate_supports import \
            GenerateSupportsConfig

        cfg = GenerateSupportsConfig()
        assert cfg.support_type == "auto"
        assert cfg.support_density == 15

    def test_slice_config_defaults(self):
        from backend.graph.configs.slice_to_gcode import SliceToGcodeConfig

        cfg = SliceToGcodeConfig()
        assert cfg.support_type == "auto"
        assert cfg.support_density == 15
        assert cfg.layer_height == 0.2
        assert cfg.nozzle_diameter == 0.4
        assert cfg.filament_type == "PLA"

    def test_slice_config_rejects_invalid_layer_height(self):
        from backend.graph.configs.slice_to_gcode import SliceToGcodeConfig

        with pytest.raises(Exception):
            SliceToGcodeConfig(layer_height=0.01)
        with pytest.raises(Exception):
            SliceToGcodeConfig(layer_height=1.0)


class TestPhase3StrategyAvailability:
    """All algorithm strategies should be available (no external dependencies missing)."""

    def test_basic_orient_available(self):
        from backend.graph.configs.orientation_optimizer import \
            OrientationOptimizerConfig
        from backend.graph.strategies.orient.basic import BasicOrientStrategy

        s = BasicOrientStrategy(config=OrientationOptimizerConfig())
        assert s.check_available() is True

    def test_scipy_orient_available(self):
        from backend.graph.configs.orientation_optimizer import \
            OrientationOptimizerConfig
        from backend.graph.strategies.orient.scipy_orient import \
            ScipyOrientStrategy

        s = ScipyOrientStrategy(config=OrientationOptimizerConfig())
        assert s.check_available() is True

    def test_tpms_lattice_available(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig
        from backend.graph.strategies.lattice.tpms import TPMSStrategy

        s = TPMSStrategy(config=ApplyLatticeConfig())
        assert s.check_available() is True

    def test_rules_thermal_available(self):
        from backend.graph.configs.thermal_simulation import \
            ThermalSimulationConfig
        from backend.graph.strategies.thermal.rules import RulesThermalStrategy

        s = RulesThermalStrategy(config=ThermalSimulationConfig())
        assert s.check_available() is True

    def test_gradient_thermal_available(self):
        from backend.graph.configs.thermal_simulation import \
            ThermalSimulationConfig
        from backend.graph.strategies.thermal.gradient import \
            GradientThermalStrategy

        s = GradientThermalStrategy(config=ThermalSimulationConfig())
        assert s.check_available() is True


class TestPhase3FallbackChains:
    """Verify fallback chain configuration for Phase 3 nodes."""

    def test_orientation_fallback_chain(self):
        import backend.graph.nodes.orientation_optimizer  # noqa: F401
        from backend.graph.registry import registry

        desc = registry.get("orientation_optimizer")
        assert desc.fallback_chain == ["scipy", "basic"]
        assert desc.default_strategy == "basic"

    def test_lattice_fallback_chain(self):
        import backend.graph.nodes.apply_lattice  # noqa: F401
        from backend.graph.registry import registry

        desc = registry.get("apply_lattice")
        assert desc.fallback_chain == ["tpms"]
        assert desc.default_strategy == "tpms"

    def test_thermal_fallback_chain(self):
        import backend.graph.nodes.thermal_simulation  # noqa: F401
        from backend.graph.registry import registry

        desc = registry.get("thermal_simulation")
        assert desc.fallback_chain == ["gradient", "rules"]
        assert desc.default_strategy == "rules"

    def test_generate_supports_no_strategies(self):
        """generate_supports has no strategies (delegated to slicer)."""
        import backend.graph.nodes.generate_supports  # noqa: F401
        from backend.graph.registry import registry

        desc = registry.get("generate_supports")
        assert desc.strategies == {}
        assert desc.fallback_chain == []


class TestPhase3InputTypes:
    """All Phase 3 nodes should be restricted to organic input type."""

    def test_all_phase3_organic_only(self):
        import backend.graph.nodes.apply_lattice  # noqa: F401
        import backend.graph.nodes.generate_supports  # noqa: F401
        import backend.graph.nodes.orientation_optimizer  # noqa: F401
        import backend.graph.nodes.thermal_simulation  # noqa: F401
        from backend.graph.registry import registry

        for name in [
            "orientation_optimizer",
            "apply_lattice",
            "thermal_simulation",
            "generate_supports",
        ]:
            desc = registry.get(name)
            assert desc.input_types == [
                "organic"
            ], f"{name} should only support organic input type"
