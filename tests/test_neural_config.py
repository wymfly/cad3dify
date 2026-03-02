"""Tests for NeuralStrategyConfig."""

import pytest
from backend.graph.configs.base import BaseNodeConfig


class TestNeuralStrategyConfig:
    def test_defaults(self):
        from backend.graph.configs.neural import NeuralStrategyConfig

        cfg = NeuralStrategyConfig()
        assert cfg.neural_enabled is False
        assert cfg.neural_endpoint is None
        assert cfg.neural_timeout == 60
        assert cfg.health_check_path == "/health"
        assert cfg.enabled is True
        assert cfg.strategy == "default"

    def test_custom_values(self):
        from backend.graph.configs.neural import NeuralStrategyConfig

        cfg = NeuralStrategyConfig(
            neural_enabled=True,
            neural_endpoint="http://gpu:8090",
            neural_timeout=30,
            health_check_path="/healthz",
            strategy="auto",
        )
        assert cfg.neural_enabled is True
        assert cfg.neural_endpoint == "http://gpu:8090"
        assert cfg.neural_timeout == 30
        assert cfg.health_check_path == "/healthz"
        assert cfg.strategy == "auto"

    def test_is_subclass_of_base(self):
        from backend.graph.configs.neural import NeuralStrategyConfig

        assert issubclass(NeuralStrategyConfig, BaseNodeConfig)
