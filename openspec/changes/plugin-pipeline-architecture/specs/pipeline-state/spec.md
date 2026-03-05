## ADDED Requirements

### Requirement: PipelineState structure
`PipelineState` SHALL be a `TypedDict` with fields: `job_id` (str), `input_type` (str), `assets` (dict[str, dict]), `data` (dict[str, Any]), `pipeline_config` (dict[str, dict]), `status` (str), `error` (str|None), `failure_reason` (str|None), `node_trace` (Annotated[list[dict], operator.add]).

#### Scenario: State initialization
- **WHEN** a new pipeline execution starts
- **THEN** `PipelineState` is initialized with `job_id`, `input_type`, empty `assets` and `data` dicts, `pipeline_config` from user request, `status="created"`, and empty `node_trace`

### Requirement: AssetRegistry
`AssetRegistry` SHALL provide `put(key, path, format, metadata)`, `get(key) -> AssetEntry`, `has(key) -> bool`, `to_dict() -> dict`, and `from_dict(d) -> AssetRegistry` methods. Each `AssetEntry` contains `key`, `path`, `format`, `producer`, and optional `metadata`.

#### Scenario: Put and get an asset
- **WHEN** `registry.put("step_model", "/path/to/model.step", format="step")` is called
- **THEN** `registry.get("step_model")` returns an `AssetEntry` with `path="/path/to/model.step"` and `format="step"`

#### Scenario: Serialize and deserialize
- **WHEN** `registry.to_dict()` is called after putting assets, then `AssetRegistry.from_dict(d)` is called with the result
- **THEN** the reconstructed registry contains identical assets

### Requirement: NodeContext as PipelineState view
`NodeContext` SHALL provide `get_asset()`, `put_asset()`, `has_asset()`, `get_data()`, `put_data()`, `config`, `get_strategy()`, `dispatch()`, `dispatch_progress()`. It is constructed from `PipelineState` via `NodeContext.from_state()` and produces a state diff via `to_state_diff()`.

#### Scenario: Node reads upstream asset
- **WHEN** a node calls `ctx.get_asset("step_model")`
- **THEN** it receives the `AssetEntry` written by the upstream node that produced `step_model`

#### Scenario: Node writes asset and produces state diff
- **WHEN** a node calls `ctx.put_asset("preview_glb", "/path/to/model.glb", format="glb")`
- **THEN** `ctx.to_state_diff()` returns a dict containing `{"assets": {..., "preview_glb": {"path": "...", "format": "glb"}}}`

#### Scenario: Node config loaded from pipeline_config
- **WHEN** `NodeContext.from_state(state, desc)` is called and `state["pipeline_config"]["analyze_dfam"]` contains `{"strategy": "sampling", "threshold": 2.0}`
- **THEN** `ctx.config` is an instance of `DfamConfig` with `strategy="sampling"` and `threshold=2.0`

#### Scenario: Strategy instantiation
- **WHEN** `ctx.get_strategy()` is called and `ctx.config.strategy == "scipy"`
- **THEN** it returns an instance of the strategy class registered under `"scipy"` in the node's descriptor

### Requirement: node_trace append-only
`node_trace` SHALL use `Annotated[list[dict], operator.add]` to ensure each node's trace entry is appended, never overwritten.

#### Scenario: Multiple nodes append traces
- **WHEN** node A and node B each return `{"node_trace": [{"node": "A", ...}]}` and `{"node_trace": [{"node": "B", ...}]}`
- **THEN** the final `state["node_trace"]` contains both entries in execution order
