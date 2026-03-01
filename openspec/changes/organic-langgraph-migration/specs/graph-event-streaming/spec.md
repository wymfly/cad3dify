## ADDED Requirements

### Requirement: Organic-specific SSE events follow job.* naming convention

The system SHALL dispatch organic-specific SSE events using the established `job.<stage>` naming convention, with payloads conforming to the standard envelope format.

#### Scenario: Organic spec ready event dispatched
- **WHEN** `analyze_organic_node` completes spec building
- **THEN** the event name is `job.organic_spec_ready`
- **AND** the payload contains `job_id`, `organic_spec` (full spec dict), `status`

#### Scenario: Post-processing step events dispatched
- **WHEN** `postprocess_organic_node` executes each sub-step
- **THEN** the event name is `job.post_processing`
- **AND** the payload contains `job_id`, `step` (one of: load, repair, scale, boolean, validate), `step_status` (running, success, degraded, skipped, failed), `message`, `progress`

#### Scenario: Mesh generation progress event
- **WHEN** `generate_organic_mesh_node` starts mesh generation
- **THEN** the event name is `job.generating` with `stage="mesh_generation"`

## MODIFIED Requirements

### Requirement: Canonical SSE event naming schema

The system SHALL use the `job.<stage>` naming convention for all SSE events, with a fixed envelope payload `{job_id, event, stage?, message, data?, ts}`.

#### Scenario: Standard event envelope emitted
- **WHEN** any Graph node dispatches a custom event
- **THEN** the SSE payload SHALL contain: `job_id` (string), `event` (string matching `job.<stage>`), `message` (human-readable string), `ts` (ISO-8601 UTC timestamp)
- **AND** MAY include `stage` (sub-stage string) and `data` (arbitrary JSON object)

#### Scenario: Lifecycle events use canonical names
- **WHEN** `create_job_node` completes
- **THEN** the event name is `job.created` (NOT `job_created`)
- **WHEN** `analyze_intent_node` completes
- **THEN** the event name is `job.intent_analyzed` (NOT `intent_parsed`)
- **WHEN** `analyze_vision_node` starts
- **THEN** the event name is `job.vision_analyzing` (NOT `analyzing`)
- **WHEN** `analyze_organic_node` completes
- **THEN** the event name is `job.organic_spec_ready`
- **WHEN** `postprocess_organic_node` executes a sub-step
- **THEN** the event name is `job.post_processing`
- **WHEN** `finalize_node` succeeds
- **THEN** the event name is `job.completed` (NOT `completed`)
- **WHEN** any node fails
- **THEN** the event name is `job.failed` (NOT `failed`)

#### Scenario: Old event names no longer emitted
- **WHEN** the codebase is audited after migration
- **THEN** SSE events with names `job_created`, `intent_parsed`, `analyzing`, `drawing_spec_ready`, `generating`, `refining`, `completed`, `failed` (bare, without `job.` prefix) MUST NOT be emitted by any backend code
- **AND** SSE events with the `event: "organic"` type (legacy organic pipeline) MUST NOT be emitted
