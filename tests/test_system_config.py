"""Tests for SystemConfigStore."""

import json
import os

import pytest

from backend.graph.system_config import SystemConfigStore


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "system_config.json"
    return SystemConfigStore(path=str(path))


class TestSystemConfigStore:
    def test_load_missing_file_returns_empty(self, store):
        assert store.load() == {}

    def test_save_and_load_roundtrip(self, store):
        data = {"generate_raw_mesh": {"hunyuan3d_api_key": "sk-test123"}}
        store.save(data)
        assert store.load() == data

    def test_get_node_existing(self, store):
        store.save({"generate_raw_mesh": {"key": "val"}})
        assert store.get_node("generate_raw_mesh") == {"key": "val"}

    def test_get_node_missing(self, store):
        store.save({"generate_raw_mesh": {"key": "val"}})
        assert store.get_node("mesh_healer") == {}

    def test_get_node_empty_store(self, store):
        assert store.get_node("anything") == {}

    def test_atomic_write_no_corruption(self, store, tmp_path):
        """Save creates valid JSON even if called repeatedly."""
        for i in range(5):
            store.save({"node": {"key": f"val-{i}"}})
        result = store.load()
        assert result == {"node": {"key": "val-4"}}
        # Verify no temp files left behind
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "system_config.json"
