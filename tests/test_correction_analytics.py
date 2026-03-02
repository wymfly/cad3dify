"""Tests for correction analytics: cleaning script logic and stats API.

Covers:
- Clean corrections filtering rules (noop, empty, missing job)
- JSONL output format
- Stats API aggregation and part_type filtering
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

try:
    from backend.db.database import Base
    from backend.db.models import JobModel, UserCorrectionModel
    from backend.db.repository import create_correction, create_job

    _DB_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    _DB_AVAILABLE = False

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not _DB_AVAILABLE, reason="backend/db/ not available"),
]

_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def db_engine():
    """In-memory async SQLite engine."""
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_TEST_DB_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def db_tables(db_engine):
    """Create all tables."""
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture()
async def session(db_engine, db_tables):
    """Provide an async session for tests."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.fixture()
async def seed_data(session):
    """Seed jobs and corrections for testing."""
    # Create jobs with different intents
    await create_job(
        session, "job-1", input_type="text",
        intent={"part_type": "rotational", "template": "flange"},
    )
    await create_job(
        session, "job-2", input_type="text",
        intent={"part_type": "plate", "template": "bracket"},
    )
    await create_job(
        session, "job-3", input_type="drawing",
        drawing_spec={"part_type": "gear", "teeth": 20},
    )

    # Valid corrections
    await create_correction(
        session, job_id="job-1",
        field_path="overall_dimensions.diameter",
        original_value="50.0", corrected_value="55.0",
    )
    await create_correction(
        session, job_id="job-1",
        field_path="overall_dimensions.height",
        original_value="10.0", corrected_value="12.0",
    )
    await create_correction(
        session, job_id="job-2",
        field_path="overall_dimensions.diameter",
        original_value="100.0", corrected_value="110.0",
    )
    await create_correction(
        session, job_id="job-3",
        field_path="features.hole_diameter",
        original_value="5.0", corrected_value="6.0",
    )

    # Noop correction (original == corrected) — should be filtered
    await create_correction(
        session, job_id="job-1",
        field_path="base_body.method",
        original_value="revolve", corrected_value="revolve",
    )

    # Empty field_path — should be filtered
    await create_correction(
        session, job_id="job-1",
        field_path="",
        original_value="x", corrected_value="y",
    )

    # Empty corrected_value — should be filtered
    await create_correction(
        session, job_id="job-2",
        field_path="some.field",
        original_value="abc", corrected_value="",
    )

    # Correction referencing non-existent job — should be filtered
    await create_correction(
        session, job_id="nonexistent-job",
        field_path="field.a",
        original_value="1", corrected_value="2",
    )

    await session.commit()


# ---------------------------------------------------------------------------
# Clean corrections logic tests
# ---------------------------------------------------------------------------


class TestCleanCorrectionsLogic:
    """Test the cleaning/filtering rules for corrections."""

    async def test_filter_noop_corrections(self, session, seed_data) -> None:
        """Corrections where original == corrected should be excluded."""
        from sqlalchemy import select

        result = await session.execute(
            select(UserCorrectionModel).where(
                UserCorrectionModel.original_value == UserCorrectionModel.corrected_value,
            ),
        )
        noop = list(result.scalars().all())
        assert len(noop) == 1
        assert noop[0].field_path == "base_body.method"

    async def test_filter_empty_field_path(self, session, seed_data) -> None:
        """Corrections with empty field_path should be excluded."""
        from sqlalchemy import select

        result = await session.execute(
            select(UserCorrectionModel).where(
                UserCorrectionModel.field_path == "",
            ),
        )
        empty = list(result.scalars().all())
        assert len(empty) == 1

    async def test_filter_empty_corrected_value(self, session, seed_data) -> None:
        """Corrections with empty corrected_value should be excluded."""
        from sqlalchemy import select

        result = await session.execute(
            select(UserCorrectionModel).where(
                UserCorrectionModel.corrected_value == "",
            ),
        )
        empty = list(result.scalars().all())
        assert len(empty) == 1

    async def test_valid_corrections_count(self, session, seed_data) -> None:
        """After filtering, only valid corrections remain."""
        from sqlalchemy import select

        result = await session.execute(
            select(UserCorrectionModel).where(
                UserCorrectionModel.field_path != "",
                UserCorrectionModel.corrected_value != "",
                UserCorrectionModel.original_value != UserCorrectionModel.corrected_value,
            ),
        )
        valid = list(result.scalars().all())
        # 4 valid + 1 nonexistent-job = 5 pass field/value filters
        # The nonexistent-job one passes SQL filters but would be skipped by job lookup
        assert len(valid) == 5


