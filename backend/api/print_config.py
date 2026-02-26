"""Print profile management API — CRUD for print technology profiles.

Provides RESTful endpoints:
- GET    /print-profiles           list all profiles (presets + custom)
- GET    /print-profiles/{name}    get single profile
- POST   /print-profiles           create custom profile
- PUT    /print-profiles/{name}    update custom profile
- DELETE /print-profiles/{name}    delete custom profile (presets protected)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

from backend.core.printability import PRESET_PROFILES
from backend.models.printability import PrintProfile

router = APIRouter()

# Custom profiles directory — overridable for testing via monkeypatch.
_CUSTOM_PROFILES_DIR = Path(__file__).parent.parent / "knowledge" / "print_profiles"

_PRESET_NAMES = frozenset(PRESET_PROFILES.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_dir() -> Path:
    _CUSTOM_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return _CUSTOM_PROFILES_DIR


def _safe_dump(profile: PrintProfile) -> str:
    """Serialize a profile to YAML, converting tuples to lists for safe_load."""
    data = profile.model_dump()
    # build_volume is a tuple which yaml.dump serializes as !!python/tuple
    if isinstance(data.get("build_volume"), tuple):
        data["build_volume"] = list(data["build_volume"])
    return yaml.dump(data, default_flow_style=False, allow_unicode=True)


def _load_custom_profiles() -> dict[str, PrintProfile]:
    """Load custom profiles from YAML files."""
    d = _ensure_dir()
    profiles: dict[str, PrintProfile] = {}
    for f in sorted(d.glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        p = PrintProfile.model_validate(data)
        profiles[p.name] = p
    return profiles


def _all_profiles() -> dict[str, PrintProfile]:
    """Return presets + custom profiles (presets take precedence)."""
    merged = _load_custom_profiles()
    merged.update(PRESET_PROFILES)
    return merged


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/print-profiles")
async def list_profiles() -> list[dict[str, Any]]:
    """List all print profiles (presets + custom)."""
    profiles = _all_profiles()
    result = []
    for name, p in sorted(profiles.items()):
        d = p.model_dump()
        d["is_preset"] = name in _PRESET_NAMES
        result.append(d)
    return result


@router.get("/print-profiles/{name}")
async def get_profile(name: str) -> dict[str, Any]:
    """Return a single profile by name."""
    profiles = _all_profiles()
    if name not in profiles:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    d = profiles[name].model_dump()
    d["is_preset"] = name in _PRESET_NAMES
    return d


@router.post("/print-profiles", status_code=201)
async def create_profile(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new custom print profile."""
    p = PrintProfile.model_validate(body)
    if p.name in _PRESET_NAMES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot overwrite preset profile '{p.name}'",
        )
    d = _ensure_dir()
    path = d / f"{p.name}.yaml"
    if path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Profile '{p.name}' already exists",
        )
    path.write_text(
        _safe_dump(p),
        encoding="utf-8",
    )
    result = p.model_dump()
    result["is_preset"] = False
    return result


@router.put("/print-profiles/{name}")
async def update_profile(name: str, body: dict[str, Any]) -> dict[str, Any]:
    """Update a custom print profile (presets are read-only)."""
    if name in _PRESET_NAMES:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot modify preset profile '{name}'",
        )
    d = _ensure_dir()
    path = d / f"{name}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    p = PrintProfile.model_validate(body)
    path.write_text(
        _safe_dump(p),
        encoding="utf-8",
    )
    result = p.model_dump()
    result["is_preset"] = False
    return result


@router.delete("/print-profiles/{name}")
async def delete_profile(name: str) -> dict[str, str]:
    """Delete a custom print profile (presets cannot be deleted)."""
    if name in _PRESET_NAMES:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot delete preset profile '{name}'",
        )
    d = _ensure_dir()
    path = d / f"{name}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    path.unlink()
    return {"status": "deleted", "name": name}
