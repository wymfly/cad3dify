"""Organic graph nodes: spec building."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.core.organic_spec_builder import OrganicSpecBuilder
from backend.graph.llm_utils import map_exception_to_failure_reason
from backend.graph.nodes.lifecycle import _safe_dispatch
from backend.graph.registry import register_node
from backend.graph.state import CadJobState
from backend.models.job import update_job as _update_job
from backend.models.organic import OrganicConstraints, OrganicGenerateRequest

logger = logging.getLogger(__name__)

LLM_TIMEOUT_S = 60


async def _safe_update_job(job_id: str, **kwargs: Any) -> None:
    """Update DB job, tolerating missing records (e.g. in unit tests)."""
    try:
        await _update_job(job_id, **kwargs)
    except (KeyError, Exception) as exc:
        logger.debug("_safe_update_job(%s) skipped: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Node 1: Analyze organic input → build OrganicSpec via LLM
# ---------------------------------------------------------------------------


@register_node(name="analyze_organic", display_name="有机形态分析",
    requires=["job_info"], produces=["organic_spec"], input_types=["organic"])
async def analyze_organic_node(state: CadJobState) -> dict[str, Any]:
    """Build OrganicSpec via LLM, dispatch spec_ready event, pause for HITL."""
    job_id = state["job_id"]
    input_text = state.get("input_text") or ""
    constraints_raw = state.get("organic_constraints")
    quality_mode = state.get("organic_quality_mode") or "standard"

    # Build OrganicGenerateRequest from state
    constraints = OrganicConstraints(**(constraints_raw or {}))
    request = OrganicGenerateRequest(
        prompt=input_text,
        reference_image=state.get("organic_reference_image"),
        constraints=constraints,
        quality_mode=quality_mode,
        provider=state.get("organic_provider") or "auto",
    )

    builder = OrganicSpecBuilder()
    try:
        spec = await asyncio.wait_for(builder.build(request), timeout=LLM_TIMEOUT_S)
    except asyncio.TimeoutError:
        error_msg = f"Organic spec 构建超时（{LLM_TIMEOUT_S}s）"
        await _safe_update_job(job_id, status="failed", error=error_msg)
        await _safe_dispatch("job.failed", {
            "job_id": job_id, "error": error_msg,
            "failure_reason": "timeout", "status": "failed",
        })
        return {
            "error": error_msg, "failure_reason": "timeout", "status": "failed",
            "_reasoning": {"error": error_msg},
        }
    except Exception as exc:
        reason = map_exception_to_failure_reason(exc)
        await _safe_update_job(job_id, status="failed", error=str(exc))
        await _safe_dispatch("job.failed", {
            "job_id": job_id, "error": str(exc),
            "failure_reason": reason, "status": "failed",
        })
        return {
            "error": str(exc), "failure_reason": reason, "status": "failed",
            "_reasoning": {"error": str(exc)},
        }

    spec_dict = spec.model_dump()

    # Persist to DB so GET /api/v1/jobs/{id} returns spec on page refresh
    await _safe_update_job(job_id, status="awaiting_confirmation", organic_spec=spec_dict)
    # Business event: carries organic_spec for frontend OrganicWorkflow confirmation UI
    await _safe_dispatch("job.organic_spec_ready", {
        "job_id": job_id, "status": "organic_spec_ready",
        "organic_spec": spec_dict,
    })
    await _safe_dispatch("job.awaiting_confirmation", {
        "job_id": job_id, "status": "awaiting_confirmation",
    })

    return {
        "organic_spec": spec_dict,
        "status": "awaiting_confirmation",
        "_reasoning": {
            "quality_mode": quality_mode,
            "provider": state.get("organic_provider") or "auto",
            "has_reference_image": str(bool(state.get("organic_reference_image"))),
            "prompt_preview": input_text[:100] if input_text else "N/A",
        },
    }
