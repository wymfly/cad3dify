## ADDED Requirements

### Requirement: Job history listing with pagination

The system SHALL provide a paginated API endpoint for listing completed jobs, and a frontend history page displaying job cards.

#### Scenario: List completed jobs
- **WHEN** a user calls GET /jobs?page=1&page_size=20&status=completed
- **THEN** the system returns a paginated list of jobs with id, input_type, input_text (truncated), status, created_at, and thumbnail URL
- **AND** results are ordered by created_at descending (newest first)

#### Scenario: Filter by status
- **WHEN** a user calls GET /jobs?status=failed
- **THEN** only jobs with status "failed" are returned

#### Scenario: Empty history
- **WHEN** no jobs exist in the database
- **THEN** the API returns an empty list with total_count=0
- **AND** the frontend shows an empty state with a prompt to start generating

### Requirement: Job detail view

The system SHALL provide a detail page for each job showing 3D preview, parameters, printability report, and download options.

#### Scenario: View completed job detail
- **WHEN** a user navigates to /history/{job_id}
- **THEN** the page displays: 3D model preview (GLB in Three.js viewer), input parameters or DrawingSpec, PrintabilityResult (if available), and download buttons for all available formats (STEP/STL/3MF/GLB)

#### Scenario: View failed job detail
- **WHEN** a user views a failed job
- **THEN** the page shows the error message and input parameters, but no 3D preview or downloads

### Requirement: Regenerate with modified parameters

The system SHALL allow users to regenerate a model from a historical job with modified parameters.

#### Scenario: Regenerate from history
- **WHEN** a user clicks "改参数重生成" on a completed job
- **THEN** the system opens the generation page with ParamForm pre-filled with the historical job's parameters
- **AND** the user can modify any parameter before triggering a new generation
- **AND** the new generation creates a separate job (does not overwrite the original)

### Requirement: Job deletion

The system SHALL allow users to delete their job records and associated output files.

#### Scenario: Delete a job
- **WHEN** a user calls DELETE /jobs/{job_id}
- **THEN** the job record is removed from the database
- **AND** associated output files (STEP, GLB, STL, 3MF) are deleted from disk
- **AND** associated user_correction records are preserved (for training data integrity)
