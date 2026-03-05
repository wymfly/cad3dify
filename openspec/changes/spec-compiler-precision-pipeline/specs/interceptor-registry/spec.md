## ADDED Requirements

### Requirement: InterceptorRegistry allows build-time node insertion

The system SHALL provide an `InterceptorRegistry` at `backend/graph/interceptors.py` that allows registering post-processing nodes to be inserted into the StateGraph at build time.

#### Scenario: Register and insert a watermark interceptor
- **WHEN** `InterceptorRegistry.register("watermark", watermark_node, after="convert_preview")` is called before `_build_workflow()`
- **THEN** the built workflow includes a `watermark` node between `convert_preview` and `check_printability`
- **AND** the edge from `convert_preview` connects to `watermark` instead of `check_printability`
- **AND** `watermark` connects to `check_printability`

#### Scenario: No interceptors registered preserves default topology
- **WHEN** no interceptors are registered
- **THEN** `_build_workflow()` produces the same graph topology as the current hardcoded version
- **AND** all existing tests pass without modification

#### Scenario: Multiple interceptors registered in sequence
- **WHEN** two interceptors are registered: `interceptor_a` after `convert_preview` and `interceptor_b` after `interceptor_a`
- **THEN** the chain becomes `convert_preview → interceptor_a → interceptor_b → check_printability`

### Requirement: Interceptor nodes follow standard node signature

Each interceptor node function SHALL accept `CadJobState` and return `dict[str, Any]`, following the same signature as all other graph nodes.

#### Scenario: Interceptor receives full state
- **WHEN** an interceptor node executes
- **THEN** it receives the full `CadJobState` including `step_path`, `model_url`, and `printability`
- **AND** it can return state updates that are merged into the graph state
