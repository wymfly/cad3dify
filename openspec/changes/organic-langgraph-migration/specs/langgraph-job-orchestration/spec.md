## MODIFIED Requirements

### Requirement: Unified StateGraph manages CAD Job lifecycle

The system SHALL implement a single `CadJobStateGraph` using LangGraph `StateGraph` to orchestrate the complete lifecycle (create → analyze → HITL → generate → postprocess → complete) for all three input types: text, drawing, and organic.

#### Scenario: Text job flows through intent analysis
- **WHEN** a POST /api/v1/jobs request arrives with `input_type=text`
- **THEN** the Graph executes `create_job_node` → `analyze_intent_node` → `confirm_with_user_node`
- **AND** each node transition is persisted to checkpoint before proceeding

#### Scenario: Drawing job flows through vision analysis
- **WHEN** a POST /api/v1/jobs/upload request arrives with `input_type=drawing`
- **THEN** the Graph executes `create_job_node` → `analyze_vision_node` → `confirm_with_user_node`
- **AND** `analyze_vision_node` wraps `analyze_vision_spec()` via `asyncio.to_thread`

#### Scenario: Organic job flows through spec building
- **WHEN** a POST /api/v1/jobs request arrives with `input_type=organic`
- **THEN** the Graph executes `create_job_node` → `analyze_organic_node` → `confirm_with_user_node`
- **AND** `analyze_organic_node` calls `OrganicSpecBuilder.build()` to translate prompt and build spec

#### Scenario: Post-confirm generation routes by type including organic
- **WHEN** `confirm_with_user_node` resumes after user confirmation
- **THEN** the Graph routes to `generate_step_text_node` for text, `generate_step_drawing_node` for drawing, or `generate_organic_mesh_node` for organic
- **AND** text/drawing paths converge at `convert_preview_node` → `check_printability_node` → `finalize_node`
- **AND** organic path goes through `generate_organic_mesh_node` → `postprocess_organic_node` → `finalize_node`

#### Scenario: Shared postprocess nodes execute once
- **WHEN** either `generate_step_text_node` or `generate_step_drawing_node` completes
- **THEN** `convert_step_to_preview()` runs exactly once to produce the GLB file
- **AND** `check_printability()` runs exactly once to produce the DfAM report
- **AND** `finalize_node` updates DB to COMPLETED and closes the stream

## REMOVED Requirements

### Requirement: Organic job skips analysis

**Reason**: Replaced by `analyze_organic_node` which performs LLM-based spec building instead of skipping analysis entirely.

**Migration**: `stub_organic_node` is deleted. The organic path now goes through `analyze_organic_node` → `confirm_with_user_node` with full HITL support.

### Requirement: Organic post-confirm exits Graph for legacy processing

**Reason**: Organic generation is now fully handled within the Graph via `generate_organic_mesh_node` → `postprocess_organic_node`. No delegation to external endpoints.

**Migration**: Delete `/api/v1/organic` endpoint after relocating `/providers` (→ `/api/v1/jobs/organic-providers`) and `/upload` (→ `/api/v1/jobs/upload-reference`) endpoints. All organic generation goes through `/api/v1/jobs` with `input_type=organic`.
