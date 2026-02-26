"""Tests for print profile management API (Phase 4 Task 4.9).

Tests call the async handler functions directly (via ``asyncio.run``) to
avoid dependency on ``httpx``/``TestClient`` which is stubbed in conftest.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import backend.api.print_config as pc_api
from backend.core.printability import PRESET_PROFILES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _use_tmp_profiles(tmp_path, monkeypatch):
    """Point API to a tmp directory for custom profiles."""
    monkeypatch.setattr(pc_api, "_CUSTOM_PROFILES_DIR", tmp_path)


# ---------------------------------------------------------------------------
# GET /print-profiles — list
# ---------------------------------------------------------------------------


class TestListProfiles:
    def test_list_includes_presets(self) -> None:
        result = asyncio.run(pc_api.list_profiles())
        names = {p["name"] for p in result}
        assert "fdm_standard" in names
        assert "sla_standard" in names
        assert "sls_standard" in names

    def test_presets_marked(self) -> None:
        result = asyncio.run(pc_api.list_profiles())
        for p in result:
            if p["name"] in PRESET_PROFILES:
                assert p["is_preset"] is True

    def test_list_returns_sorted(self) -> None:
        result = asyncio.run(pc_api.list_profiles())
        names = [p["name"] for p in result]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# GET /print-profiles/{name} — get single
# ---------------------------------------------------------------------------


class TestGetProfile:
    def test_get_preset(self) -> None:
        result = asyncio.run(pc_api.get_profile("fdm_standard"))
        assert result["name"] == "fdm_standard"
        assert result["is_preset"] is True
        assert result["technology"] == "FDM"

    def test_get_not_found(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(pc_api.get_profile("nonexistent"))
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /print-profiles — create
# ---------------------------------------------------------------------------


CUSTOM_PROFILE = {
    "name": "my_fdm",
    "technology": "FDM",
    "min_wall_thickness": 1.0,
    "max_overhang_angle": 50.0,
    "min_hole_diameter": 2.5,
    "min_rib_thickness": 1.0,
    "build_volume": [300, 300, 400],
}


class TestCreateProfile:
    def test_create_custom(self) -> None:
        result = asyncio.run(pc_api.create_profile(CUSTOM_PROFILE.copy()))
        assert result["name"] == "my_fdm"
        assert result["is_preset"] is False

        # Verify readable
        got = asyncio.run(pc_api.get_profile("my_fdm"))
        assert got["name"] == "my_fdm"
        assert got["min_wall_thickness"] == 1.0

    def test_create_duplicate_fails(self) -> None:
        asyncio.run(pc_api.create_profile(CUSTOM_PROFILE.copy()))
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(pc_api.create_profile(CUSTOM_PROFILE.copy()))
        assert exc_info.value.status_code == 409

    def test_create_preset_name_blocked(self) -> None:
        body = CUSTOM_PROFILE.copy()
        body["name"] = "fdm_standard"
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(pc_api.create_profile(body))
        assert exc_info.value.status_code == 409

    def test_custom_appears_in_list(self) -> None:
        asyncio.run(pc_api.create_profile(CUSTOM_PROFILE.copy()))
        result = asyncio.run(pc_api.list_profiles())
        names = {p["name"] for p in result}
        assert "my_fdm" in names


# ---------------------------------------------------------------------------
# PUT /print-profiles/{name} — update
# ---------------------------------------------------------------------------


class TestUpdateProfile:
    def test_update_custom(self) -> None:
        asyncio.run(pc_api.create_profile(CUSTOM_PROFILE.copy()))
        updated = CUSTOM_PROFILE.copy()
        updated["min_wall_thickness"] = 1.2
        result = asyncio.run(pc_api.update_profile("my_fdm", updated))
        assert result["min_wall_thickness"] == 1.2

    def test_update_preset_blocked(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                pc_api.update_profile("fdm_standard", CUSTOM_PROFILE.copy())
            )
        assert exc_info.value.status_code == 403

    def test_update_not_found(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                pc_api.update_profile("ghost", CUSTOM_PROFILE.copy())
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /print-profiles/{name}
# ---------------------------------------------------------------------------


class TestDeleteProfile:
    def test_delete_custom(self) -> None:
        asyncio.run(pc_api.create_profile(CUSTOM_PROFILE.copy()))
        result = asyncio.run(pc_api.delete_profile("my_fdm"))
        assert result["status"] == "deleted"

        # Verify gone
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(pc_api.get_profile("my_fdm"))
        assert exc_info.value.status_code == 404

    def test_delete_preset_blocked(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(pc_api.delete_profile("fdm_standard"))
        assert exc_info.value.status_code == 403

    def test_delete_not_found(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(pc_api.delete_profile("nonexistent"))
        assert exc_info.value.status_code == 404
