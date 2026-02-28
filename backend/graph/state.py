"""CadJobState — the single state object flowing through the CAD Job StateGraph."""

from __future__ import annotations

from typing import TypedDict


class CadJobState(TypedDict, total=False):
    # ── Input ──
    job_id: str
    input_type: str              # "text" | "drawing" | "organic"
    input_text: str | None
    image_path: str | None

    # ── Analysis outputs ──
    intent: dict | None          # IntentSpec.model_dump()
    matched_template: str | None
    drawing_spec: dict | None    # DrawingSpec.model_dump()

    # ── HITL confirmation inputs ──
    confirmed_params: dict | None
    confirmed_spec: dict | None
    disclaimer_accepted: bool

    # ── Generation outputs ──
    step_path: str | None
    model_url: str | None        # GLB preview URL
    printability: dict | None

    # ── Status & error ──
    status: str                  # mirrors JobStatus value
    error: str | None
    failure_reason: str | None   # typed: timeout | rate_limited | invalid_json | generation_error


# Maps CadJobState field names → ORM JobModel column names where they differ.
STATE_TO_ORM_MAPPING: dict[str, str] = {
    "confirmed_spec": "drawing_spec_confirmed",
    "printability": "printability_result",
    "step_path": "output_step_path",
}
