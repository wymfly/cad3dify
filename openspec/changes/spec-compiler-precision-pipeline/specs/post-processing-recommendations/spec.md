## ADDED Requirements

### Requirement: Post-processing recommendations generated from printability results

The system SHALL generate actionable post-processing recommendations based on the output of `PrintabilityChecker`, and store them in the Job's `recommendations` field.

#### Scenario: Thin wall issues produce strengthening recommendations
- **WHEN** `PrintabilityChecker` reports issues with `type="thin_wall"` and `severity="warning"`
- **THEN** recommendations SHALL include an entry with `action="thicken_wall"`, `tool="NX/Magics"`, and a description explaining the minimum wall thickness required

#### Scenario: Overhang issues produce support recommendations
- **WHEN** `PrintabilityChecker` reports issues with `type="overhang"` and `severity="warning"`
- **THEN** recommendations SHALL include an entry with `action="add_support"`, `tool="Oqton/Magics"`, and the overhang angle threshold

#### Scenario: No printability issues produce empty recommendations
- **WHEN** `PrintabilityChecker` returns `printable=True` with no issues
- **THEN** recommendations SHALL be an empty list

#### Scenario: Recommendations persisted in Job result
- **WHEN** `finalize_node` runs after printability check
- **THEN** the Job's `result` JSON in the database SHALL contain a `recommendations` array
- **AND** each recommendation includes `action`, `tool`, `description`, and `severity` fields

### Requirement: Recommendations dispatched via SSE for real-time display

The system SHALL dispatch recommendations as part of the `job.printability_checked` SSE event payload.

#### Scenario: SSE event includes recommendations
- **WHEN** `check_printability_node` completes
- **THEN** the `job.printability_checked` SSE event payload SHALL include a `recommendations` array
- **AND** the frontend can display recommendations without additional API calls
