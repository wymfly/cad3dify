## ADDED Requirements

### Requirement: Organic jobs pause for user confirmation before generation

The system SHALL pause organic jobs at `confirm_with_user_node` (via `interrupt_before`) after `analyze_organic_node` completes, allowing users to review and adjust the OrganicSpec before mesh generation proceeds.

#### Scenario: Organic spec presented for confirmation
- **WHEN** `analyze_organic_node` completes with a valid `organic_spec`
- **THEN** a `job.organic_spec_ready` SSE event is dispatched with payload containing `prompt_en`, `shape_category`, `suggested_bounding_box`, `final_bounding_box`, `engineering_cuts`, `quality_mode`
- **AND** a `job.awaiting_confirmation` SSE event is dispatched
- **AND** the Graph pauses at `confirm_with_user_node` boundary

#### Scenario: User confirms organic spec without changes
- **WHEN** user calls POST /api/v1/jobs/{id}/confirm with `confirmed_params` containing the original spec values
- **THEN** the Graph resumes from `confirm_with_user_node`
- **AND** `route_after_confirm` returns `"organic"`
- **AND** `generate_organic_mesh_node` executes with the original spec

#### Scenario: User adjusts bounding box before confirming
- **WHEN** user calls POST /api/v1/jobs/{id}/confirm with `confirmed_params.bounding_box` set to a different value
- **THEN** the Graph resumes and `postprocess_organic_node` uses the user-confirmed bounding box for scaling
- **AND** the original `suggested_bounding_box` in organic_spec is preserved (not overwritten)

#### Scenario: User changes quality mode or provider
- **WHEN** user calls confirm with `confirmed_params.quality_mode="high"` or `confirmed_params.provider="tripo3d"`
- **THEN** `state["organic_quality_mode"]` and/or `state["organic_provider"]` are updated before generation

#### Scenario: User edits translated prompt
- **WHEN** user modifies the `prompt_en` field in confirmed_params
- **THEN** `generate_organic_mesh_node` uses the user-edited English prompt for mesh generation
