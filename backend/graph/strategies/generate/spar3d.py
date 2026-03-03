"""SPAR3DGenerateStrategy — local-only via LocalModelStrategy."""

from __future__ import annotations

import logging
from typing import Any

from backend.graph.strategies.generate.base import LocalModelStrategy

logger = logging.getLogger(__name__)


class SPAR3DGenerateStrategy(LocalModelStrategy):
    """SPAR3D mesh generation — local HTTP endpoint only.

    No SaaS fallback. Requires spar3d_endpoint to be configured
    and healthy.
    """

    def check_available(self) -> bool:
        """Available if spar3d_endpoint is configured and healthy."""
        endpoint = getattr(self.config, "spar3d_endpoint", None)
        if not endpoint:
            return False
        return self._check_endpoint_health(endpoint)

    async def execute(self, ctx: Any) -> None:
        """Generate mesh via local SPAR3D endpoint."""
        endpoint = self.config.spar3d_endpoint
        timeout = getattr(self.config, "timeout", 120)
        output_format = getattr(self.config, "output_format", "glb")

        # Get generation input from context
        gen_input = ctx.get_data("confirmed_params") or ctx.get_data("generation_input")
        if gen_input is None:
            gen_input = {}
        prompt_en = gen_input.get("prompt_en", "")
        reference_image = gen_input.get("reference_image", None)

        await ctx.dispatch_progress(1, 3, "SPAR3D 生成中")

        image_bytes = reference_image if isinstance(reference_image, bytes) else None
        data, content_type = await self._post_generate(
            endpoint=endpoint,
            image_data=image_bytes,
            params={"prompt": prompt_en, "format": output_format},
            timeout=timeout,
        )

        await ctx.dispatch_progress(2, 3, "SPAR3D 生成完成")

        suffix = f".{output_format}"
        output_path = self._save_output(data, ctx.job_id, suffix, "spar3d")
        ctx.put_asset("raw_mesh", output_path, output_format)
        await ctx.dispatch_progress(3, 3, "资产注册完成")
