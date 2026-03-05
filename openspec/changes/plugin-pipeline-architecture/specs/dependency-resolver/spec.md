## ADDED Requirements

### Requirement: Resolve pipeline topology from enabled nodes
`DependencyResolver.resolve()` SHALL accept a `NodeRegistry`, a set of enabled node names, and an `input_type`, and return a `ResolvedPipeline` with topologically sorted nodes.

#### Scenario: Basic text pipeline resolution
- **WHEN** resolver is called with enabled nodes `{create_job, analyze_intent, confirm_with_user, generate_step_text, convert_preview, finalize}` and `input_type="text"`
- **THEN** `ResolvedPipeline.ordered_nodes` contains these nodes in dependency order: create_job before analyze_intent, analyze_intent before confirm_with_user, etc.

### Requirement: Filter nodes by input_type
The resolver SHALL exclude nodes whose `input_types` list does not contain the current `input_type`.

#### Scenario: Organic nodes excluded for text input
- **WHEN** resolver is called with `input_type="text"` and enabled nodes include `generate_organic_mesh`
- **THEN** `generate_organic_mesh` is excluded from the resolved pipeline (its `input_types=["organic"]`)

### Requirement: Dependency validation — missing producer
The resolver SHALL raise an error if an enabled node requires an asset key that no other enabled node produces.

#### Scenario: Missing dependency error
- **WHEN** `slice_to_gcode` (requires `watertight_mesh`) is enabled but no node producing `watertight_mesh` is enabled
- **THEN** resolver raises an error with message containing "slice_to_gcode requires watertight_mesh" and listing nodes that could produce it

### Requirement: OR dependency support
The resolver SHALL support OR dependencies: `requires=[["a", "b"]]` means the node needs asset `a` OR asset `b`. The dependency is satisfied if at least one asset in the OR group has a producer among enabled nodes.

#### Scenario: OR dependency satisfied
- **WHEN** `check_printability` has `requires=[["step_model", "watertight_mesh"]]` and only `generate_step_text` (produces `step_model`) is enabled
- **THEN** the dependency is satisfied via `step_model`

#### Scenario: OR dependency unsatisfied
- **WHEN** `check_printability` has `requires=[["step_model", "watertight_mesh"]]` and neither producer is enabled
- **THEN** resolver raises an error listing both possible producers

### Requirement: Conflict detection — duplicate producers
The resolver SHALL raise an error if two enabled nodes (after input_type filtering) produce the same asset key.

#### Scenario: Duplicate producer conflict
- **WHEN** `generate_step_text` and `generate_step_drawing` are both enabled and both produce `step_model`, and `input_type="text"` does not filter out `generate_step_drawing` (hypothetical)
- **THEN** resolver raises a conflict error

### Requirement: HITL interrupt points
`ResolvedPipeline.interrupt_before` SHALL contain the names of all nodes with `supports_hitl=True`.

#### Scenario: Confirm node in interrupt list
- **WHEN** `confirm_with_user` has `supports_hitl=True`
- **THEN** `resolved.interrupt_before` contains `"confirm_with_user"`

### Requirement: ResolvedPipeline validation
`ResolvedPipeline.validate()` SHALL verify: no cycles in the DAG, all requires are satisfied, no duplicate producers. It returns a list of warnings (non-fatal issues like OR ambiguity).

#### Scenario: Valid pipeline
- **WHEN** `validate()` is called on a correctly resolved pipeline
- **THEN** it returns an empty list (no warnings)
