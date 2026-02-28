## ADDED Requirements

### Requirement: Unified API versioning
All API endpoints SHALL be accessible under the `/api/v1/` prefix. Endpoints without this prefix SHALL NOT be available.

#### Scenario: Versioned endpoint access
- **WHEN** client sends a request to `POST /api/v1/jobs`
- **THEN** the server SHALL process the request and return a valid response

#### Scenario: Unversioned endpoint rejected
- **WHEN** client sends a request to `POST /api/generate`
- **THEN** the server SHALL return 404

### Requirement: Unified Job creation endpoint
The system SHALL accept job creation through a single endpoint `POST /api/v1/jobs`. The `input_type` field SHALL determine the pipeline: `"text"` for parametric template, `"drawing"` for 2D engineering drawing analysis, `"organic"` for text-to-3D mesh generation.

#### Scenario: Create text job
- **WHEN** client sends `POST /api/v1/jobs` with `input_type: "text"` and `text: "法兰盘，外径100"`
- **THEN** the server SHALL create a job, invoke IntentParser, and return `{ "job_id": "<uuid>", "status": "created" }`

#### Scenario: Create drawing job
- **WHEN** client sends `POST /api/v1/jobs` with `input_type: "drawing"` and an uploaded image file
- **THEN** the server SHALL create a job, start DrawingAnalyzer, and return `{ "job_id": "<uuid>", "status": "created" }`

#### Scenario: Create organic job
- **WHEN** client sends `POST /api/v1/jobs` with `input_type: "organic"` and `prompt: "一条龙的雕塑"`
- **THEN** the server SHALL create a job, start mesh generation, and return `{ "job_id": "<uuid>", "status": "created" }`

### Requirement: Job CRUD operations
The system SHALL provide standard CRUD operations for Job resources.

#### Scenario: List jobs with pagination
- **WHEN** client sends `GET /api/v1/jobs?page=1&page_size=20`
- **THEN** the server SHALL return a paginated list of jobs with total count

#### Scenario: Get job detail
- **WHEN** client sends `GET /api/v1/jobs/{id}`
- **THEN** the server SHALL return the full job detail including status, result, and printability

#### Scenario: Delete job
- **WHEN** client sends `DELETE /api/v1/jobs/{id}`
- **THEN** the server SHALL soft-delete the job (mark status as deleted)

#### Scenario: Regenerate job
- **WHEN** client sends `POST /api/v1/jobs/{id}/regenerate`
- **THEN** the server SHALL create a new job with the same parameters and return the new job ID

### Requirement: HITL confirmation endpoint
The system SHALL provide `POST /api/v1/jobs/{id}/confirm` for user confirmation of AI-analyzed specs.

#### Scenario: Confirm drawing spec
- **WHEN** client sends `POST /api/v1/jobs/{id}/confirm` with `confirmed_spec` body on a job in `awaiting_confirmation` status
- **THEN** the server SHALL resume the generation pipeline with the confirmed spec

#### Scenario: Confirm parameters
- **WHEN** client sends `POST /api/v1/jobs/{id}/confirm` with `confirmed_params` body on a job in `awaiting_confirmation` status
- **THEN** the server SHALL render the template with confirmed parameters

#### Scenario: Confirm on wrong status
- **WHEN** client sends `POST /api/v1/jobs/{id}/confirm` on a job NOT in `awaiting_confirmation` status
- **THEN** the server SHALL return error code `INVALID_JOB_STATE`

### Requirement: Independent SSE event subscription
The system SHALL provide `GET /api/v1/jobs/{id}/events` as an independent SSE endpoint for real-time pipeline progress. The SSE stream SHALL NOT be embedded in POST responses.

#### Scenario: Subscribe to job events
- **WHEN** client opens an SSE connection to `GET /api/v1/jobs/{id}/events`
- **THEN** the server SHALL stream events for the job's pipeline progress in real-time

#### Scenario: Event format consistency
- **WHEN** any SSE event is emitted
- **THEN** the event data SHALL contain at minimum: `job_id`, `status`, `message`

#### Scenario: Completed event is terminal
- **WHEN** the pipeline finishes successfully
- **THEN** the `completed` event SHALL be the last event emitted on the stream, with no subsequent events

### Requirement: Unified error response format
All API errors SHALL use the format `{ "error": { "code": "<ERROR_CODE>", "message": "<human_readable>", "details": <optional> } }`.

#### Scenario: Validation error
- **WHEN** client sends invalid parameters
- **THEN** the server SHALL return HTTP 422 with error code `VALIDATION_FAILED` and details listing each violation

#### Scenario: Resource not found
- **WHEN** client requests a non-existent job
- **THEN** the server SHALL return HTTP 404 with error code `JOB_NOT_FOUND`

#### Scenario: State conflict
- **WHEN** client attempts an action invalid for the current job state
- **THEN** the server SHALL return HTTP 409 with error code `INVALID_JOB_STATE`
