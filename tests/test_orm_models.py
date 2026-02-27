"""Tests for SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.db.database import Base, async_session, engine
from backend.db.models import JobModel, OrganicJobModel, UserCorrectionModel


@pytest.fixture(autouse=True)
async def _setup_db():
    """Create tables before each test, drop after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


class TestJobModel:
    async def test_create_with_defaults(self) -> None:
        async with async_session() as session:
            job = JobModel(job_id="j1")
            session.add(job)
            await session.commit()

            result = await session.get(JobModel, "j1")
            assert result is not None
            assert result.status == "created"
            assert result.input_type == "text"
            assert result.input_text == ""
            assert result.created_at is not None

    async def test_create_with_all_fields(self) -> None:
        async with async_session() as session:
            job = JobModel(
                job_id="j2",
                status="completed",
                input_type="drawing",
                input_text="做一个法兰",
                intent={"confidence": 0.9},
                precise_spec={"part_type": "rotational"},
                drawing_spec={"part_type": "rotational", "d": 50},
                drawing_spec_confirmed={"part_type": "rotational", "d": 52},
                image_path="/tmp/img.png",
                recommendations=[{"param": "d", "value": 50}],
                result={"model_url": "/models/j2.glb"},
                printability_result={"score": 85},
                error=None,
            )
            session.add(job)
            await session.commit()

            result = await session.get(JobModel, "j2")
            assert result.status == "completed"
            assert result.drawing_spec["d"] == 50
            assert result.recommendations[0]["param"] == "d"

    async def test_json_fields_roundtrip(self) -> None:
        async with async_session() as session:
            job = JobModel(
                job_id="j3",
                intent={"nested": {"key": [1, 2, 3]}},
            )
            session.add(job)
            await session.commit()

        async with async_session() as session:
            result = await session.get(JobModel, "j3")
            assert result.intent == {"nested": {"key": [1, 2, 3]}}

    async def test_nullable_fields(self) -> None:
        async with async_session() as session:
            job = JobModel(job_id="j4")
            session.add(job)
            await session.commit()

            result = await session.get(JobModel, "j4")
            assert result.intent is None
            assert result.drawing_spec is None
            assert result.error is None


class TestOrganicJobModel:
    async def test_create_with_defaults(self) -> None:
        async with async_session() as session:
            job = OrganicJobModel(job_id="o1")
            session.add(job)
            await session.commit()

            result = await session.get(OrganicJobModel, "o1")
            assert result.status == "created"
            assert result.provider == "auto"
            assert result.quality_mode == "standard"
            assert result.progress == 0.0

    async def test_update_progress(self) -> None:
        async with async_session() as session:
            job = OrganicJobModel(job_id="o2", prompt="a dragon")
            session.add(job)
            await session.commit()

            job.progress = 0.75
            job.status = "generating"
            job.message = "75% complete"
            await session.commit()

        async with async_session() as session:
            result = await session.get(OrganicJobModel, "o2")
            assert result.progress == 0.75
            assert result.status == "generating"


class TestUserCorrectionModel:
    async def test_create_correction(self) -> None:
        async with async_session() as session:
            correction = UserCorrectionModel(
                job_id="j1",
                field_path="overall_dimensions.max_diameter",
                original_value="48.0",
                corrected_value="50.0",
            )
            session.add(correction)
            await session.commit()
            await session.refresh(correction)
            assert correction.id is not None
            assert correction.timestamp is not None

    async def test_multiple_corrections_per_job(self) -> None:
        async with async_session() as session:
            for i, path in enumerate(["d1", "d2", "d3"]):
                session.add(UserCorrectionModel(
                    job_id="j1",
                    field_path=path,
                    original_value=str(i),
                    corrected_value=str(i + 10),
                ))
            await session.commit()

        async with async_session() as session:
            stmt = select(UserCorrectionModel).where(
                UserCorrectionModel.job_id == "j1",
            )
            result = await session.execute(stmt)
            corrections = result.scalars().all()
            assert len(corrections) == 3

    async def test_autoincrement_id(self) -> None:
        async with async_session() as session:
            c1 = UserCorrectionModel(
                job_id="j1", field_path="a",
                original_value="0", corrected_value="1",
            )
            c2 = UserCorrectionModel(
                job_id="j1", field_path="b",
                original_value="0", corrected_value="1",
            )
            session.add_all([c1, c2])
            await session.commit()
            await session.refresh(c1)
            await session.refresh(c2)
            assert c1.id < c2.id
