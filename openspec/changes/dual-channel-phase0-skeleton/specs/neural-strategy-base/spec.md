## ADDED Requirements

### Requirement: NeuralStrategy base class with HTTP health check

The system SHALL provide a `NeuralStrategy` abstract base class (extending `NodeStrategy`) that integrates HTTP health check into `check_available()`. All Neural channel strategies SHALL extend this base class.

#### Scenario: Neural strategy available when endpoint healthy
- **WHEN** a `NeuralStrategy` subclass has `neural_enabled=True` and `neural_endpoint="http://gpu:8090"`
- **AND** GET `http://gpu:8090/health` returns HTTP 200
- **THEN** `check_available()` SHALL return `True`

#### Scenario: Neural strategy unavailable when endpoint unhealthy
- **WHEN** a `NeuralStrategy` subclass has `neural_enabled=True` and `neural_endpoint="http://gpu:8090"`
- **AND** GET `http://gpu:8090/health` returns non-200 or times out
- **THEN** `check_available()` SHALL return `False`

#### Scenario: Neural strategy disabled by default
- **WHEN** a `NeuralStrategy` subclass has `neural_enabled=False` (default)
- **THEN** `check_available()` SHALL return `False` without making any HTTP request

#### Scenario: Neural strategy unavailable when no endpoint configured
- **WHEN** a `NeuralStrategy` subclass has `neural_enabled=True` but `neural_endpoint=None`
- **THEN** `check_available()` SHALL return `False`

### Requirement: NeuralStrategyConfig extends BaseNodeConfig

The system SHALL provide `NeuralStrategyConfig` as a Pydantic model extending `BaseNodeConfig`, adding Neural channel configuration fields.

#### Scenario: Config parsed from pipeline_config
- **WHEN** `pipeline_config` contains `{"mesh_healer": {"strategy": "auto", "neural_enabled": true, "neural_endpoint": "http://gpu:8090"}}`
- **AND** the node's `config_model` is set to `NeuralStrategyConfig`
- **THEN** `NodeContext.config` SHALL be a `NeuralStrategyConfig` instance with `neural_enabled=True` and `neural_endpoint="http://gpu:8090"`

#### Scenario: Config injected into strategy via constructor
- **WHEN** `NodeContext.get_strategy()` instantiates a `NeuralStrategy` subclass
- **THEN** it SHALL pass the node config as `strategies[name](config=self.config)`
- **AND** the `NeuralStrategy` instance SHALL access endpoint configuration via `self.config`
- **AND** existing no-arg strategies SHALL remain compatible (default `config=None`)

#### Scenario: Default config has Neural disabled
- **WHEN** `pipeline_config` does not contain an entry for a node using `NeuralStrategyConfig`
- **THEN** the default config SHALL have `neural_enabled=False`, `neural_endpoint=None`, `neural_timeout=60`

### Requirement: Health check results are cached at class/module level

The system SHALL cache health check results to avoid repeated HTTP requests within a short window. The cache SHALL be **class-level or module-level** (keyed by `(endpoint, health_check_path)` tuple), NOT instance-level — because `get_strategy()` creates a new strategy instance on each call, instance-level cache would always miss.

#### Scenario: Cache hit within TTL
- **WHEN** `check_available()` was called less than 30 seconds ago for the same `(endpoint, health_check_path)` and returned `True`
- **AND** `check_available()` is called again (possibly on a different instance with the same endpoint)
- **THEN** the cached result SHALL be returned without making a new HTTP request

#### Scenario: Cache expired triggers new check
- **WHEN** `check_available()` was last called more than 30 seconds ago for a given `(endpoint, health_check_path)`
- **AND** `check_available()` is called again
- **THEN** a new HTTP health check request SHALL be made

#### Scenario: Health check uses sync HTTP with short timeout
- **WHEN** `check_available()` performs an HTTP health check
- **THEN** it SHALL use a synchronous HTTP client with a 5-second timeout
- **AND** the sync overhead is mitigated by the 30s cache (first call blocks briefly, subsequent calls within TTL are instant)

### Requirement: Three-state design for Neural strategies

Each Neural strategy SHALL operate in one of three states: disabled, available, or degraded.

#### Scenario: Disabled state
- **WHEN** `neural_enabled=False` or `neural_endpoint=None`
- **THEN** the strategy is in **disabled** state
- **AND** it SHALL NOT appear in available strategies listings

#### Scenario: Available state
- **WHEN** `neural_enabled=True` and `neural_endpoint` is set and health check passes
- **THEN** the strategy is in **available** state
- **AND** users MAY select it explicitly or via auto mode

#### Scenario: Degraded state
- **WHEN** `neural_enabled=True` and `neural_endpoint` is set but health check fails
- **THEN** the strategy is in **degraded** state
- **AND** auto mode SHALL skip it
- **AND** explicit selection SHALL raise `RuntimeError` with health check failure details
