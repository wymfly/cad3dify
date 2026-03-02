"""Neural strategy configuration model."""

from backend.graph.configs.base import BaseNodeConfig


class NeuralStrategyConfig(BaseNodeConfig):
    """Configuration for nodes that support Neural channel strategies.

    Extends BaseNodeConfig with neural-specific fields.
    """

    neural_enabled: bool = False
    neural_endpoint: str | None = None
    neural_timeout: int = 60
    health_check_path: str = "/health"
