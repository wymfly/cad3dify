"""Tests for analysis graph nodes."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.graph.state import CadJobState


class TestAnalyzeIntentNode:
    @pytest.mark.asyncio
    async def test_success_returns_intent(self) -> None:
        from backend.graph.nodes.analysis import analyze_intent_node

        state = CadJobState(
            job_id="t1", input_type="text", input_text="make a 50mm gear",
            status="created",
        )
        mock_intent = {"description": "gear", "parameters": {"diameter": 50}}
        with patch("backend.graph.nodes.analysis._parse_intent", new_callable=AsyncMock, return_value=mock_intent):
            result = await analyze_intent_node(state)

        assert result["intent"] == mock_intent
        assert result["status"] == "awaiting_confirmation"

    @pytest.mark.asyncio
    async def test_timeout_returns_failed(self) -> None:
        from backend.graph.nodes.analysis import analyze_intent_node

        state = CadJobState(
            job_id="t1", input_type="text", input_text="make a gear",
            status="created",
        )
        with patch(
            "backend.graph.nodes.analysis._parse_intent",
            new_callable=AsyncMock,
            side_effect=asyncio.TimeoutError(),
        ):
            result = await analyze_intent_node(state)

        assert result["status"] == "failed"
        assert result["failure_reason"] == "timeout"

    @pytest.mark.asyncio
    async def test_generic_error_returns_failed(self) -> None:
        from backend.graph.nodes.analysis import analyze_intent_node

        state = CadJobState(
            job_id="t1", input_type="text", input_text="make a gear",
            status="created",
        )
        with patch(
            "backend.graph.nodes.analysis._parse_intent",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ):
            result = await analyze_intent_node(state)

        assert result["status"] == "failed"
        assert result["failure_reason"] == "generation_error"


class TestAnalyzeVisionNode:
    @pytest.mark.asyncio
    async def test_success_returns_drawing_spec(self) -> None:
        from backend.graph.nodes.analysis import analyze_vision_node

        state = CadJobState(
            job_id="t1", input_type="drawing", image_path="/tmp/test.jpg",
            status="created",
        )
        mock_spec = MagicMock()
        mock_spec.model_dump.return_value = {"part_type": "rotational", "diameter": 30}
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = mock_spec
        mock_image = MagicMock(type="jpg", data="ZmFrZQ==")
        with (
            patch("backend.graph.nodes.analysis._cost_optimizer") as mock_optimizer,
            patch("backend.graph.nodes.analysis.ImageData") as mock_image_cls,
            patch("backend.graph.nodes.analysis.build_vision_analysis_chain", return_value=mock_chain),
        ):
            mock_optimizer.get_cached_result.return_value = None
            mock_image_cls.load_from_file.return_value = mock_image
            result = await analyze_vision_node(state)

        assert result["drawing_spec"] == {"part_type": "rotational", "diameter": 30}
        assert result["status"] == "awaiting_drawing_confirmation"

    @pytest.mark.asyncio
    async def test_timeout_returns_failed(self) -> None:
        from backend.graph.nodes.analysis import analyze_vision_node

        state = CadJobState(
            job_id="t1", input_type="drawing", image_path="/tmp/test.jpg",
            status="created",
        )
        mock_chain = AsyncMock()
        mock_chain.ainvoke.side_effect = asyncio.TimeoutError()
        mock_image = MagicMock(type="jpg", data="ZmFrZQ==")
        with (
            patch("backend.graph.nodes.analysis._cost_optimizer") as mock_optimizer,
            patch("backend.graph.nodes.analysis.ImageData") as mock_image_cls,
            patch("backend.graph.nodes.analysis.build_vision_analysis_chain", return_value=mock_chain),
        ):
            mock_optimizer.get_cached_result.return_value = None
            mock_image_cls.load_from_file.return_value = mock_image
            result = await analyze_vision_node(state)

        assert result["status"] == "failed"
        assert result["failure_reason"] == "timeout"


class TestAnalyzeOrganicNode:
    @pytest.mark.asyncio
    async def test_success_returns_organic_spec(self) -> None:
        from unittest.mock import MagicMock

        from backend.graph.nodes.organic import analyze_organic_node

        state = CadJobState(
            job_id="t1", input_type="organic", input_text="a dragon sculpture",
            status="created",
        )
        mock_spec = MagicMock()
        mock_spec.model_dump.return_value = {"prompt_en": "a dragon sculpture", "style": "organic"}
        mock_builder = MagicMock()
        mock_builder.build = AsyncMock(return_value=mock_spec)
        with patch(
            "backend.graph.nodes.organic.OrganicSpecBuilder",
            return_value=mock_builder,
        ):
            result = await analyze_organic_node(state)

        assert result["organic_spec"] == {"prompt_en": "a dragon sculpture", "style": "organic"}
        assert result["status"] == "awaiting_confirmation"
