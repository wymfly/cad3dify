## ADDED Requirements

### Requirement: NodeStrategy abstract interface
The system SHALL provide a `NodeStrategy` ABC with `execute(*args, **kwargs) -> Any` (abstract) and `check_available() -> bool` (default True) methods.

#### Scenario: Strategy implementation
- **WHEN** a class inherits from `NodeStrategy` and implements `execute()`
- **THEN** it can be registered in a node's `strategies` dict and instantiated at runtime

### Requirement: Strategy availability check
Each strategy SHALL implement `check_available()` to verify its runtime dependencies (e.g., pymeshlab installed). The system SHALL skip unavailable strategies when presenting options to the UI.

#### Scenario: pymeshlab not installed
- **WHEN** `PymeshlabStrategy.check_available()` is called and pymeshlab is not importable
- **THEN** it returns `False`

#### Scenario: Available strategies listed for UI
- **WHEN** `GET /api/v1/pipeline/nodes` is called
- **THEN** each node's strategies include an `available: bool` field reflecting `check_available()` results

### Requirement: Strategy selection via config
The active strategy for a node SHALL be determined by `config.strategy` field. If the selected strategy is unavailable, the system SHALL raise an error before execution.

#### Scenario: Strategy selected and executed
- **WHEN** `MeshRepairConfig(strategy="pymeshlab")` is the config and `PymeshlabStrategy.check_available()` returns `True`
- **THEN** `ctx.get_strategy()` returns an instance of `PymeshlabStrategy`

#### Scenario: Unavailable strategy selected
- **WHEN** `MeshRepairConfig(strategy="meshlib")` is the config and `MeshLibStrategy.check_available()` returns `False`
- **THEN** `ctx.get_strategy()` raises an error indicating meshlib is not available

### Requirement: BaseNodeConfig with standard fields
All node configs SHALL extend `BaseNodeConfig` which provides `enabled: bool = True` and `strategy: str` (default from descriptor's `default_strategy`).

#### Scenario: Default config
- **WHEN** no config is provided for a node in `pipeline_config`
- **THEN** the node uses its `config_model` defaults, which inherit `enabled=True` and `strategy=<default_strategy>`
