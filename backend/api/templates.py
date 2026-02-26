"""Template management API — CRUD + validate.

Provides RESTful endpoints for parametric template management:
- GET    /templates           list all (optional ?part_type= filter)
- GET    /templates/{name}    get single template
- POST   /templates           create new template
- PUT    /templates/{name}    update existing template
- DELETE /templates/{name}    delete template
- POST   /templates/{name}/validate   validate params against template
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.template_engine import TemplateEngine
from backend.models.template import ParametricTemplate

router = APIRouter()

# Templates directory — overridable for testing via monkeypatch.
_TEMPLATES_DIR = Path(__file__).parent.parent / "knowledge" / "templates"


def _get_engine() -> TemplateEngine:
    """Load a fresh engine from the templates directory."""
    return TemplateEngine.from_directory(_TEMPLATES_DIR)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ValidateResponse(BaseModel):
    """Result of parameter validation."""

    valid: bool
    errors: list[str]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/templates")
async def list_templates(part_type: Optional[str] = None) -> list[dict[str, Any]]:
    """List all templates, optionally filtered by ``part_type``."""
    engine = _get_engine()
    templates = engine.list_templates()
    if part_type:
        templates = [t for t in templates if t.part_type == part_type]
    return [t.model_dump() for t in templates]


@router.get("/templates/{name}")
async def get_template(name: str) -> dict[str, Any]:
    """Return a single template by name (404 if not found)."""
    engine = _get_engine()
    try:
        tmpl = engine.get_template(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
    return tmpl.model_dump()


@router.post("/templates", status_code=201)
async def create_template(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new template (409 if name already exists)."""
    tmpl = ParametricTemplate.model_validate(body)
    path = _TEMPLATES_DIR / f"{tmpl.name}.yaml"
    if path.exists():
        raise HTTPException(
            status_code=409, detail=f"Template '{tmpl.name}' already exists"
        )
    path.write_text(tmpl.to_yaml_string(), encoding="utf-8")
    return tmpl.model_dump()


@router.put("/templates/{name}")
async def update_template(name: str, body: dict[str, Any]) -> dict[str, Any]:
    """Update an existing template (404 if not found)."""
    path = _TEMPLATES_DIR / f"{name}.yaml"
    if not path.exists():
        # Try glob match for templates stored with prefixed filenames.
        matches = list(_TEMPLATES_DIR.glob(f"*{name}*.yaml"))
        if not matches:
            raise HTTPException(
                status_code=404, detail=f"Template '{name}' not found"
            )
        path = matches[0]
    tmpl = ParametricTemplate.model_validate(body)
    path.write_text(tmpl.to_yaml_string(), encoding="utf-8")
    return tmpl.model_dump()


@router.delete("/templates/{name}")
async def delete_template(name: str) -> dict[str, str]:
    """Delete a template by name (404 if not found)."""
    path = _TEMPLATES_DIR / f"{name}.yaml"
    if not path.exists():
        matches = list(_TEMPLATES_DIR.glob(f"*{name}*.yaml"))
        if not matches:
            raise HTTPException(
                status_code=404, detail=f"Template '{name}' not found"
            )
        path = matches[0]
    path.unlink()
    return {"status": "deleted", "name": name}


@router.post("/templates/{name}/validate")
async def validate_params(name: str, body: dict[str, Any]) -> ValidateResponse:
    """Validate parameters against a template's definitions and constraints."""
    engine = _get_engine()
    try:
        errors = engine.validate(name, body)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Template '{name}' not found"
        )
    return ValidateResponse(valid=len(errors) == 0, errors=errors)
