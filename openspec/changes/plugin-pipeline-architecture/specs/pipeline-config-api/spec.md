## ADDED Requirements

### Requirement: List all registered nodes
`GET /api/v1/pipeline/nodes` SHALL return all registered node descriptors including: name, display_name, requires, produces, input_types, strategies (with availability), config schema (JSON Schema from Pydantic model), description, estimated_duration, is_entry, supports_hitl, non_fatal.

#### Scenario: Nodes endpoint returns full metadata
- **WHEN** `GET /api/v1/pipeline/nodes` is called
- **THEN** response contains an array of node descriptors, each with strategy availability info and JSON Schema for its config model

### Requirement: Validate pipeline configuration
`POST /api/v1/pipeline/validate` SHALL accept `{input_type, config}` and return the validation result: whether the config is valid, the resolved ordered node list, and any errors or warnings.

#### Scenario: Valid configuration
- **WHEN** a valid config with all dependencies satisfied is posted
- **THEN** response contains `{valid: true, ordered_nodes: [...], warnings: []}`

#### Scenario: Invalid configuration — missing dependency
- **WHEN** a config enables `slice_to_gcode` without any node producing `watertight_mesh`
- **THEN** response contains `{valid: false, errors: ["slice_to_gcode requires watertight_mesh..."]}`

### Requirement: List pipeline presets
`GET /api/v1/pipeline/presets` SHALL return all defined presets with their per-node configurations.

#### Scenario: Presets endpoint
- **WHEN** `GET /api/v1/pipeline/presets` is called
- **THEN** response contains preset objects (fast, balanced, full_print) each with node-level config overrides

### Requirement: Backward-compatible pipeline_config in job creation
`POST /api/v1/jobs` SHALL accept both old format (`{"preset": "balanced", "best_of_n": 3}`) and new format (`{"preset": "balanced", "nodes": {...}}`). Old format SHALL be auto-converted via a migration function.

#### Scenario: Old format auto-converted
- **WHEN** `POST /api/v1/jobs` receives `{"pipeline_config": {"preset": "balanced", "best_of_n": 3}}`
- **THEN** the system converts it to the new per-node format and proceeds normally

#### Scenario: New format accepted
- **WHEN** `POST /api/v1/jobs` receives `{"pipeline_config": {"nodes": {"analyze_dfam": {"enabled": true, "strategy": "raycast"}}}}`
- **THEN** the system uses the config directly without conversion

### Requirement: Job response includes pipeline topology
`GET /api/v1/jobs/{id}` response SHALL include `pipeline_topology` (ordered list of node names executed) and `node_trace` (per-node execution records with timing and reasoning).

#### Scenario: Job with topology info
- **WHEN** a completed job is fetched via `GET /api/v1/jobs/{id}`
- **THEN** response includes `pipeline_topology: ["create_job", "analyze_intent", ...]` and `node_trace: [{"node": "create_job", "elapsed_ms": 100, ...}, ...]`
