## ADDED Requirements

### Requirement: Organic HITL confirmation presents spec for user review

The system SHALL present the built OrganicSpec to the user for review and confirmation before proceeding with mesh generation, using the same `confirm_with_user_node` interrupt mechanism as text and drawing paths.

#### Scenario: Organic spec confirmation UI data
- **WHEN** the Graph pauses at `confirm_with_user_node` for an organic job
- **THEN** the `job.organic_spec_ready` event payload SHALL contain: `prompt_en`, `shape_category`, `suggested_bounding_box`, `final_bounding_box`, `engineering_cuts`, `quality_mode`, `provider`
- **AND** the frontend renders a confirmation interface showing these fields

#### Scenario: Organic confirm request via existing ConfirmRequest model
- **WHEN** user confirms organic spec via POST /api/v1/jobs/{id}/confirm
- **THEN** the `ConfirmRequest.confirmed_params` dict (typed `dict[str, Any]`, not `dict[str, float]`) SHALL accept organic-specific keys: `prompt_en`, `bounding_box`, `quality_mode`, `provider`
- **AND** `confirm_with_user_node` merges these into `CadJobState` (updating `organic_spec`, `organic_quality_mode`, `organic_provider` as needed)
- **AND** the existing `confirmed_params: dict[str, float]` type annotation in `jobs.py` MUST be changed to `dict[str, Any]` to support string-valued organic parameters

#### Scenario: Organic confirm resumes graph to mesh generation
- **WHEN** `confirm_with_user_node` completes for an organic job
- **THEN** `route_after_confirm` returns `"organic"`
- **AND** the Graph proceeds to `generate_organic_mesh_node`
