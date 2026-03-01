"""Tests for V1 export API — job_id based resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from backend.main import app

    return TestClient(app)


class TestExportRequest:
    """Test the V1 ExportRequest validation and endpoint routing."""

    def test_nonexistent_job_id_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/jobs/nonexistent-job/export",
            json={"config": {"format": "stl"}},
        )
        assert resp.status_code == 404
        assert "FILE_NOT_FOUND" in resp.json()["error"]["code"]

    def test_step_format_returns_raw_file(
        self, client: TestClient, tmp_path: Path, monkeypatch,
    ) -> None:
        """When format=step, the raw STEP file should be returned."""
        import backend.api.v1.export as export_mod
        import backend.infra.outputs as outputs_mod

        # Create a fake STEP file inside the allowed directory
        fake_outputs = tmp_path / "outputs"
        fake_outputs.mkdir()
        job_dir = fake_outputs / "test-job-step"
        job_dir.mkdir()
        step_file = job_dir / "model.step"
        step_file.write_text("STEP;fake")

        # Patch _ALLOWED_DIR and OUTPUTS_DIR
        monkeypatch.setattr(export_mod, "_ALLOWED_DIR", fake_outputs)
        monkeypatch.setattr(outputs_mod, "OUTPUTS_DIR", fake_outputs)

        resp = client.post(
            "/api/v1/jobs/test-job-step/export",
            json={"config": {"format": "step"}},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/STEP")
        assert resp.content == b"STEP;fake"

    def test_job_id_resolves_via_get_step_path(
        self, client: TestClient, tmp_path: Path, monkeypatch,
    ) -> None:
        """When job_id is provided, it should resolve through get_step_path."""
        import backend.api.v1.export as export_mod
        import backend.infra.outputs as outputs_mod

        fake_outputs = tmp_path / "outputs"
        fake_outputs.mkdir()
        job_dir = fake_outputs / "test-job-123"
        job_dir.mkdir()
        step_file = job_dir / "model.step"
        step_file.write_text("STEP;from-job")

        monkeypatch.setattr(outputs_mod, "OUTPUTS_DIR", fake_outputs)
        monkeypatch.setattr(export_mod, "_ALLOWED_DIR", fake_outputs)

        resp = client.post(
            "/api/v1/jobs/test-job-123/export",
            json={"config": {"format": "step"}},
        )
        assert resp.status_code == 200
        assert resp.content == b"STEP;from-job"
