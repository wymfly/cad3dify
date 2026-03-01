"""V1 导出端点 — 按 Job ID 导出 STEP/STL/3MF/glTF。

POST /api/v1/jobs/{job_id}/export  body: {config: {format: "step"|"stl"|"3mf"|"gltf"}}
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from backend.api.v1.errors import APIError, ErrorCode
from backend.core.format_exporter import ExportConfig, FormatExporter
from backend.infra.outputs import get_step_path

router = APIRouter(tags=["export"])

_ALLOWED_DIR = Path("outputs").resolve()

_MEDIA_TYPES = {
    "step": "application/STEP",
    "stl": "application/sla",
    "3mf": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
    "gltf": "model/gltf-binary",
}

_EXTENSIONS = {"step": ".step", "stl": ".stl", "3mf": ".3mf", "gltf": ".glb"}


class ExportRequest(BaseModel):
    """Request body for the export endpoint."""

    config: ExportConfig = ExportConfig()


@router.post("/jobs/{job_id}/export")
async def export_model(job_id: str, body: ExportRequest) -> FileResponse:
    """导出指定 Job 的模型文件。"""
    config = body.config

    resolved = get_step_path(job_id)
    if not resolved.is_relative_to(_ALLOWED_DIR):
        raise APIError(
            status_code=403,
            code=ErrorCode.VALIDATION_FAILED,
            message="Access denied: path outside allowed directory",
        )

    if not resolved.exists():
        raise APIError(
            status_code=404,
            code=ErrorCode.FILE_NOT_FOUND,
            message=f"STEP file not found for job {job_id}",
        )

    # Direct STEP download — no conversion needed
    if config.format == "step":
        return FileResponse(
            path=str(resolved),
            media_type=_MEDIA_TYPES["step"],
            filename="model.step",
        )

    ext = _EXTENSIONS[config.format]
    fd, out_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)

    exporter = FormatExporter()
    exporter.export(str(resolved), out_path, config)

    def _cleanup() -> None:
        Path(out_path).unlink(missing_ok=True)

    return FileResponse(
        path=out_path,
        media_type=_MEDIA_TYPES[config.format],
        filename=f"model{ext}",
        background=BackgroundTask(_cleanup),
    )
