"""Base configuration model for pipeline nodes."""

from pydantic import BaseModel


class BaseNodeConfig(BaseModel):
    """Every node config inherits from this — provides enabled + strategy."""

    enabled: bool = True
    strategy: str = "default"
