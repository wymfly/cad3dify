## MODIFIED Requirements

### Requirement: Unified StateGraph manages CAD Job lifecycle

The system SHALL implement a single `CadJobStateGraph` using LangGraph `StateGraph` to orchestrate the complete lifecycle (create → analyze → HITL → generate → postprocess → complete) for all three input types: text, drawing, and organic.

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
- **THEN** the Graph executes `create_job_node` → `analyze_organic_node` → `confirm_with_user_node` directly
- **AND** no LLM analysis is performed before presenting confirmation

#### Scenario: Post-confirm text generation uses SpecCompiler
- **WHEN** `confirm_with_user_node` resumes after user confirmation for a text job
- **THEN** `generate_step_text_node` calls `SpecCompiler.compile()` with `matched_template` and `confirmed_params`
- **AND** SpecCompiler uses template-first strategy with LLM fallback
- **AND** the generation path converges at `convert_preview_node` → `check_printability_node` → `finalize_node`

#### Scenario: Post-confirm drawing generation unchanged
- **WHEN** `confirm_with_user_node` resumes after user confirmation for a drawing job
- **THEN** `generate_step_drawing_node` calls `generate_step_from_spec()` via the V2 pipeline (unchanged)

#### Scenario: Interceptors inserted at build time
- **WHEN** `_build_workflow()` is called and `InterceptorRegistry` has registered interceptors
- **THEN** the registered nodes are inserted at their specified positions in the graph topology
- **AND** edges are rewired to maintain the correct execution order

#### Scenario: Shared postprocess nodes execute once
- **WHEN** either `generate_step_text_node` or `generate_step_drawing_node` completes
- **THEN** `convert_step_to_preview()` runs exactly once to produce the GLB file
- **AND** `check_printability()` runs exactly once to produce the DfAM report and generate recommendations
- **AND** `finalize_node` updates DB to COMPLETED with recommendations and closes the stream
