"""Export endpoint: convert STEP to STL/3MF/glTF."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from backend.core.format_exporter import ExportConfig, FormatExporter

router = APIRouter()

_ALLOWED_DIR = Path("outputs").resolve()

_MEDIA_TYPES = {
    "stl": "application/sla",
    "3mf": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
    "gltf": "model/gltf-binary",
}

_EXTENSIONS = {"stl": ".stl", "3mf": ".3mf", "gltf": ".glb"}


@router.post("/export")
async def export_model(step_path: str, config: ExportConfig | None = None) -> FileResponse:
    config = config or ExportConfig()

    resolved = Path(step_path).resolve()
    if not resolved.is_relative_to(_ALLOWED_DIR):
        raise HTTPException(status_code=403, detail="Access denied: path outside allowed directory")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"STEP file not found: {step_path}")

    ext = _EXTENSIONS[config.format]
    fd, out_path = tempfile.mkstemp(suffix=ext)
    import os
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
