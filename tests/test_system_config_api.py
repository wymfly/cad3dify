"""Tests for system config API endpoints."""

from __future__ import annotations

import json

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig
from backend.graph.descriptor import NodeDescriptor
from backend.graph.registry import registry, enhance_config_schema


async def _noop(**kwargs):
    pass


_TEST_DESC = NodeDescriptor(
    name="generate_raw_mesh",
    display_name="Generate Raw Mesh",
    fn=_noop,
    config_model=GenerateRawMeshConfig,
)


@pytest.fixture(autouse=True)
def _register_test_node():
    """Ensure generate_raw_mesh is registered for all tests in this module."""
    if "generate_raw_mesh" not in registry:
        registry.register(_TEST_DESC)
    yield


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)


class TestSystemConfigSchemaEndpoint:
    def test_returns_only_system_fields(self, client):
        resp = client.get("/api/v1/pipeline/system-config-schema")
        assert resp.status_code == 200
        data = resp.json()
        assert "generate_raw_mesh" in data
        props = data["generate_raw_mesh"]["properties"]
        for field_name, field_schema in props.items():
            assert field_schema.get("x-scope") == "system"
        # engineering fields should NOT appear
        assert "timeout" not in props
        assert "output_format" not in props


class TestSystemConfigGetEndpoint:
    def test_returns_masked_sensitive_values(self, client):
        with patch("backend.api.v1.pipeline_config.system_config_store") as mock_store:
            mock_store.load.return_value = {
                "generate_raw_mesh": {"triposg_endpoint": "http://gpu:8081"}
            }
            resp = client.get("/api/v1/pipeline/system-config")
            assert resp.status_code == 200
            data = resp.json()
            # Non-sensitive system fields are returned as-is
            assert data["generate_raw_mesh"]["triposg_endpoint"] == "http://gpu:8081"


class TestSystemConfigPutEndpoint:
    def test_saves_valid_system_config(self, client):
        with patch("backend.api.v1.pipeline_config.system_config_store") as mock_store:
            mock_store.load.return_value = {}
            mock_store.save.return_value = None
            resp = client.put("/api/v1/pipeline/system-config", json={
                "generate_raw_mesh": {"hunyuan3d_endpoint": "https://example.com"}
            })
            assert resp.status_code == 200

    def test_rejects_engineering_field(self, client):
        resp = client.put("/api/v1/pipeline/system-config", json={
            "generate_raw_mesh": {"timeout": 999}
        })
        assert resp.status_code == 400
