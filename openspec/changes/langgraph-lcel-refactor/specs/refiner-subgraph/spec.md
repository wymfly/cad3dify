## ADDED Requirements

### Requirement: SmartRefiner modeled as LangGraph subgraph

The system SHALL implement a `build_refiner_subgraph()` function in `backend/graph/subgraphs/refiner.py` that returns a compiled `CompiledStateGraph` modeling the Compare→Fix→Re-execute→Re-render cycle as a LangGraph subgraph with up to `max_rounds` iterations.

#### Scenario: Subgraph executes one refinement round
- **WHEN** the subgraph is invoked with `RefinerState` containing code, step_path, drawing_spec, image_path, and `round=0, max_rounds=3`
- **THEN** the subgraph SHALL execute: `static_diagnose → render_for_compare → vl_compare → route_verdict`
- **AND** if verdict is "fail" and round < max_rounds: `coder_fix → re_execute → render_for_compare → vl_compare → route_verdict` (loop)
- **AND** if verdict is "pass": exit subgraph

#### Scenario: Subgraph loop includes re-render between rounds
- **WHEN** `coder_fix` produces new code and `re_execute` generates a new STEP file
- **THEN** `render_for_compare` SHALL re-render the new STEP to PNG before the next `vl_compare`
- **AND** `rendered_image_path` in RefinerState SHALL be updated with the new render path
- **AND** the previous render SHALL NOT be reused (stale render after code fix)

#### Scenario: Subgraph exits after max rounds
- **WHEN** `round >= max_rounds` after a "fail" verdict
- **THEN** the subgraph SHALL exit with the current code (best effort)
- **AND** the final `verdict` SHALL be "max_rounds_reached"

#### Scenario: Subgraph dispatches SSE events per round
- **WHEN** each refinement round begins
- **THEN** the `vl_compare` node SHALL dispatch `job.refining` SSE event with `{"round": N, "max_rounds": M, "status": "comparing"}`
- **AND** the `coder_fix` node SHALL dispatch `job.refining` with `{"round": N, "status": "fixing"}`

#### Scenario: Checkpoint granularity is subgraph-level
- **WHEN** the subgraph is invoked via `refiner_subgraph.ainvoke(state, config=config)` from within `generate_step_drawing_node`
- **THEN** the checkpoint boundary SHALL be the subgraph invocation as a whole (not per internal node)
- **AND** if the process crashes during subgraph execution, recovery SHALL restart from `generate_step_drawing_node` entry (not from an internal subgraph node)
- **NOTE** Per-round crash recovery (e.g., resume from `coder_fix` after `vl_compare`) is a future enhancement requiring the subgraph to be promoted to a first-class node in the main graph

### Requirement: RefinerState is independent of CadJobState

The system SHALL define `RefinerState` as an independent `TypedDict` with explicit fields, mapped to/from `CadJobState` via helper functions at subgraph entry/exit.

#### Scenario: RefinerState includes all fields for loop correctness
- **WHEN** `RefinerState` is defined
- **THEN** it SHALL include:
  - `code: str` — current CadQuery code
  - `step_path: str` — STEP file path
  - `drawing_spec: dict` — drawing spec as dict (converted from DrawingSpec at entry)
  - `image_path: str` — original drawing image path
  - `round: int` — current round number
  - `max_rounds: int` — maximum rounds
  - `verdict: str` — "pending" | "pass" | "fail" | "max_rounds_reached"
  - `static_notes: list[str]` — Layer 1/2 diagnostic notes
  - `comparison_result: str | None` — VL comparison output (persisted for coder_fix to use)
  - `rendered_image_path: str | None` — current round's rendered PNG path
  - `prev_score: float | None` — previous round's geometry score (for rollback detection)

#### Scenario: State mapping at subgraph entry with type conversion
- **WHEN** `generate_step_drawing_node` invokes the refiner subgraph
- **THEN** it SHALL construct `RefinerState` from `CadJobState` fields: `generated_code → code`, `step_path → step_path`, `drawing_spec → drawing_spec`, `image_path → image_path`
- **AND** `drawing_spec` SHALL be converted via `spec.model_dump()` if it is a `DrawingSpec` object (not already a dict)
- **AND** set `round=0`, `max_rounds=config.max_refinements`, `verdict="pending"`, `comparison_result=None`, `rendered_image_path=None`, `prev_score=None`

#### Scenario: State mapping at subgraph exit
- **WHEN** the refiner subgraph completes
- **THEN** the caller SHALL extract `RefinerState["code"]` as the refined code
- **AND** if `verdict == "pass"`, the code is final
- **AND** if `verdict == "max_rounds_reached"`, the code is best-effort

### Requirement: Static diagnosis node provides Layer 1/2/2.5 diagnostics

The system SHALL implement a `static_diagnose` node within the refiner subgraph that runs Layer 1 (parameter validation), Layer 2 (bounding box), and Layer 2.5 (topology, if enabled via config) checks, storing results in `RefinerState["static_notes"]`.

#### Scenario: Static diagnosis with valid STEP and type-safe validator call
- **WHEN** `static_diagnose` runs with a valid STEP file
- **THEN** it SHALL reconstruct `DrawingSpec` from `state["drawing_spec"]` dict via `DrawingSpec(**state["drawing_spec"])` before calling `validate_code_params(code, spec)`
- **AND** it SHALL populate `static_notes` with any mismatches from `validate_code_params()`, `validate_bounding_box()`, and optionally `compare_topology()` (based on `config["configurable"]["pipeline_config"].topology_check`)
- **AND** it SHALL NOT make any LLM calls

#### Scenario: Static diagnosis with missing STEP
- **WHEN** `static_diagnose` runs but the STEP file does not exist
- **THEN** `static_notes` SHALL be empty
- **AND** the subgraph SHALL continue to `render_for_compare` (diagnosis is advisory only)

### Requirement: Rollback tracking within subgraph

The system SHALL integrate `RollbackTracker` within the refiner subgraph to detect score degradation after each fix round, using `prev_score` in RefinerState.

#### Scenario: Code fix degrades geometry score
- **WHEN** `re_execute` node completes and the new geometry score is lower than `state["prev_score"]`
- **THEN** the subgraph SHALL rollback to the previous round's code
- **AND** dispatch `job.refining` SSE event with `{"round": N, "status": "rollback"}`
- **AND** re-execute the rolled-back code to restore the STEP file

#### Scenario: Code fix improves or maintains score
- **WHEN** `re_execute` node completes and the geometry score is >= `state["prev_score"]`
- **THEN** the subgraph SHALL update `prev_score` with the new score, accept the new code, and continue to the next round or exit

### Requirement: PipelineConfig accessible via LangGraph configurable

The system SHALL access `PipelineConfig` parameters within the refiner subgraph via `config["configurable"]["pipeline_config"]`, supporting:
- `rollback_on_degrade` → whether RollbackTracker is enabled
- `structured_feedback` → text vs structured VL feedback mode
- `topology_check` → whether to run topology comparison in static_diagnose
- `multi_view_render` → multi-view vs single-view rendering

#### Scenario: Subgraph uses structured feedback when configured
- **WHEN** `pipeline_config.structured_feedback` is True
- **THEN** `vl_compare` node SHALL use `build_compare_chain(structured=True)`
- **AND** PASS detection SHALL use `feedback.passed` boolean (not text heuristic)
