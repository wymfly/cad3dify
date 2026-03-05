## ADDED Requirements

### Requirement: NodeDescriptor declares fallback_chain for auto mode

The `NodeDescriptor` dataclass SHALL include a `fallback_chain: list[str]` field that defines the strategy execution order when the user selects `strategy: "auto"`. The `@register_node` decorator SHALL accept a `fallback_chain` keyword argument and pass it to `NodeDescriptor`.

#### Scenario: Register node with fallback chain
- **WHEN** a node function is decorated with `@register_node(name="mesh_healer", strategies={"algorithm": AlgoStrategy, "neural": NeuralStrategy}, fallback_chain=["algorithm", "neural"])`
- **THEN** the registered `NodeDescriptor` has `fallback_chain == ["algorithm", "neural"]`
- **AND** all names in `fallback_chain` exist in `strategies`

#### Scenario: Register node without fallback chain
- **WHEN** a node function is decorated with `@register_node(name="some_node", strategies={"default": SomeStrategy})` without `fallback_chain`
- **THEN** the registered `NodeDescriptor` has `fallback_chain == []`
- **AND** the node only supports explicit strategy selection (not auto mode)

#### Scenario: Invalid fallback chain rejected at registration
- **WHEN** a node function is decorated with `@register_node(fallback_chain=["nonexistent"])` where `"nonexistent"` is not a key in `strategies`
- **THEN** registration SHALL raise `ValueError` with a message identifying the invalid strategy name

### Requirement: get_strategy() selects strategy without executing (selection layer)

`NodeContext.get_strategy()` SHALL support `strategy: "auto"` by iterating through the node's `fallback_chain`, returning the first strategy instance where `check_available()` returns `True`. It SHALL NOT call `execute()`.

#### Scenario: Auto mode selects first available strategy
- **WHEN** `config.strategy == "auto"` and `fallback_chain == ["algorithm", "neural"]`
- **AND** `AlgorithmStrategy.check_available()` returns `True`
- **THEN** `get_strategy()` returns an instance of `AlgorithmStrategy` without calling `execute()`

#### Scenario: Auto mode skips unavailable strategies during selection
- **WHEN** `config.strategy == "auto"` and `fallback_chain == ["algorithm", "neural"]`
- **AND** `AlgorithmStrategy.check_available()` returns `False`
- **THEN** `get_strategy()` skips `AlgorithmStrategy` and returns `NeuralStrategy` (if available)

#### Scenario: Auto mode selection fails when none available
- **WHEN** `config.strategy == "auto"` and all strategies in `fallback_chain` return `check_available() == False`
- **THEN** `get_strategy()` SHALL raise `RuntimeError` listing all strategies with reason `"unavailable (check returned False)"`

#### Scenario: Auto mode without fallback_chain raises error
- **WHEN** `config.strategy == "auto"` but `descriptor.fallback_chain` is empty
- **THEN** `get_strategy()` SHALL raise `ValueError` indicating no fallback chain is configured

### Requirement: execute_with_fallback() executes with retry (execution layer)

`NodeContext` SHALL provide an `execute_with_fallback()` instance method (no parameters beyond `self`) that combines strategy selection and execution. In `auto` mode, it SHALL **independently iterate** the `fallback_chain` (not delegate to `get_strategy()`), calling `check_available()` and `execute()` on each strategy. The first successful `execute()` SHALL return the result. In non-auto mode, it SHALL directly call `get_strategy().execute(self)`.

#### Scenario: Auto mode executes first available strategy successfully
- **WHEN** `ctx.execute_with_fallback()` is called with `config.strategy == "auto"`
- **AND** the first available strategy's `execute()` succeeds
- **THEN** the result of that `execute()` SHALL be returned
- **AND** no fallback is triggered

#### Scenario: Auto mode falls back on execute failure
- **WHEN** `ctx.execute_with_fallback()` is called with `config.strategy == "auto"`
- **AND** `AlgorithmStrategy.execute()` raises an exception
- **THEN** the system SHALL attempt `NeuralStrategy` (next in `fallback_chain`)
- **AND** if `NeuralStrategy.check_available()` returns `True` and `execute()` succeeds, return that result

#### Scenario: Auto mode exhausts all strategies
- **WHEN** `ctx.execute_with_fallback()` is called and all strategies in `fallback_chain` either fail `check_available()` or raise during `execute()`
- **THEN** `RuntimeError` SHALL be raised listing all attempted strategies and their failure reasons
- **AND** failure reasons SHALL include `"unavailable (check returned False)"` for `check_available()` failures and exception messages for `execute()` failures

#### Scenario: Non-auto mode delegates directly
- **WHEN** `ctx.execute_with_fallback()` is called with `config.strategy == "algorithm"` (not "auto")
- **THEN** it SHALL call `get_strategy().execute(self)` directly without fallback logic

### Requirement: Fallback events are traced

When auto fallback occurs, the system SHALL record the fallback event in `node_trace` for observability. Fallback trace information SHALL be stored in `NodeContext` internal state and **merged into** the `_wrap_node()` trace entry (not appended as a separate entry), ensuring each node produces exactly one `node_trace` record.

#### Scenario: Successful fallback recorded in trace
- **WHEN** auto mode falls back from `"algorithm"` to `"neural"` due to algorithm failure
- **THEN** the single `node_trace` entry for this node SHALL include `"fallback_triggered": true`
- **AND** `"strategies_attempted": [{"name": "algorithm", "error": "<reason>"}, {"name": "neural", "result": "success"}]`

#### Scenario: No fallback recorded when first strategy succeeds
- **WHEN** auto mode succeeds with the first strategy in `fallback_chain`
- **THEN** the single `node_trace` entry SHALL include `"fallback_triggered": false`
- **AND** `"strategy_used": "algorithm"`

### Requirement: Explicit strategy selection unchanged

Existing behavior for explicit strategy selection (`strategy: "algorithm"` or `strategy: "neural"`) SHALL remain unchanged.

#### Scenario: Explicit strategy selection works as before
- **WHEN** `config.strategy == "algorithm"` (not "auto")
- **THEN** `get_strategy()` behaves identically to current implementation: look up in `strategies`, instantiate, check_available, return

#### Scenario: Explicit neural strategy fails if unavailable
- **WHEN** `config.strategy == "neural"` and `NeuralStrategy.check_available()` returns `False`
- **THEN** `get_strategy()` SHALL raise `RuntimeError` (same as current behavior)
