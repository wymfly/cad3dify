"""Tests for organic graph nodes (analyze_organic_node)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.graph.nodes.organic import analyze_organic_node


@pytest.fixture
def base_state():
    return {
        "job_id": "test-organic-001",
        "input_type": "organic",
        "input_text": "一个小熊雕塑",
        "organic_provider": "auto",
        "organic_quality_mode": "standard",
        "organic_reference_image": None,
        "organic_constraints": None,
        "organic_warnings": [],
        "status": "created",
    }


# ---------------------------------------------------------------------------
# analyze_organic_node
# ---------------------------------------------------------------------------


class TestAnalyzeOrganicNode:
    @pytest.mark.asyncio
    async def test_success(self, base_state):
        mock_spec = {
            "prompt_en": "A small bear sculpture",
            "prompt_original": "一个小熊雕塑",
            "shape_category": "figurine",
            "suggested_bounding_box": [80, 60, 100],
            "final_bounding_box": [80, 60, 100],
            "engineering_cuts": [],
            "quality_mode": "standard",
        }
        with patch("backend.graph.nodes.organic.OrganicSpecBuilder") as MockBuilder:
            instance = MockBuilder.return_value
            instance.build = AsyncMock(return_value=MagicMock(model_dump=lambda: mock_spec))
            result = await analyze_organic_node(base_state)

        assert result["status"] == "awaiting_confirmation"
        assert result["organic_spec"] == mock_spec

    @pytest.mark.asyncio
    async def test_timeout(self, base_state):
        with patch("backend.graph.nodes.organic.OrganicSpecBuilder") as MockBuilder:
            instance = MockBuilder.return_value
            instance.build = AsyncMock(side_effect=asyncio.TimeoutError())
            result = await analyze_organic_node(base_state)

        assert result["status"] == "failed"
        assert result["failure_reason"] == "timeout"

    @pytest.mark.asyncio
    async def test_generic_error(self, base_state):
        with patch("backend.graph.nodes.organic.OrganicSpecBuilder") as MockBuilder:
            instance = MockBuilder.return_value
            instance.build = AsyncMock(side_effect=RuntimeError("LLM crash"))
            result = await analyze_organic_node(base_state)

        assert result["status"] == "failed"
        assert result["failure_reason"] == "generation_error"
