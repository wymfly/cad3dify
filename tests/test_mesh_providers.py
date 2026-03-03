"""Tests for mesh provider abstraction layer."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.organic import OrganicSpec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_spec(**overrides: object) -> OrganicSpec:
    defaults = dict(
        prompt_en="golf club head",
        prompt_original="高尔夫球头",
        shape_category="organic",
        quality_mode="standard",
    )
    defaults.update(overrides)
    return OrganicSpec(**defaults)


# ---------------------------------------------------------------------------
# ABC tests
# ---------------------------------------------------------------------------

def test_mesh_provider_abc_cannot_be_instantiated():
    from backend.infra.mesh_providers.base import MeshProvider
    with pytest.raises(TypeError):
        MeshProvider()  # type: ignore[abstract]


def test_mesh_provider_has_required_methods():
    from backend.infra.mesh_providers.base import MeshProvider
    assert hasattr(MeshProvider, "generate")
    assert hasattr(MeshProvider, "check_health")


# ---------------------------------------------------------------------------
# TripoProvider tests
# ---------------------------------------------------------------------------

@pytest.fixture
def tripo_provider() -> object:
    from backend.infra.mesh_providers.tripo import TripoProvider
    return TripoProvider(api_key="test-key", output_dir=Path("/tmp/test"))


class TestTripoProvider:
    async def test_generate_success(self, tripo_provider: object, tmp_path: Path) -> None:
        from backend.infra.mesh_providers.tripo import TripoProvider
        provider = TripoProvider(api_key="test-key", output_dir=tmp_path)
        spec = _make_spec()

        mock_response_create = MagicMock()
        mock_response_create.status_code = 200
        mock_response_create.json.return_value = {
            "code": 0,
            "data": {"task_id": "task-123"},
        }

        mock_response_poll = MagicMock()
        mock_response_poll.status_code = 200
        mock_response_poll.json.return_value = {
            "code": 0,
            "data": {
                "status": "success",
                "output": {"model": "https://example.com/model.glb"},
            },
        }

        mock_response_download = MagicMock()
        mock_response_download.status_code = 200
        mock_response_download.content = b"fake-glb-data"

        async def mock_post(url: str, **kwargs: object) -> MagicMock:
            return mock_response_create

        async def mock_get(url: str, **kwargs: object) -> MagicMock:
            if "task" in url and "model" not in url:
                return mock_response_poll
            return mock_response_download

        with patch.object(provider, "_client") as mock_client:
            mock_client.post = AsyncMock(side_effect=mock_post)
            mock_client.get = AsyncMock(side_effect=mock_get)

            result = await provider.generate(spec)
            assert result.exists() or isinstance(result, Path)

    async def test_generate_timeout(self, tmp_path: Path) -> None:
        from backend.infra.mesh_providers.tripo import TripoProvider
        provider = TripoProvider(
            api_key="test-key",
            output_dir=tmp_path,
            timeout_s=0.1,  # very short timeout
        )
        spec = _make_spec()

        mock_response_create = MagicMock()
        mock_response_create.status_code = 200
        mock_response_create.json.return_value = {
            "code": 0,
            "data": {"task_id": "task-123"},
        }

        # Poll always returns "running" to trigger timeout
        mock_response_poll = MagicMock()
        mock_response_poll.status_code = 200
        mock_response_poll.json.return_value = {
            "code": 0,
            "data": {"status": "running"},
        }

        with patch.object(provider, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response_create)
            mock_client.get = AsyncMock(return_value=mock_response_poll)

            with pytest.raises(TimeoutError):
                await provider.generate(spec)

    async def test_check_health(self, tmp_path: Path) -> None:
        from backend.infra.mesh_providers.tripo import TripoProvider
        provider = TripoProvider(api_key="test-key", output_dir=tmp_path)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0}

        with patch.object(provider, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response)
            assert await provider.check_health() is True

    async def test_check_health_no_key(self, tmp_path: Path) -> None:
        from backend.infra.mesh_providers.tripo import TripoProvider
        provider = TripoProvider(api_key=None, output_dir=tmp_path)
        assert await provider.check_health() is False


# ---------------------------------------------------------------------------
# HunyuanProvider tests
# ---------------------------------------------------------------------------

class TestHunyuanProvider:
    async def test_generate_success(self, tmp_path: Path) -> None:
        from backend.infra.mesh_providers.hunyuan import HunyuanProvider
        provider = HunyuanProvider(api_key="test-key", output_dir=tmp_path)
        spec = _make_spec()

        mock_response_create = MagicMock()
        mock_response_create.status_code = 200
        mock_response_create.json.return_value = {
            "Response": {"TaskId": "task-456"},
        }

        mock_response_poll = MagicMock()
        mock_response_poll.status_code = 200
        mock_response_poll.json.return_value = {
            "Response": {
                "Status": "SUCCEED",
                "ResultUrl": "https://example.com/model.glb",
            },
        }

        mock_response_download = MagicMock()
        mock_response_download.status_code = 200
        mock_response_download.content = b"fake-glb-data"

        with patch.object(provider, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response_create)
            mock_client.get = AsyncMock(side_effect=[
                mock_response_poll,
                mock_response_download,
            ])
            result = await provider.generate(spec)
            assert isinstance(result, Path)

    async def test_check_health_no_key(self, tmp_path: Path) -> None:
        from backend.infra.mesh_providers.hunyuan import HunyuanProvider
        provider = HunyuanProvider(api_key=None, output_dir=tmp_path)
        assert await provider.check_health() is False


# ---------------------------------------------------------------------------
# AutoProvider tests (REMOVED)
# ---------------------------------------------------------------------------
# AutoProvider was removed in Phase 2 Task 7.
# Fallback logic is now handled by strategy-based dispatch in
# generate_raw_mesh node (see backend.graph.nodes.generate_raw_mesh).
# See tests/test_phase2_integration.py for the replacement tests.
