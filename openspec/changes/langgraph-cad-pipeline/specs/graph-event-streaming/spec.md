## ADDED Requirements

### Requirement: adispatch_custom_event replaces global event queues

The system SHALL eliminate the global `_event_queues: dict[str, Queue]` dictionary and replace it with `langgraph.utils.events.adispatch_custom_event(name, data)` called from inside Graph nodes.

#### Scenario: Node dispatches progress event
- **WHEN** `analyze_vision_node` completes DrawingSpec extraction
- **THEN** the node calls `await adispatch_custom_event("job.spec_ready", {"job_id": ..., "drawing_spec": ...})`
- **AND** the event is automatically associated with the current Graph run context

#### Scenario: Event lifecycle tied to Graph Run
- **WHEN** a Graph run ends (either completed or failed)
- **THEN** all custom events from that run are automatically garbage-collected
- **AND** `cleanup_queue()` is NOT called (it does not exist)
- **AND** no memory accumulates from terminated runs

#### Scenario: _event_queues no longer exists
- **WHEN** the codebase is audited after migration
- **THEN** `_event_queues` MUST NOT appear in any source file
- **AND** `emit_event()`, `cleanup_queue()`, and `PipelineBridge` MUST NOT appear in any source file

### Requirement: API layer receives events via astream_events pull model

The system SHALL pull Graph events from `graph.astream_events(config=config, version="v2")` in the SSE endpoint generator, filtering for `on_custom_event` type.

#### Scenario: SSE endpoint filters events by type
- **WHEN** the API SSE generator iterates `graph.astream_events()`
- **THEN** only events where `event["event"] == "on_custom_event"` are forwarded to the HTTP response
- **AND** internal LangGraph lifecycle events (`on_chain_start`, `on_llm_end`, etc.) are silently discarded

#### Scenario: Client disconnect terminates event stream
- **WHEN** an SSE client disconnects (HTTP connection closed)
- **THEN** the `async for` loop in the SSE generator terminates
- **AND** no further Graph events are consumed
- **AND** the Graph run itself is cancelled via the generator's `aclose()` call

#### Scenario: Multiple concurrent jobs use separate streams
- **WHEN** two different Job IDs are created concurrently
- **THEN** each Graph run uses its own `thread_id` (= `job_id`) config
- **AND** events from Job A are never delivered to the SSE stream of Job B
- **AND** no cross-contamination occurs (no shared global queue)

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
- **WHEN** `finalize_node` succeeds
- **THEN** the event name is `job.completed` (NOT `completed`)
- **WHEN** any node fails
- **THEN** the event name is `job.failed` (NOT `failed`)

#### Scenario: Old event names no longer emitted
- **WHEN** the codebase is audited after migration
- **THEN** SSE events with names `job_created`, `intent_parsed`, `analyzing`, `drawing_spec_ready`, `generating`, `refining`, `completed`, `failed` (bare, without `job.` prefix) MUST NOT be emitted by any backend code
