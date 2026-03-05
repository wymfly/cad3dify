## ADDED Requirements

### Requirement: Dynamic graph generation from ResolvedPipeline
`PipelineBuilder.build()` SHALL accept a `ResolvedPipeline` and return a `StateGraph` with all resolved nodes registered and edges wired according to the dependency topology.

#### Scenario: Build a simple pipeline
- **WHEN** `build()` is called with a ResolvedPipeline containing `[create_job, analyze_intent, confirm_with_user, generate_step_text, finalize]`
- **THEN** the returned StateGraph has 5 nodes with edges matching the dependency order

### Requirement: Node function wrapping
`PipelineBuilder` SHALL wrap each node function (which accepts `NodeContext`) into a LangGraph-compatible function (which accepts `PipelineState` and returns `dict`). The wrapper SHALL: construct `NodeContext.from_state()`, call the original function, return `ctx.to_state_diff()`.

#### Scenario: Wrapped node execution
- **WHEN** a wrapped node function is called with a `PipelineState`
- **THEN** the original node function receives a `NodeContext` and the state diff is returned

### Requirement: timed_node lifecycle events preserved
Each wrapped node SHALL be decorated with `@timed_node(node_name)` to emit `node.started`, `node.completed`, `node.failed` SSE events with timing and reasoning metadata.

#### Scenario: Node lifecycle events
- **WHEN** a node executes successfully
- **THEN** `node.started` and `node.completed` events are dispatched with `job_id`, `node` name, and `elapsed_ms`

### Requirement: HITL interrupt_before wiring
`PipelineBuilder` SHALL pass `resolved.interrupt_before` to `graph.compile(interrupt_before=...)` so LangGraph pauses before HITL nodes.

#### Scenario: Graph pauses before confirm
- **WHEN** the compiled graph reaches `confirm_with_user` (which has `supports_hitl=True`)
- **THEN** execution pauses and waits for `Command(resume=...)` input

### Requirement: Conditional edges for branching
For nodes where multiple successors exist (e.g., after `create_job` routing to different analysis nodes by input_type), `PipelineBuilder` SHALL generate `add_conditional_edges` with a routing function based on `state["input_type"]`.

#### Scenario: Input type routing
- **WHEN** `create_job` completes with `input_type="organic"`
- **THEN** the graph routes to `analyze_organic` (not `analyze_intent` or `analyze_vision`)
