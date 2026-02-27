"""Organic job session model for the organic generation pipeline.

Parallel to backend/models/job.py but for organic generation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from backend.models.organic import OrganicJobResult


class OrganicJobStatus(str, Enum):
    """Lifecycle states for an organic generation job."""

    CREATED = "created"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    POST_PROCESSING = "post_processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OrganicJob(BaseModel):
    """Organic job record (API-layer data object)."""

    job_id: str
    status: OrganicJobStatus = OrganicJobStatus.CREATED
    prompt: str = ""
    provider: str = "auto"
    quality_mode: str = "standard"
    progress: float = 0.0
    message: str = ""
    result: Optional[OrganicJobResult] = None
    error: Optional[str] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# ORM ↔ Pydantic conversion
# ---------------------------------------------------------------------------


def _orm_to_organic_job(orm: Any) -> OrganicJob:
    """Convert an OrganicJobModel ORM instance to a Pydantic OrganicJob."""
    created_at = ""
    if orm.created_at is not None:
        created_at = (
            orm.created_at.isoformat()
            if isinstance(orm.created_at, datetime)
            else str(orm.created_at)
        )
    result = None
    if orm.result is not None:
        try:
            result = OrganicJobResult.model_validate(orm.result)
        except Exception:
            pass
    return OrganicJob(
        job_id=orm.job_id,
        status=OrganicJobStatus(orm.status),
        prompt=orm.prompt or "",
        provider=orm.provider or "auto",
        quality_mode=orm.quality_mode or "standard",
        progress=orm.progress or 0.0,
        message=orm.message or "",
        result=result,
        error=orm.error,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# Async organic job store (delegates to SQLite repository)
# ---------------------------------------------------------------------------


async def create_organic_job(
    job_id: str,
    prompt: str = "",
    provider: str = "auto",
    quality_mode: str = "standard",
) -> OrganicJob:
    """Create and persist a new organic job."""
    from backend.db.database import async_session
    from backend.db.repository import create_organic_job as repo_create

    async with async_session() as session:
        orm_job = await repo_create(
            session,
            job_id=job_id,
            status=OrganicJobStatus.CREATED.value,
            prompt=prompt,
            provider=provider,
            quality_mode=quality_mode,
        )
        await session.commit()
        return _orm_to_organic_job(orm_job)


async def get_organic_job(job_id: str) -> Optional[OrganicJob]:
    """Retrieve an organic job by ID, or None."""
    from backend.db.database import async_session
    from backend.db.repository import get_organic_job as repo_get

    async with async_session() as session:
        orm_job = await repo_get(session, job_id)
        if orm_job is None:
            return None
        return _orm_to_organic_job(orm_job)


async def update_organic_job(job_id: str, **kwargs: Any) -> OrganicJob:
    """Update fields on an existing organic job. Raises KeyError if not found."""
    from backend.db.database import async_session
    from backend.db.repository import update_organic_job as repo_update

    # Serialize Pydantic models to dicts for JSON columns
    serialized = {}
    for key, value in kwargs.items():
        if isinstance(value, BaseModel):
            serialized[key] = value.model_dump(mode="json")
        else:
            serialized[key] = value

    async with async_session() as session:
        orm_job = await repo_update(session, job_id, **serialized)
        await session.commit()
        return _orm_to_organic_job(orm_job)


async def delete_organic_job(job_id: str) -> None:
    """Remove an organic job from the store."""
    from backend.db.database import async_session
    from backend.db.models import OrganicJobModel

    async with async_session() as session:
        orm_job = await session.get(OrganicJobModel, job_id)
        if orm_job is not None:
            await session.delete(orm_job)
            await session.commit()


async def list_organic_jobs() -> list[OrganicJob]:
    """Return all organic jobs."""
    from backend.db.database import async_session
    from backend.db.repository import list_organic_jobs as repo_list

    async with async_session() as session:
        orm_jobs, _ = await repo_list(session, page=1, page_size=10000)
        return [_orm_to_organic_job(j) for j in orm_jobs]


async def clear_organic_jobs() -> None:
    """Clear all organic jobs (for testing)."""
    from sqlalchemy import delete as sa_delete

    from backend.db.database import async_session
    from backend.db.models import OrganicJobModel

    async with async_session() as session:
        await session.execute(sa_delete(OrganicJobModel))
        await session.commit()
