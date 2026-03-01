"""V1 工程标准 API — 浏览、推荐、检查。

GET  /api/v1/standards
GET  /api/v1/standards/{category}
POST /api/v1/standards/recommend
POST /api/v1/standards/check
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core.engineering_standards import (
    ConstraintViolation,
    EngineeringStandards,
    ParamRecommendation,
    StandardEntry,
)

router = APIRouter(prefix="/standards", tags=["standards"])

# Standards directory — overridable for testing via monkeypatch.
_STANDARDS_DIR = Path(__file__).parent.parent.parent / "knowledge" / "standards"


def _get_standards() -> EngineeringStandards:
    """Load a fresh standards instance."""
    return EngineeringStandards(standards_dir=_STANDARDS_DIR)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class RecommendRequest(BaseModel):
    """Request body for parameter recommendation."""

    part_type: str
    known_params: dict[str, float]


class RecommendResponse(BaseModel):
    """Response for parameter recommendation."""

    recommendations: list[ParamRecommendation]


class CheckRequest(BaseModel):
    """Request body for constraint checking."""

    part_type: str
    params: dict[str, float]


class CheckResponse(BaseModel):
    """Response for constraint checking."""

    valid: bool
    violations: list[ConstraintViolation]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("")
async def list_categories() -> list[str]:
    """列出所有标准类别。"""
    eng = _get_standards()
    return eng.list_categories()


@router.get("/{category}")
async def get_category(category: str) -> list[dict[str, Any]]:
    """获取指定类别的所有标准条目。"""
    eng = _get_standards()
    entries = eng.get_category(category)
    return [e.model_dump() for e in entries]


@router.post("/recommend")
async def recommend_params(body: RecommendRequest) -> RecommendResponse:
    """基于工程标准推荐缺失参数。"""
    eng = _get_standards()
    recs = eng.recommend_params(body.part_type, body.known_params)
    return RecommendResponse(recommendations=recs)


@router.post("/check")
async def check_constraints(body: CheckRequest) -> CheckResponse:
    """检查给定参数的工程约束。"""
    eng = _get_standards()
    violations = eng.check_constraints(body.part_type, body.params)
    return CheckResponse(valid=len(violations) == 0, violations=violations)
