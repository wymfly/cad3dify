"""Pipeline configuration endpoints: tooltips and presets."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.models.pipeline_config import PRESETS, get_tooltips

router = APIRouter()


@router.get("/tooltips")
async def get_pipeline_tooltips() -> dict[str, Any]:
    return {k: v.model_dump() for k, v in get_tooltips().items()}


@router.get("/presets")
async def get_pipeline_presets() -> list[dict[str, Any]]:
    return [{"name": k, **v.model_dump()} for k, v in PRESETS.items()]
