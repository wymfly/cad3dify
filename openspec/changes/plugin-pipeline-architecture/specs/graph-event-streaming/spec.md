## MODIFIED Requirements

### Requirement: node.completed events include node_trace data
`node.completed` SSE events SHALL include a `node_trace` field containing: `node` name, `elapsed_ms`, `reasoning` dict, `outputs_summary` dict, and `assets_produced` (list of asset keys written by this node).

#### Scenario: Enriched node.completed event
- **WHEN** `analyze_dfam` completes successfully
- **THEN** the `node.completed` SSE event payload includes `assets_produced: ["dfam_glb"]` in addition to existing `elapsed_ms` and `reasoning` fields

### Requirement: Pipeline topology in job events
`job.created` SSE event SHALL include `pipeline_topology` (ordered list of node names that will execute) so the frontend can render the DAG before execution starts.

#### Scenario: Frontend receives topology at job start
- **WHEN** `job.created` event is dispatched
- **THEN** the payload includes `pipeline_topology: ["create_job", "analyze_intent", "confirm_with_user", ...]`
