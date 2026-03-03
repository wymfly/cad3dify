"""LocalModelStrategy — base class for local HTTP model endpoints.

Provides:
- Health check with TTL cache: GET {endpoint}/health
- Generation POST: POST {endpoint}/v1/generate (multipart/form-data)
- Output file saving helper
"""

from __future__ import annotations

import logging
import tempfile
import time
from abc import abstractmethod
from pathlib import Path
from typing import Any

import httpx

from backend.graph.descriptor import NodeStrategy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level health check cache
# ---------------------------------------------------------------------------

_CACHE_TTL = 30  # seconds

# Cache: endpoint -> (result: bool, timestamp: float)
_health_cache: dict[str, tuple[bool, float]] = {}


class LocalModelStrategy(NodeStrategy):
    """Base class for strategies that call a local HTTP model endpoint.

    Subclasses implement execute() and use _check_endpoint_health() and
    _post_generate() to interact with the local model service.
    """

    def __init__(self, config=None):
        super().__init__(config)

    def _check_endpoint_health(self, endpoint: str) -> bool:
        """Check endpoint health via GET {endpoint}/health with TTL cache.

        Returns True if status 200, False otherwise. Results are cached
        for _CACHE_TTL seconds.
        """
        # Check cache
        if endpoint in _health_cache:
            cached_result, cached_time = _health_cache[endpoint]
            if time.monotonic() - cached_time < _CACHE_TTL:
                return cached_result

        # Perform health check
        url = f"{endpoint.rstrip('/')}/health"
        timeout = getattr(self.config, "timeout", 120)
        check_timeout = min(timeout, 5)  # Cap health check at 5s
        try:
            resp = httpx.get(url, timeout=check_timeout)
            result = resp.status_code == 200
        except Exception as exc:
            logger.warning("Health check failed for %s: %s", url, exc)
            result = False

        _health_cache[endpoint] = (result, time.monotonic())
        return result

    async def _post_generate(
        self,
        endpoint: str,
        image_data: bytes | None = None,
        params: dict[str, Any] | None = None,
        timeout: int = 120,
    ) -> tuple[bytes, str]:
        """POST multipart/form-data to {endpoint}/v1/generate.

        Args:
            endpoint: Base URL of the local model service.
            image_data: Optional reference image bytes.
            params: Additional generation parameters.
            timeout: Request timeout in seconds.

        Returns:
            Tuple of (response_bytes, content_type).
        """
        url = f"{endpoint.rstrip('/')}/v1/generate"

        files: dict[str, Any] = {}
        if image_data is not None:
            files["image"] = ("input.png", image_data, "image/png")

        data = params or {}

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, files=files or None, data=data)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "application/octet-stream")
            return resp.content, content_type

    @staticmethod
    def _save_output(
        data: bytes,
        job_id: str,
        suffix: str = ".glb",
        prefix: str = "generate",
    ) -> str:
        """Save raw mesh bytes to a temp file and return the path."""
        output_dir = Path(tempfile.gettempdir()) / "cadpilot" / prefix
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{job_id}{suffix}"
        output_path.write_bytes(data)
        return str(output_path)

    @abstractmethod
    async def execute(self, ctx: Any) -> Any:
        """Subclasses implement the actual generation call."""
        ...