# ---------------------------------------------------------------------------
# JSONL output format tests
# ---------------------------------------------------------------------------


class TestJSONLOutput:
    """Test the JSONL output format of the cleaning script."""

    async def test_clean_corrections_output(self, session, seed_data, tmp_path) -> None:
        """Full pipeline: clean corrections and verify JSONL output."""
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        # Simulate clean_corrections logic in-process (avoid DB URL coupling)
        all_corrections_result = await session.execute(
            select(UserCorrectionModel).order_by(UserCorrectionModel.timestamp),
        )
        all_corrections = list(all_corrections_result.scalars().all())

        job_ids = {c.job_id for c in all_corrections}
        jobs_result = await session.execute(
            select(JobModel).where(JobModel.job_id.in_(job_ids)),
        )
        jobs_by_id = {j.job_id: j for j in jobs_result.scalars().all()}

        output_path = tmp_path / "corrections.jsonl"
        records = []
        from collections import defaultdict

        corrections_by_job: dict[str, list] = defaultdict(list)
        skipped_noop = 0
        skipped_empty = 0
        skipped_no_job = 0

        for c in all_corrections:
            if c.original_value == c.corrected_value:
                skipped_noop += 1
                continue
            if not c.field_path or not c.field_path.strip():
                skipped_empty += 1
                continue
            if not c.corrected_value or not c.corrected_value.strip():
                skipped_empty += 1
                continue
            if c.job_id not in jobs_by_id:
                skipped_no_job += 1
                continue
            corrections_by_job[c.job_id].append(c)

        with open(output_path, "w", encoding="utf-8") as f:
            for job_id, corrections in corrections_by_job.items():
                job = jobs_by_id[job_id]
                input_spec = job.intent or job.drawing_spec or {}
                record = {
                    "job_id": job_id,
                    "input_spec": input_spec,
                    "corrections": [
                        {"field_path": c.field_path, "corrected_value": c.corrected_value}
                        for c in corrections
                    ],
                    "timestamp": corrections[-1].timestamp.isoformat() if corrections[-1].timestamp else None,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                records.append(record)

        assert skipped_noop == 1
        assert skipped_empty == 2
        assert skipped_no_job == 1

        # Read and verify JSONL
        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 3  # job-1, job-2, job-3

        parsed = [json.loads(line) for line in lines]

        # job-1 should have 2 corrections
        job1_record = next(r for r in parsed if r["job_id"] == "job-1")
        assert len(job1_record["corrections"]) == 2
        assert job1_record["input_spec"]["part_type"] == "rotational"

        # job-2 should have 1 correction
        job2_record = next(r for r in parsed if r["job_id"] == "job-2")
        assert len(job2_record["corrections"]) == 1

        # job-3 uses drawing_spec as input_spec
        job3_record = next(r for r in parsed if r["job_id"] == "job-3")
        assert job3_record["input_spec"]["part_type"] == "gear"

    async def test_jsonl_record_format(self, session, seed_data, tmp_path) -> None:
        """Each JSONL record has required fields."""
        from sqlalchemy import select

        result = await session.execute(
            select(UserCorrectionModel).where(
                UserCorrectionModel.job_id == "job-1",
                UserCorrectionModel.field_path != "",
                UserCorrectionModel.corrected_value != "",
                UserCorrectionModel.original_value != UserCorrectionModel.corrected_value,
            ).order_by(UserCorrectionModel.timestamp),
        )
        corrections = list(result.scalars().all())

        job_result = await session.execute(
            select(JobModel).where(JobModel.job_id == "job-1"),
        )
        job = job_result.scalar_one()

        record = {
            "job_id": "job-1",
            "input_spec": job.intent or job.drawing_spec or {},
            "corrections": [
                {"field_path": c.field_path, "corrected_value": c.corrected_value}
                for c in corrections
            ],
            "timestamp": corrections[-1].timestamp.isoformat() if corrections[-1].timestamp else None,
        }

        assert "job_id" in record
        assert "input_spec" in record
        assert "corrections" in record
        assert "timestamp" in record
        assert isinstance(record["corrections"], list)
        for c in record["corrections"]:
            assert "field_path" in c
            assert "corrected_value" in c


# ---------------------------------------------------------------------------
# Stats API tests
# ---------------------------------------------------------------------------


class TestStatsAPI:
    """Test the GET /api/v1/corrections/stats endpoint logic."""

    async def test_stats_aggregation(self, session, seed_data) -> None:
        """Stats should aggregate corrections by field_path."""
        from sqlalchemy import func, select

        stmt = (
            select(
                UserCorrectionModel.field_path,
                func.count().label("cnt"),
            )
            .where(
                UserCorrectionModel.field_path != "",
                UserCorrectionModel.corrected_value != "",
                UserCorrectionModel.original_value != UserCorrectionModel.corrected_value,
            )
            .group_by(UserCorrectionModel.field_path)
            .order_by(func.count().desc())
            .limit(20)
        )
        result = await session.execute(stmt)
        rows = result.all()

        # overall_dimensions.diameter appears in job-1 and job-2 = 2 times
        field_counts = {r.field_path: r.cnt for r in rows}
        assert field_counts["overall_dimensions.diameter"] == 2
        assert field_counts["overall_dimensions.height"] == 1
        assert field_counts["features.hole_diameter"] == 1
        # field.a from nonexistent-job still counted in raw SQL (no job join)
        assert field_counts["field.a"] == 1

    async def test_stats_with_part_type_filter(self, session, seed_data) -> None:
        """Stats filtered by part_type via intent JSON."""
        from sqlalchemy import func, select

        stmt = (
            select(
                UserCorrectionModel.field_path,
                func.count().label("cnt"),
            )
            .join(
                JobModel,
                UserCorrectionModel.job_id == JobModel.job_id,
            )
            .where(
                UserCorrectionModel.field_path != "",
                UserCorrectionModel.corrected_value != "",
                UserCorrectionModel.original_value != UserCorrectionModel.corrected_value,
                func.json_extract(JobModel.intent, "$.part_type") == "rotational",
            )
            .group_by(UserCorrectionModel.field_path)
            .order_by(func.count().desc())
            .limit(20)
        )
        result = await session.execute(stmt)
        rows = result.all()

        # Only job-1 is rotational: 2 corrections
        assert len(rows) == 2
        field_counts = {r.field_path: r.cnt for r in rows}
        assert field_counts["overall_dimensions.diameter"] == 1
        assert field_counts["overall_dimensions.height"] == 1

    async def test_stats_empty_result(self, session, db_tables) -> None:
        """Stats on empty database returns empty list."""
        from sqlalchemy import func, select

        stmt = (
            select(
                UserCorrectionModel.field_path,
                func.count().label("cnt"),
            )
            .where(
                UserCorrectionModel.field_path != "",
                UserCorrectionModel.corrected_value != "",
                UserCorrectionModel.original_value != UserCorrectionModel.corrected_value,
            )
            .group_by(UserCorrectionModel.field_path)
            .order_by(func.count().desc())
            .limit(20)
        )
        result = await session.execute(stmt)
        rows = result.all()
        assert rows == []

    async def test_stats_percent_calculation(self, session, seed_data) -> None:
        """Percentages should sum to ~100% (within rounding)."""
        from sqlalchemy import func, select

        stmt = (
            select(
                UserCorrectionModel.field_path,
                func.count().label("cnt"),
            )
            .where(
                UserCorrectionModel.field_path != "",
                UserCorrectionModel.corrected_value != "",
                UserCorrectionModel.original_value != UserCorrectionModel.corrected_value,
            )
            .group_by(UserCorrectionModel.field_path)
            .order_by(func.count().desc())
            .limit(20)
        )
        result = await session.execute(stmt)
        rows = result.all()

        total = sum(r.cnt for r in rows)
        percents = [round(r.cnt / total * 100, 1) for r in rows]
        assert abs(sum(percents) - 100.0) < 1.0  # Allow rounding tolerance


# ---------------------------------------------------------------------------
# Pydantic response model tests
# ---------------------------------------------------------------------------


class TestResponseModels:
    """Test the Pydantic response models."""

    def test_field_stat_model(self) -> None:
        """FieldStat model accepts valid data."""
        from backend.api.v1.corrections import FieldStat

        stat = FieldStat(field_path="dimensions.diameter", count=10, percent=25.0)
        assert stat.field_path == "dimensions.diameter"
        assert stat.count == 10
        assert stat.percent == 25.0

    def test_correction_stats_response_model(self) -> None:
        """CorrectionStatsResponse wraps a list of FieldStat."""
        from backend.api.v1.corrections import CorrectionStatsResponse, FieldStat

        resp = CorrectionStatsResponse(
            top_fields=[
                FieldStat(field_path="a", count=5, percent=50.0),
                FieldStat(field_path="b", count=5, percent=50.0),
            ],
        )
        assert len(resp.top_fields) == 2

    def test_empty_stats_response(self) -> None:
        """Empty response has empty top_fields."""
        from backend.api.v1.corrections import CorrectionStatsResponse

        resp = CorrectionStatsResponse()
        assert resp.top_fields == []
