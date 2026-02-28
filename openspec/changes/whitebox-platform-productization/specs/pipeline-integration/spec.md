## ADDED Requirements

### Requirement: PrintabilityChecker automatic invocation
The system SHALL automatically invoke PrintabilityChecker after model generation in both precision and organic pipelines. A `printability_checked` SSE event SHALL be emitted before `completed`.

#### Scenario: Precision pipeline printability check
- **WHEN** CadQuery code execution produces a valid STEP file
- **THEN** PrintabilityChecker SHALL run against the STEP geometry and its result SHALL be included in the `completed` event's `printability` field

#### Scenario: Organic pipeline printability check
- **WHEN** MeshPostProcessor completes mesh processing
- **THEN** PrintabilityChecker SHALL run against the mesh and its result SHALL be included in the `completed` event's `printability` field

#### Scenario: Printability check failure does not block pipeline
- **WHEN** PrintabilityChecker raises an exception
- **THEN** the pipeline SHALL continue to `completed` with `printability: null` and a warning message

### Requirement: Drawing path HITL confirmation flow
The drawing pipeline SHALL split into two phases: analysis and generation. After analysis, the system SHALL pause for user confirmation before generating.

#### Scenario: Drawing analysis produces confirmation request
- **WHEN** DrawingAnalyzer completes analysis of an uploaded engineering drawing
- **THEN** the system SHALL emit `drawing_spec_ready` SSE event with the extracted DrawingSpec and set job status to `awaiting_confirmation`

#### Scenario: User confirms and generation resumes
- **WHEN** user confirms the DrawingSpec via `POST /api/v1/jobs/{id}/confirm`
- **THEN** the system SHALL resume with `generate_from_drawing_spec(confirmed_spec)` and emit subsequent pipeline events

#### Scenario: User modifies DrawingSpec before confirmation
- **WHEN** user edits DrawingSpec fields (e.g., changes diameter from 100 to 120) and confirms
- **THEN** the system SHALL use the modified values for generation AND record the changes in `user_corrections`

### Requirement: IntentParser replaces keyword matching
For text input jobs, the system SHALL use IntentParser (LLM-based) as the primary intent routing mechanism. Keyword matching (`_match_template`) SHALL serve as fallback only.

#### Scenario: IntentParser routes to correct template
- **WHEN** user inputs "帮我做一个法兰盘，外径100，内径40"
- **THEN** IntentParser SHALL identify `part_type: rotational` and match to `flange_basic` template

#### Scenario: IntentParser failure falls back to keyword
- **WHEN** IntentParser raises an exception or returns low confidence
- **THEN** the system SHALL fall back to keyword matching and log a warning

### Requirement: Organic pipeline 3MF export
The organic pipeline SHALL export 3MF format alongside GLB and STL. The `threemf_url` field in the completed event SHALL contain a valid download URL.

#### Scenario: 3MF file generated
- **WHEN** organic pipeline completes mesh post-processing
- **THEN** the system SHALL export the mesh as `model.3mf` in the output directory

#### Scenario: 3MF download available
- **WHEN** client accesses the `threemf_url` from the completed event
- **THEN** the server SHALL return a valid 3MF file

### Requirement: User correction data collection
The system SHALL automatically capture field-level diffs when users modify AI-analyzed specs during HITL confirmation.

#### Scenario: Drawing spec field modification tracked
- **WHEN** user changes `base_body.profile[0].diameter` from 100 to 120 during HITL confirmation
- **THEN** a correction record SHALL be created with `field_path: "base_body.profile[0].diameter"`, `original_value: "100"`, `corrected_value: "120"`

#### Scenario: No corrections when unchanged
- **WHEN** user confirms the DrawingSpec without modifications
- **THEN** no correction records SHALL be created for that job
