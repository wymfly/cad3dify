## ADDED Requirements

### Requirement: SQLite-based job persistence

The system SHALL persist all Job records to a SQLite database, replacing the current in-memory dict storage. Jobs MUST survive process restarts.

#### Scenario: Job survives restart
- **WHEN** a job is created and the backend process is restarted
- **THEN** the job record is still accessible via GET /generate/{job_id}
- **AND** all fields (status, specs, results, output file paths) are preserved

#### Scenario: Job creation
- **WHEN** a new generation request is received
- **THEN** a Job record is inserted into the database with status, input_type, input_text, and timestamps
- **AND** the record is updated as the pipeline progresses through stages

#### Scenario: Organic job survives restart
- **WHEN** an organic generation job is created and the backend process is restarted
- **THEN** the organic job record is still accessible
- **AND** all fields (status, prompt, provider, quality_mode, result, output file paths) are preserved

### Requirement: Async database operations

All database operations SHALL be async (using aiosqlite) to avoid blocking the FastAPI event loop.

#### Scenario: Concurrent requests
- **WHEN** multiple generation requests are processed simultaneously
- **THEN** database reads and writes do not block each other
- **AND** no "database is locked" errors occur under normal load (single uvicorn worker)
- **AND** aiosqlite is configured with busy_timeout=30s and pool_pre_ping=True to avoid connection hanging (SQLAlchemy #13039)

### Requirement: Schema migration support

The system SHALL use Alembic for database schema migrations, enabling safe schema evolution.

#### Scenario: Initial migration
- **WHEN** the application starts with no existing database
- **THEN** Alembic creates all tables (jobs, organic_jobs, user_corrections) automatically

#### Scenario: Schema upgrade
- **WHEN** a new migration adds a column to the jobs table
- **THEN** `alembic upgrade head` applies the change without data loss

### Requirement: DrawingSpec and user correction persistence

The system SHALL store both the original AI-extracted DrawingSpec and the user-confirmed version, along with field-level correction records.

#### Scenario: Drawing spec versions stored
- **WHEN** a user confirms a modified DrawingSpec during HITL
- **THEN** the job record contains both `drawing_spec` (original) and `drawing_spec_confirmed` (user version) as JSON fields

#### Scenario: User corrections queryable
- **WHEN** an administrator queries user_corrections for training data export
- **THEN** each record contains job_id, field_path, original_value, corrected_value, and timestamp
- **AND** records can be joined with jobs to retrieve the associated image path

### Requirement: Printability result persistence

The system SHALL store PrintabilityResult as a JSON field in the job record.

#### Scenario: Printability stored with job
- **WHEN** PrintabilityChecker completes for a job
- **THEN** the full PrintabilityResult (printable flag, issues list, material estimate, time estimate) is stored in the job's `printability_result` JSON field
