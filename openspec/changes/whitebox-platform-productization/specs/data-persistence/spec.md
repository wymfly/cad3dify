## ADDED Requirements

### Requirement: SQLite database persistence
All Job data SHALL be persisted to SQLite database via SQLAlchemy async ORM. In-memory dict storage SHALL be removed entirely.

#### Scenario: Job survives process restart
- **WHEN** a job is created, the backend process restarts, and client queries the job
- **THEN** the server SHALL return the job with all its data intact

#### Scenario: Concurrent read/write safety
- **WHEN** multiple async coroutines read and write jobs simultaneously
- **THEN** no data corruption or lost updates SHALL occur (aiosqlite serialization)

### Requirement: Storage abstraction interface
The system SHALL define `JobRepository` and `FileStorage` Protocol interfaces that abstract the underlying storage backend. Implementations SHALL be swappable via environment variable.

#### Scenario: SQLite repository
- **WHEN** `DATABASE_URL` is set to `sqlite+aiosqlite:///...`
- **THEN** the system SHALL use `SQLiteJobRepository` for all job operations

#### Scenario: PostgreSQL migration readiness
- **WHEN** `DATABASE_URL` is set to `postgresql+asyncpg://...`
- **THEN** the system SHALL use `PostgresJobRepository` without code changes (interface compliance)

#### Scenario: Local file storage
- **WHEN** `STORAGE_BACKEND` is set to `local`
- **THEN** generated files (STEP, GLB, STL, 3MF) SHALL be stored in `outputs/{job_id}/`

### Requirement: Database migration support
The system SHALL use Alembic for database schema migrations.

#### Scenario: Initial migration
- **WHEN** `alembic upgrade head` is run on a fresh database
- **THEN** all required tables (jobs, organic_jobs, user_corrections) SHALL be created

#### Scenario: Schema evolution
- **WHEN** a new column is added to the Job model
- **THEN** an Alembic migration script SHALL handle the schema change without data loss

### Requirement: User correction tracking
The system SHALL persist user corrections (field-level diffs from HITL confirmation) in a dedicated `user_corrections` table.

#### Scenario: Record drawing spec correction
- **WHEN** user modifies a DrawingSpec field during HITL confirmation (e.g., diameter from 10 to 12)
- **THEN** the system SHALL insert a row with `job_id`, `field_path`, `original_value`, `corrected_value`, `timestamp`

#### Scenario: Query corrections for a job
- **WHEN** client sends `GET /api/v1/jobs/{id}/corrections`
- **THEN** the server SHALL return all corrections made during that job's HITL confirmation
