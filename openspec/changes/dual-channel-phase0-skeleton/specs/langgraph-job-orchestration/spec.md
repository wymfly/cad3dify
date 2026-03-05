## MODIFIED Requirements

### Requirement: Unified StateGraph manages CAD Job lifecycle

The system SHALL implement a single `CadJobStateGraph` using LangGraph `StateGraph` to orchestrate the complete lifecycle (create → analyze → HITL → generate → postprocess → complete) for all three input types: text, drawing, and organic.

The new builder (`PipelineBuilder` in `builder_new.py`) SHALL be the default graph builder (`USE_NEW_BUILDER=1`). The legacy builder (`builder.py`) SHALL be renamed to `builder_legacy.py` and marked as deprecated.

#### Scenario: Text job flows through intent analysis
- **WHEN** a POST /api/v1/jobs request arrives with `input_type=text`
- **THEN** the Graph executes `create_job_node` → `analyze_intent_node` → `confirm_with_user_node`
- **AND** each node transition is persisted to `AsyncSqliteSaver` checkpoint before proceeding

#### Scenario: Drawing job flows through vision analysis
- **WHEN** a POST /api/v1/jobs/upload request arrives with `input_type=drawing`
- **THEN** the Graph executes `create_job_node` → `analyze_vision_node` → `confirm_with_user_node`
- **AND** `analyze_vision_node` wraps `analyze_vision_spec()` via `asyncio.to_thread`

#### Scenario: Organic job skips analysis
- **WHEN** a POST /api/v1/jobs request arrives with `input_type=organic`
- **THEN** the Graph executes `create_job_node` → `stub_organic_node` → `confirm_with_user_node` directly
- **AND** no LLM analysis is performed before presenting confirmation

> **Note**: Current implementation routes organic through `analyze_organic → generate_organic_mesh → postprocess_organic` (see `builder.py`). The scenario above describes the target design. This change does NOT modify the organic path — discrepancy is pre-existing.

#### Scenario: Post-confirm generation routes by type
- **WHEN** `confirm_with_user_node` resumes after user confirmation
- **THEN** the Graph routes to `generate_step_text_node` for text input or `generate_step_drawing_node` for drawing input
- **AND** both paths converge at `convert_preview_node` → `check_printability_node` → `finalize_node`

#### Scenario: Organic post-confirm exits Graph for legacy processing
- **WHEN** `confirm_with_user_node` resumes for an organic input type
- **THEN** `route_after_confirm` returns `"organic_external"`
- **AND** the Graph routes to `finalize_node` which marks the Job in DB as `confirmed` (not `completed`)
- **AND** the actual organic generation is delegated to the legacy `/api/generate/organic` endpoint (outside the Graph)
- **AND** a `job.organic_delegated` SSE event is dispatched before the Graph run ends

#### Scenario: Shared postprocess nodes execute once
- **WHEN** either `generate_step_text_node` or `generate_step_drawing_node` completes
- **THEN** `convert_step_to_preview()` runs exactly once to produce the GLB file
- **AND** `check_printability()` runs exactly once to produce the DfAM report
- **AND** `finalize_node` updates DB to COMPLETED and closes the stream

#### Scenario: New builder supports interceptor insertion
- **WHEN** `PipelineBuilder.build()` is called and `InterceptorRegistry` contains registered interceptors
- **THEN** interceptor nodes SHALL be inserted between `convert_preview` and `check_printability`
- **AND** the interceptor chain SHALL behave identically to the legacy builder's interceptor support for the `after="convert_preview"` insertion point (the only insertion point currently used)

#### Scenario: New builder is default with legacy fallback
- **WHEN** the application starts without `USE_NEW_BUILDER` environment variable set
- **THEN** `USE_NEW_BUILDER` SHALL default to `"1"` (new builder)
- **AND** setting `USE_NEW_BUILDER=0` SHALL activate the legacy builder (deprecated)

#### Scenario: Legacy builder accessible via re-export wrapper
- **WHEN** the legacy builder code is moved to `builder_legacy.py`
- **THEN** `builder.py` SHALL remain as a re-export wrapper with `@deprecated` marker
- **AND** all existing `from backend.graph.builder import ...` imports SHALL continue to work
- **AND** importing from `builder.py` SHALL emit a deprecation warning
