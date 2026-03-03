"""Tests for mesh_healer dual-channel node."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh


class TestMeshDiagnosis:
    """diagnose() 按缺陷严重度分级。"""

    def _make_watertight_box(self) -> trimesh.Trimesh:
        """创建水密立方体用于测试。"""
        return trimesh.primitives.Box().to_mesh()

    def _make_open_mesh(self) -> trimesh.Trimesh:
        """创建有孔洞的非水密 mesh（删除一个面）。"""
        box = trimesh.primitives.Box().to_mesh()
        # 删除最后一个面制造孔洞
        faces = box.faces[:-1]
        return trimesh.Trimesh(vertices=box.vertices, faces=faces)

    def _make_flipped_normals(self) -> trimesh.Trimesh:
        """创建 normals 翻转的 mesh。"""
        box = trimesh.primitives.Box().to_mesh()
        # 翻转所有 face winding
        box.faces = np.fliplr(box.faces)
        return box

    def test_clean_mesh_diagnosed_as_clean(self):
        from backend.graph.strategies.heal.diagnose import diagnose

        mesh = self._make_watertight_box()
        result = diagnose(mesh)
        assert result.level == "clean"
        assert result.issues == []

    def test_flipped_normals_diagnosed_as_mild(self):
        from backend.graph.strategies.heal.diagnose import diagnose

        mesh = self._make_flipped_normals()
        result = diagnose(mesh)
        assert result.level in ("mild", "moderate")
        assert len(result.issues) > 0

    def test_open_mesh_diagnosed_as_moderate(self):
        from backend.graph.strategies.heal.diagnose import diagnose

        mesh = self._make_open_mesh()
        result = diagnose(mesh)
        assert result.level in ("moderate", "severe")
        assert len(result.issues) > 0

    def test_level_is_valid_literal(self):
        from backend.graph.strategies.heal.diagnose import diagnose

        mesh = self._make_watertight_box()
        result = diagnose(mesh)
        assert result.level in ("clean", "mild", "moderate", "severe")


class TestValidateRepair:
    """validate_repair() 检查修复结果。"""

    def test_watertight_mesh_passes(self):
        from backend.graph.strategies.heal.diagnose import validate_repair

        mesh = trimesh.primitives.Box().to_mesh()
        assert validate_repair(mesh) is True

    def test_non_watertight_fails(self):
        from backend.graph.strategies.heal.diagnose import validate_repair

        box = trimesh.primitives.Box().to_mesh()
        faces = box.faces[:-1]
        mesh = trimesh.Trimesh(vertices=box.vertices, faces=faces)
        assert validate_repair(mesh) is False

    def test_empty_mesh_fails(self):
        from backend.graph.strategies.heal.diagnose import validate_repair

        mesh = trimesh.Trimesh()
        assert validate_repair(mesh) is False
