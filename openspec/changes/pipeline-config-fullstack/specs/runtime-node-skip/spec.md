## ADDED Requirements

### Requirement: Runtime node skip via pipeline_config state

The system SHALL compile all registered nodes into the LangGraph graph regardless of their `enabled` state, and SHALL skip disabled nodes at runtime by checking `state["pipeline_config"][node_name]["enabled"]` in the `_wrap_node()` wrapper. When a node is skipped, it SHALL return an empty dict without executing any logic.

#### Scenario: Node disabled in pipeline_config skips at runtime
- **WHEN** a Job is created with `pipeline_config={"mesh_repair": {"enabled": false}}`
- **THEN** the graph contains the `mesh_repair` node (compiled in)
- **AND** when execution reaches `mesh_repair`, `_wrap_node()` detects `enabled=false`
- **AND** the node returns `{}` without executing its strategy
- **AND** a log message "Node mesh_repair skipped (disabled)" is emitted at INFO level

#### Scenario: Node enabled by default when not specified
- **WHEN** a Job is created with `pipeline_config={}` (empty config)
- **THEN** all nodes execute normally (enabled defaults to `true`)

#### Scenario: Resolver no longer filters by enabled
- **WHEN** `DependencyResolver.resolve_all()` is called with `pipeline_config={"mesh_repair": {"enabled": false}}`
- **THEN** `mesh_repair` is still included in the resolved node list
- **AND** the graph topology includes `mesh_repair` with its edges intact

### Requirement: Validate endpoint respects enabled for preview

The `POST /api/v1/pipeline/validate` endpoint SHALL still filter by `enabled` when computing the preview topology, showing the user which nodes would actually execute.

#### Scenario: Validate shows effective topology excluding disabled nodes
- **WHEN** `POST /pipeline/validate` is called with `config={"mesh_repair": {"enabled": false}}`
- **THEN** the response `topology` list does NOT include `mesh_repair`
- **AND** the response `valid` field reflects whether the remaining topology is viable
