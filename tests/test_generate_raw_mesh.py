"""Tests for generate_raw_mesh config + 4 model strategies."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# GenerateRawMeshConfig
# ---------------------------------------------------------------------------


class TestGenerateRawMeshConfig:
    def test_default_values(self):
        from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig

        cfg = GenerateRawMeshConfig()
        assert cfg.strategy == "hunyuan3d"
        assert cfg.hunyuan3d_api_key is None
        assert cfg.hunyuan3d_endpoint is None
        assert cfg.tripo3d_api_key is None
        assert cfg.spar3d_endpoint is None
        assert cfg.trellis_endpoint is None
        assert cfg.timeout == 120
        assert cfg.output_format == "glb"

    def test_inherits_base_node_config(self):
        from backend.graph.configs.base import BaseNodeConfig
        from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig

        assert issubclass(GenerateRawMeshConfig, BaseNodeConfig)

    def test_custom_values(self):
        from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig

        cfg = GenerateRawMeshConfig(
            strategy="tripo3d",
            tripo3d_api_key="sk-test",
            timeout=60,
            output_format="obj",
        )
        assert cfg.strategy == "tripo3d"
        assert cfg.tripo3d_api_key == "sk-test"
        assert cfg.timeout == 60
        assert cfg.output_format == "obj"

    def test_all_fields_settable(self):
        from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig

        cfg = GenerateRawMeshConfig(
            strategy="hunyuan3d",
            hunyuan3d_api_key="key1",
            hunyuan3d_endpoint="http://local:8080",
            tripo3d_api_key="key2",
            spar3d_endpoint="http://spar:9090",
            trellis_endpoint="http://trellis:7070",
            timeout=300,
            output_format="obj",
        )
        assert cfg.hunyuan3d_api_key == "key1"
        assert cfg.hunyuan3d_endpoint == "http://local:8080"
        assert cfg.tripo3d_api_key == "key2"
        assert cfg.spar3d_endpoint == "http://spar:9090"
        assert cfg.trellis_endpoint == "http://trellis:7070"


# ---------------------------------------------------------------------------
# LocalModelStrategy — health check + TTL cache
# ---------------------------------------------------------------------------


class TestLocalModelStrategy:
    """LocalModelStrategy base class with health check and TTL cache."""

    def _make_config(self, endpoint: str = "http://gpu:8090") -> MagicMock:
        cfg = MagicMock()
        cfg.timeout = 120
        return cfg

    def test_health_check_healthy(self):
        from backend.graph.strategies.generate.base import (
            LocalModelStrategy,
            _health_cache,
        )

        _health_cache.clear()

        cfg = self._make_config()
        endpoint = "http://gpu:8090"

        # Create a concrete subclass for testing
        class ConcreteLocal(LocalModelStrategy):
            async def execute(self, ctx):
                pass

        strategy = ConcreteLocal(config=cfg)

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch(
            "backend.graph.strategies.generate.base.httpx.get",
            return_value=mock_resp,
        ) as mock_get:
            result = strategy._check_endpoint_health(endpoint)
            assert result is True
            mock_get.assert_called_once()

    def test_health_check_unhealthy(self):
        from backend.graph.strategies.generate.base import (
            LocalModelStrategy,
            _health_cache,
        )

        _health_cache.clear()

        cfg = self._make_config()
        endpoint = "http://gpu:8090"

        class ConcreteLocal(LocalModelStrategy):
            async def execute(self, ctx):
                pass

        strategy = ConcreteLocal(config=cfg)

        mock_resp = MagicMock()
        mock_resp.status_code = 503

        with patch(
            "backend.graph.strategies.generate.base.httpx.get",
            return_value=mock_resp,
        ):
            result = strategy._check_endpoint_health(endpoint)
            assert result is False

    def test_health_check_connection_error(self):
        from backend.graph.strategies.generate.base import (
            LocalModelStrategy,
            _health_cache,
        )

        _health_cache.clear()

        cfg = self._make_config()
        endpoint = "http://gpu:8090"

        class ConcreteLocal(LocalModelStrategy):
            async def execute(self, ctx):
                pass

        strategy = ConcreteLocal(config=cfg)

        with patch(
            "backend.graph.strategies.generate.base.httpx.get",
            side_effect=ConnectionError("refused"),
        ):
            result = strategy._check_endpoint_health(endpoint)
            assert result is False

    def test_health_check_ttl_cache_hit(self):
        from backend.graph.strategies.generate.base import (
            LocalModelStrategy,
            _health_cache,
            _CACHE_TTL,
        )

        _health_cache.clear()

        cfg = self._make_config()
        endpoint = "http://gpu:8090"

        class ConcreteLocal(LocalModelStrategy):
            async def execute(self, ctx):
                pass

        strategy = ConcreteLocal(config=cfg)

        # Pre-populate cache with healthy result
        _health_cache[endpoint] = (True, time.monotonic())

        with patch(
            "backend.graph.strategies.generate.base.httpx.get",
        ) as mock_get:
            result = strategy._check_endpoint_health(endpoint)
            assert result is True
            # Should NOT have made HTTP call — cache hit
            mock_get.assert_not_called()

    def test_health_check_ttl_cache_expired(self):
        from backend.graph.strategies.generate.base import (
            LocalModelStrategy,
            _health_cache,
            _CACHE_TTL,
        )

        _health_cache.clear()

        cfg = self._make_config()
        endpoint = "http://gpu:8090"

        class ConcreteLocal(LocalModelStrategy):
            async def execute(self, ctx):
                pass

        strategy = ConcreteLocal(config=cfg)

        # Pre-populate cache with expired entry
        _health_cache[endpoint] = (True, time.monotonic() - _CACHE_TTL - 1)

        mock_resp = MagicMock()
        mock_resp.status_code = 503

        with patch(
            "backend.graph.strategies.generate.base.httpx.get",
            return_value=mock_resp,
        ) as mock_get:
            result = strategy._check_endpoint_health(endpoint)
            assert result is False
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_generate(self):
        """_post_generate sends multipart POST to endpoint/v1/generate."""
        from backend.graph.strategies.generate.base import (
            LocalModelStrategy,
            _health_cache,
        )

        _health_cache.clear()

        cfg = self._make_config()

        class ConcreteLocal(LocalModelStrategy):
            async def execute(self, ctx):
                pass

        strategy = ConcreteLocal(config=cfg)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"mesh-data-bytes"
        mock_resp.headers = {"content-type": "model/gltf-binary"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch(
            "backend.graph.strategies.generate.base.httpx.AsyncClient",
            return_value=mock_client,
        ):
            data, content_type = await strategy._post_generate(
                endpoint="http://gpu:8090",
                image_data=b"image-bytes",
                params={"format": "glb"},
                timeout=120,
            )
            assert data == b"mesh-data-bytes"
            mock_client.post.assert_awaited_once()


# ---------------------------------------------------------------------------
# Hunyuan3DGenerateStrategy
# ---------------------------------------------------------------------------


class TestHunyuan3DGenerateStrategy:
    """Hunyuan3D: dual-deploy (local + SaaS)."""

    def _make_config(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        timeout: int = 120,
        output_format: str = "glb",
    ) -> MagicMock:
        cfg = MagicMock()
        cfg.hunyuan3d_endpoint = endpoint
        cfg.hunyuan3d_api_key = api_key
        cfg.timeout = timeout
        cfg.output_format = output_format
        return cfg

    # -- check_available --

    def test_check_available_local_healthy(self):
        from backend.graph.strategies.generate.base import _health_cache
        from backend.graph.strategies.generate.hunyuan3d import (
            Hunyuan3DGenerateStrategy,
        )

        _health_cache.clear()
        cfg = self._make_config(endpoint="http://gpu:8090")
        strategy = Hunyuan3DGenerateStrategy(config=cfg)

        with patch.object(strategy, "_check_endpoint_health", return_value=True):
            assert strategy.check_available() is True

    def test_check_available_local_unhealthy_saas_key(self):
        """Local unhealthy + SaaS api_key -> still available."""
        from backend.graph.strategies.generate.base import _health_cache
        from backend.graph.strategies.generate.hunyuan3d import (
            Hunyuan3DGenerateStrategy,
        )

        _health_cache.clear()
        cfg = self._make_config(
            endpoint="http://gpu:8090", api_key="sk-hunyuan"
        )
        strategy = Hunyuan3DGenerateStrategy(config=cfg)

        with patch.object(strategy, "_check_endpoint_health", return_value=False):
            assert strategy.check_available() is True

    def test_check_available_local_only_unhealthy(self):
        """Local endpoint configured but unhealthy, no SaaS key -> unavailable."""
        from backend.graph.strategies.generate.base import _health_cache
        from backend.graph.strategies.generate.hunyuan3d import (
            Hunyuan3DGenerateStrategy,
        )

        _health_cache.clear()
        cfg = self._make_config(endpoint="http://gpu:8090")
        strategy = Hunyuan3DGenerateStrategy(config=cfg)

        with patch.object(strategy, "_check_endpoint_health", return_value=False):
            assert strategy.check_available() is False

    def test_check_available_saas_only(self):
        """No endpoint, only SaaS api_key -> available."""
        from backend.graph.strategies.generate.hunyuan3d import (
            Hunyuan3DGenerateStrategy,
        )

        cfg = self._make_config(api_key="sk-hunyuan")
        strategy = Hunyuan3DGenerateStrategy(config=cfg)
        assert strategy.check_available() is True

    def test_check_available_no_config(self):
        """No endpoint and no api_key -> unavailable."""
        from backend.graph.strategies.generate.hunyuan3d import (
            Hunyuan3DGenerateStrategy,
        )

        cfg = self._make_config()
        strategy = Hunyuan3DGenerateStrategy(config=cfg)
        assert strategy.check_available() is False

    # -- execute --

    @pytest.mark.asyncio
    async def test_execute_local_priority(self):
        """Local endpoint healthy -> uses local, not SaaS."""
        from backend.graph.strategies.generate.hunyuan3d import (
            Hunyuan3DGenerateStrategy,
        )

        cfg = self._make_config(
            endpoint="http://gpu:8090", api_key="sk-hunyuan"
        )
        strategy = Hunyuan3DGenerateStrategy(config=cfg)

        ctx = MagicMock()
        ctx.get_data.return_value = {
            "prompt_en": "a gear", "reference_image": None,
        }
        ctx.dispatch_progress = AsyncMock()
        ctx.put_asset = MagicMock()
        ctx.job_id = "job-1"
        ctx.node_name = "generate_raw_mesh"

        with patch.object(
            strategy, "_check_endpoint_health", return_value=True
        ):
            with patch.object(
                strategy,
                "_post_generate",
                new_callable=AsyncMock,
                return_value=(b"mesh-data", "model/gltf-binary"),
            ) as mock_post:
                with patch.object(
                    strategy, "_save_output", return_value="/tmp/output.glb"
                ):
                    await strategy.execute(ctx)
                    mock_post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_local_fail_fallback_saas(self):
        """Local endpoint fails -> fallback to SaaS via HunyuanProvider."""
        from backend.graph.strategies.generate.hunyuan3d import (
            Hunyuan3DGenerateStrategy,
        )

        cfg = self._make_config(
            endpoint="http://gpu:8090", api_key="sk-hunyuan"
        )
        strategy = Hunyuan3DGenerateStrategy(config=cfg)

        ctx = MagicMock()
        ctx.get_data.return_value = {
            "prompt_en": "a gear",
            "reference_image": None,
        }
        ctx.dispatch_progress = AsyncMock()
        ctx.put_asset = MagicMock()
        ctx.job_id = "job-1"
        ctx.node_name = "generate_raw_mesh"

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=Path("/tmp/saas.glb"))

        with patch.object(
            strategy, "_check_endpoint_health", return_value=True
        ):
            with patch.object(
                strategy,
                "_post_generate",
                new_callable=AsyncMock,
                side_effect=RuntimeError("local timeout"),
            ):
                with patch.object(
                    strategy,
                    "_create_hunyuan_provider",
                    return_value=mock_provider,
                ):
                    await strategy.execute(ctx)
                    mock_provider.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_saas_only(self):
        """No local endpoint -> SaaS directly via HunyuanProvider."""
        from backend.graph.strategies.generate.hunyuan3d import (
            Hunyuan3DGenerateStrategy,
        )

        cfg = self._make_config(api_key="sk-hunyuan")
        strategy = Hunyuan3DGenerateStrategy(config=cfg)

        ctx = MagicMock()
        ctx.get_data.return_value = {
            "prompt_en": "a gear",
            "reference_image": None,
        }
        ctx.dispatch_progress = AsyncMock()
        ctx.put_asset = MagicMock()
        ctx.job_id = "job-1"
        ctx.node_name = "generate_raw_mesh"

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=Path("/tmp/saas.glb"))

        with patch.object(
            strategy,
            "_create_hunyuan_provider",
            return_value=mock_provider,
        ):
            await strategy.execute(ctx)
            mock_provider.generate.assert_awaited_once()

        # put_asset should have been called
        ctx.put_asset.assert_called_once()
        call_args = ctx.put_asset.call_args
        assert call_args[0][0] == "raw_mesh"


# ---------------------------------------------------------------------------
# Tripo3DGenerateStrategy
# ---------------------------------------------------------------------------


class TestTripo3DGenerateStrategy:
    """Tripo3D: SaaS-only via TripoProvider."""

    def _make_config(
        self, api_key: str | None = None, timeout: int = 120
    ) -> MagicMock:
        cfg = MagicMock()
        cfg.tripo3d_api_key = api_key
        cfg.timeout = timeout
        cfg.output_format = "glb"
        return cfg

    def test_check_available_with_key(self):
        from backend.graph.strategies.generate.tripo3d import (
            Tripo3DGenerateStrategy,
        )

        cfg = self._make_config(api_key="sk-tripo")
        strategy = Tripo3DGenerateStrategy(config=cfg)
        assert strategy.check_available() is True

    def test_check_available_without_key(self):
        from backend.graph.strategies.generate.tripo3d import (
            Tripo3DGenerateStrategy,
        )

        cfg = self._make_config()
        strategy = Tripo3DGenerateStrategy(config=cfg)
        assert strategy.check_available() is False

    @pytest.mark.asyncio
    async def test_execute_wraps_tripo_provider(self):
        from backend.graph.strategies.generate.tripo3d import (
            Tripo3DGenerateStrategy,
        )

        cfg = self._make_config(api_key="sk-tripo")
        strategy = Tripo3DGenerateStrategy(config=cfg)

        ctx = MagicMock()
        ctx.get_data.return_value = {
            "prompt_en": "a cup",
            "reference_image": None,
        }
        ctx.dispatch_progress = AsyncMock()
        ctx.put_asset = MagicMock()
        ctx.job_id = "job-2"
        ctx.node_name = "generate_raw_mesh"

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=Path("/tmp/tripo.glb"))

        with patch.object(
            strategy, "_create_tripo_provider", return_value=mock_provider
        ):
            await strategy.execute(ctx)
            mock_provider.generate.assert_awaited_once()

        ctx.put_asset.assert_called_once()
        call_args = ctx.put_asset.call_args
        assert call_args[0][0] == "raw_mesh"
        assert "glb" in call_args[0][2]


# ---------------------------------------------------------------------------
# SPAR3DGenerateStrategy
# ---------------------------------------------------------------------------


class TestSPAR3DGenerateStrategy:
    """SPAR3D: local-only via LocalModelStrategy."""

    def _make_config(
        self, endpoint: str | None = None, timeout: int = 120
    ) -> MagicMock:
        cfg = MagicMock()
        cfg.spar3d_endpoint = endpoint
        cfg.timeout = timeout
        cfg.output_format = "glb"
        return cfg

    def test_check_available_healthy(self):
        from backend.graph.strategies.generate.base import _health_cache
        from backend.graph.strategies.generate.spar3d import (
            SPAR3DGenerateStrategy,
        )

        _health_cache.clear()
        cfg = self._make_config(endpoint="http://spar:9090")
        strategy = SPAR3DGenerateStrategy(config=cfg)

        with patch.object(strategy, "_check_endpoint_health", return_value=True):
            assert strategy.check_available() is True

    def test_check_available_unhealthy(self):
        from backend.graph.strategies.generate.base import _health_cache
        from backend.graph.strategies.generate.spar3d import (
            SPAR3DGenerateStrategy,
        )

        _health_cache.clear()
        cfg = self._make_config(endpoint="http://spar:9090")
        strategy = SPAR3DGenerateStrategy(config=cfg)

        with patch.object(strategy, "_check_endpoint_health", return_value=False):
            assert strategy.check_available() is False

    def test_check_available_no_endpoint(self):
        from backend.graph.strategies.generate.spar3d import (
            SPAR3DGenerateStrategy,
        )

        cfg = self._make_config()
        strategy = SPAR3DGenerateStrategy(config=cfg)
        assert strategy.check_available() is False

    @pytest.mark.asyncio
    async def test_execute_calls_local_post(self):
        from backend.graph.strategies.generate.base import _health_cache
        from backend.graph.strategies.generate.spar3d import (
            SPAR3DGenerateStrategy,
        )

        _health_cache.clear()
        cfg = self._make_config(endpoint="http://spar:9090")
        strategy = SPAR3DGenerateStrategy(config=cfg)

        ctx = MagicMock()
        ctx.get_data.return_value = {
            "prompt_en": "a vase",
            "reference_image": b"image-bytes",
        }
        ctx.dispatch_progress = AsyncMock()
        ctx.put_asset = MagicMock()
        ctx.job_id = "job-3"
        ctx.node_name = "generate_raw_mesh"

        with patch.object(
            strategy,
            "_post_generate",
            new_callable=AsyncMock,
            return_value=(b"mesh-data", "model/gltf-binary"),
        ):
            with patch.object(
                strategy, "_save_output", return_value="/tmp/spar.glb"
            ):
                await strategy.execute(ctx)

        ctx.put_asset.assert_called_once()
        assert ctx.put_asset.call_args[0][0] == "raw_mesh"


# ---------------------------------------------------------------------------
# TRELLISGenerateStrategy
# ---------------------------------------------------------------------------


class TestTRELLISGenerateStrategy:
    """TRELLIS: local-only via LocalModelStrategy."""

    def _make_config(
        self, endpoint: str | None = None, timeout: int = 120
    ) -> MagicMock:
        cfg = MagicMock()
        cfg.trellis_endpoint = endpoint
        cfg.timeout = timeout
        cfg.output_format = "glb"
        return cfg

    def test_check_available_healthy(self):
        from backend.graph.strategies.generate.base import _health_cache
        from backend.graph.strategies.generate.trellis import (
            TRELLISGenerateStrategy,
        )

        _health_cache.clear()
        cfg = self._make_config(endpoint="http://trellis:7070")
        strategy = TRELLISGenerateStrategy(config=cfg)

        with patch.object(strategy, "_check_endpoint_health", return_value=True):
            assert strategy.check_available() is True

    def test_check_available_unhealthy(self):
        from backend.graph.strategies.generate.base import _health_cache
        from backend.graph.strategies.generate.trellis import (
            TRELLISGenerateStrategy,
        )

        _health_cache.clear()
        cfg = self._make_config(endpoint="http://trellis:7070")
        strategy = TRELLISGenerateStrategy(config=cfg)

        with patch.object(strategy, "_check_endpoint_health", return_value=False):
            assert strategy.check_available() is False

    def test_check_available_no_endpoint(self):
        from backend.graph.strategies.generate.trellis import (
            TRELLISGenerateStrategy,
        )

        cfg = self._make_config()
        strategy = TRELLISGenerateStrategy(config=cfg)
        assert strategy.check_available() is False

    @pytest.mark.asyncio
    async def test_execute_calls_local_post(self):
        from backend.graph.strategies.generate.base import _health_cache
        from backend.graph.strategies.generate.trellis import (
            TRELLISGenerateStrategy,
        )

        _health_cache.clear()
        cfg = self._make_config(endpoint="http://trellis:7070")
        strategy = TRELLISGenerateStrategy(config=cfg)

        ctx = MagicMock()
        ctx.get_data.return_value = {
            "prompt_en": "a lamp",
            "reference_image": b"image-bytes",
        }
        ctx.dispatch_progress = AsyncMock()
        ctx.put_asset = MagicMock()
        ctx.job_id = "job-4"
        ctx.node_name = "generate_raw_mesh"

        with patch.object(
            strategy,
            "_post_generate",
            new_callable=AsyncMock,
            return_value=(b"mesh-data", "model/gltf-binary"),
        ):
            with patch.object(
                strategy, "_save_output", return_value="/tmp/trellis.glb"
            ):
                await strategy.execute(ctx)

        ctx.put_asset.assert_called_once()
        assert ctx.put_asset.call_args[0][0] == "raw_mesh"
