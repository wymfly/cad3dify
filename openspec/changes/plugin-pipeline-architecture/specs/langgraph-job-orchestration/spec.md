## MODIFIED Requirements

### Requirement: Graph construction uses dynamic builder
The LangGraph StateGraph SHALL be constructed dynamically by `PipelineBuilder` from a `ResolvedPipeline`, instead of being hand-coded in `builder.py`. The graph topology is determined at compile time based on enabled nodes and their dependency relationships.

#### Scenario: Dynamic graph matches resolved pipeline
- **WHEN** `PipelineBuilder.build(resolved)` is called with a resolved pipeline of 10 nodes
- **THEN** the compiled StateGraph contains exactly those 10 nodes with edges matching the resolved dependency order

#### Scenario: Different configs produce different graphs
- **WHEN** config A enables `{create_job, analyze_intent, confirm, generate_step_text, finalize}` and config B additionally enables `{check_printability, analyze_dfam}`
- **THEN** the two compiled graphs have different node counts and edge topologies

### Requirement: State model is PipelineState
The graph SHALL use `PipelineState` (with `assets`, `data`, `pipeline_config`, `node_trace` fields) instead of the legacy `CadJobState` with 25+ scattered fields. A compatibility layer SHALL handle migration of existing data.

#### Scenario: Assets stored in dict
- **WHEN** `generate_step_text` produces a STEP file
- **THEN** the path is stored in `state["assets"]["step_model"]` (not `state["step_path"]`)

#### Scenario: Legacy state compat
- **WHEN** old checkpoint data with `CadJobState` format is encountered
- **THEN** `compat.py` migration function converts it to `PipelineState` format

### Requirement: Finalize node collects from assets registry
`finalize` node SHALL read all produced assets from `state["assets"]` and semantic data from `state["data"]` to assemble the ORM `result` JSON, instead of hard-coding field names per input_type.

#### Scenario: Finalize assembles result from assets
- **WHEN** finalize runs with `assets={"step_model": {...}, "preview_glb": {...}, "printability_report": {...}}`
- **THEN** the ORM `result` JSON contains URLs/paths for all produced assets
