"""CLI script to clean user correction data and export to JSONL.

Reads UserCorrection records from the database, filters invalid entries,
joins with Job data for input_spec context, and outputs clean JSONL
suitable for SFT training.

Usage:
    uv run python scripts/data/clean_corrections.py
    uv run python scripts/data/clean_corrections.py --output /tmp/corrections.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = Path("data/training/corrections_clean.jsonl")


async def clean_corrections(output_path: Path) -> dict[str, int]:
    """Read corrections from DB, clean, and write JSONL.

    Returns a summary dict with counts of total, skipped, written records.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from backend.db.database import DATABASE_URL
    from backend.db.models import JobModel, UserCorrectionModel

    engine = create_async_engine(DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stats = {"total": 0, "skipped_noop": 0, "skipped_empty": 0, "skipped_no_job": 0, "written": 0}

    async with factory() as session:
        # Load all corrections
        result = await session.execute(
            select(UserCorrectionModel).order_by(UserCorrectionModel.timestamp),
        )
        all_corrections = list(result.scalars().all())
        stats["total"] = len(all_corrections)

        if not all_corrections:
            logger.info("No corrections found in database.")
            await engine.dispose()
            return stats

        # Collect unique job_ids and load jobs
        job_ids = {c.job_id for c in all_corrections}
        job_result = await session.execute(
            select(JobModel).where(JobModel.job_id.in_(job_ids)),
        )
        jobs_by_id = {j.job_id: j for j in job_result.scalars().all()}

    await engine.dispose()

    # Group corrections by job_id
    corrections_by_job: dict[str, list] = defaultdict(list)
    for c in all_corrections:
        # Rule 1: skip noop (original == corrected)
        if c.original_value == c.corrected_value:
            stats["skipped_noop"] += 1
            continue

        # Rule 2: skip empty field_path or corrected_value
        if not c.field_path or not c.field_path.strip():
            stats["skipped_empty"] += 1
            continue
        if not c.corrected_value or not c.corrected_value.strip():
            stats["skipped_empty"] += 1
            continue

        # Rule 3: skip if job not found (warning, not crash)
        if c.job_id not in jobs_by_id:
            stats["skipped_no_job"] += 1
            logger.warning("Correction id=%d references unknown job_id=%s, skipping.", c.id, c.job_id)
            continue

        corrections_by_job[c.job_id].append(c)

    # Write JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for job_id, corrections in corrections_by_job.items():
            job = jobs_by_id[job_id]

            # input_spec from intent or drawing_spec
            input_spec = job.intent or job.drawing_spec or {}

            record = {
                "job_id": job_id,
                "input_spec": input_spec,
                "corrections": [
                    {
                        "field_path": c.field_path,
                        "corrected_value": c.corrected_value,
                    }
                    for c in corrections
                ],
                "timestamp": corrections[-1].timestamp.isoformat() if corrections[-1].timestamp else None,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            stats["written"] += len(corrections)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean user correction data for SFT training.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSONL path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    stats = asyncio.run(clean_corrections(args.output))

    logger.info("Done. Total=%d, Written=%d, Skipped(noop=%d, empty=%d, no_job=%d)",
                stats["total"], stats["written"],
                stats["skipped_noop"], stats["skipped_empty"], stats["skipped_no_job"])
    logger.info("Output: %s", args.output)


if __name__ == "__main__":
    main()
