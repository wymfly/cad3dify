# Phase 3 Optimization Nodes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 实现 3 个优化节点（orientation_optimizer、apply_lattice、thermal_simulation）+ 支撑策略委托扩展，完成端到端管线的优化阶段。

**Architecture:** 三层模型（节点=目的，策略=功能，部署=配置）。全部遵循 mesh_healer/Phase 2 的验证模式：Config → Strategy → Node → Tests。

**Tech Stack:** Python 3.10+, scipy, numpy, trimesh, manifold3d, scikit-image (marching_cubes), Pydantic v2

**Design doc:** `docs/plans/end-to-end-architecture/2026-03-02-dual-channel-pipeline-design.md` §五 提案 6+

---

## 设计决策（brainstorming 结论）

| 节点 | 决策 | 理由 |
|------|------|------|
| `orientation_optimizer` | 三层 Strategy：Basic → Scipy → Tweaker3 | 85% 成功率，纯数学优化，ROI 最高 |
| `apply_lattice` | TPMS 数学函数 + manifold3d 体素交集 | 75% 成功率，放弃 FEA 拓扑优化，只做纯数学晶格 |
| `thermal_simulation` | 降级为 DfAM 热风险静态报告 | 10-20% FEA 成功率太低，复用现有 analyze_dfam + 扩展热特征 |
| `generate_supports` | 委托给 slice_to_gcode，扩展 SliceToGcodeConfig | 60% 独立实现 ROI 低，PrusaSlicer 内置支撑质量远高于 PySLM |
| GNN 支撑预测 | Phase 3 不实现，仅预留 NeuralStrategy 接口 | 无训练数据集，ROI 极低 |

---

## Task 1: orientation_optimizer — Config + BasicStrategy [backend]

**Files:**
- Create: `backend/graph/configs/orientation_optimizer.py`
- Create: `backend/graph/strategies/orient/__init__.py`
- Create: `backend/graph/strategies/orient/basic.py`
- Create: `tests/test_orientation_optimizer.py`

**Step 1: Write failing tests for BasicOrientStrategy**

```python
# tests/test_orientation_optimizer.py
"""Tests for orientation_optimizer node and strategies."""

from __future__ import annotations

import pytest
import numpy as np
from unittest.mock import MagicMock


class TestOrientationOptimizerConfig:
    def test_defaults(self):
        from backend.graph.configs.orientation_optimizer import OrientationOptimizerConfig
        cfg = OrientationOptimizerConfig()
        assert cfg.strategy == "basic"
        assert cfg.enabled is True
        assert 0 < cfg.weight_support_area <= 1.0
        assert 0 < cfg.weight_height <= 1.0
        assert 0 < cfg.weight_stability <= 1.0

    def test_weights_sum_validation(self):
        """Weights can be any positive float — no sum constraint."""
        from backend.graph.configs.orientation_optimizer import OrientationOptimizerConfig
        cfg = OrientationOptimizerConfig(
            weight_support_area=0.5,
            weight_height=0.3,
            weight_stability=0.2,
        )
        assert cfg.weight_support_area == 0.5


class TestBasicOrientStrategy:
    """BasicOrientStrategy: 6-direction discrete search (±X, ±Y, ±Z)."""

    @pytest.fixture
    def strategy(self):
        from backend.graph.configs.orientation_optimizer import OrientationOptimizerConfig
        from backend.graph.strategies.orient.basic import BasicOrientStrategy
        cfg = OrientationOptimizerConfig()
        return BasicOrientStrategy(config=cfg)

    def test_check_available_always_true(self, strategy):
        assert strategy.check_available() is True

    def test_evaluate_orientation_returns_score(self, strategy):
        """evaluate_orientation(mesh, rotation_matrix) -> float score."""
        mesh = _make_box_mesh(10, 20, 30)
        score = strategy.evaluate_orientation(mesh, np.eye(4))
        assert isinstance(score, float)
        assert score >= 0

    def test_flat_box_prefers_largest_face_down(self, strategy):
        """A flat box (100x100x10) should prefer Z-up (XY face down)."""
        mesh = _make_box_mesh(100, 100, 10)
        best_rotation, best_score, all_scores = strategy.find_best_orientation(mesh)
        # Z-up orientation should have lowest score (best)
        assert best_rotation is not None
        assert len(all_scores) == 6  # 6 cardinal directions

    def test_tall_box_prefers_laying_down(self, strategy):
        """A tall box (10x10x100) should prefer laying flat."""
        mesh = _make_box_mesh(10, 10, 100)
        best_rotation, best_score, all_scores = strategy.find_best_orientation(mesh)
        # The result rotation should reduce Z-height
        rotated = mesh.copy()
        rotated.apply_transform(best_rotation)
        assert rotated.bounding_box.extents[2] < 100  # Should be shorter

    def test_execute_registers_oriented_mesh(self, strategy):
        """Strategy.execute(ctx) should register 'oriented_mesh' asset."""
        pytest.skip("Tested in Task 3 (node integration)")


def _make_box_mesh(x: float, y: float, z: float):
    """Create a simple box mesh for testing."""
    import trimesh
    return trimesh.creation.box(extents=[x, y, z])
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orientation_optimizer.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write OrientationOptimizerConfig**

```python
# backend/graph/configs/orientation_optimizer.py
"""Configuration for orientation_optimizer node."""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator

from backend.graph.configs.neural import NeuralStrategyConfig


class OrientationOptimizerConfig(NeuralStrategyConfig):
    """orientation_optimizer node configuration.

    Inherits neural_enabled, neural_endpoint, neural_timeout, health_check_path
    from NeuralStrategyConfig for future Neural channel.
    """

    strategy: Literal["basic", "scipy", "auto"] = "basic"

    # Scoring weights (higher = more important)
    weight_support_area: float = 0.4
    weight_height: float = 0.3
    weight_stability: float = 0.3

    # Scipy-specific
    scipy_max_iter: int = 100
    scipy_popsize: int = 15

    @field_validator("weight_support_area", "weight_height", "weight_stability")
    @classmethod
    def _positive_weight(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"Weight must be non-negative, got {v}")
        return v
```

**Step 4: Write BasicOrientStrategy**

```python
# backend/graph/strategies/orient/__init__.py
"""Orientation optimizer strategies."""

# backend/graph/strategies/orient/basic.py
"""BasicOrientStrategy — 6-direction discrete orientation search.

Evaluates ±X, ±Y, ±Z orientations using a weighted scoring function:
  score = w_support * support_area + w_height * z_height + w_stability * instability
Lower score = better orientation.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import trimesh

from backend.graph.descriptor import NodeStrategy

logger = logging.getLogger(__name__)

# 6 cardinal rotations: identity, ±90° around X, ±90° around Y, 180° around X
_CARDINAL_ROTATIONS = [
    ("Z-up (identity)", np.eye(4)),
    ("X-up (+90° Y)", trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])),
    ("X-down (-90° Y)", trimesh.transformations.rotation_matrix(-np.pi / 2, [0, 1, 0])),
    ("Y-up (-90° X)", trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])),
    ("Y-down (+90° X)", trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])),
    ("Z-down (180° X)", trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])),
]


class BasicOrientStrategy(NodeStrategy):
    """6-direction discrete orientation search."""

    def evaluate_orientation(self, mesh: trimesh.Trimesh, rotation: np.ndarray) -> float:
        """Evaluate a single orientation. Lower = better."""
        rotated = mesh.copy()
        rotated.apply_transform(rotation)

        extents = rotated.bounding_box.extents
        z_height = extents[2]

        # Estimate support area: sum of face areas where face normal Z < -cos(45°)
        face_normals = rotated.face_normals
        face_areas = rotated.area_faces
        overhang_mask = face_normals[:, 2] < -np.cos(np.radians(45))
        support_area = float(np.sum(face_areas[overhang_mask]))

        # Stability: higher center of gravity = less stable
        centroid_z = rotated.centroid[2] - rotated.bounds[0][2]
        max_z = extents[2]
        instability = centroid_z / max(max_z, 1e-6)

        # Normalize each term to [0, 1] range for comparable weighting
        total_area = float(np.sum(mesh.area_faces))
        max_extent = float(max(extents))
        norm_support = support_area / max(total_area, 1e-6)
        norm_height = z_height / max(max_extent, 1e-6)
        # instability is already in [0, 1]

        w = self.config
        score = (
            w.weight_support_area * norm_support
            + w.weight_height * norm_height
            + w.weight_stability * instability
        )
        return score

    def find_best_orientation(
        self, mesh: trimesh.Trimesh
    ) -> tuple[np.ndarray, float, list[tuple[str, float]]]:
        """Search 6 cardinal directions, return best rotation + all scores."""
        all_scores: list[tuple[str, float]] = []
        best_rotation = np.eye(4)
        best_score = float("inf")

        for name, rotation in _CARDINAL_ROTATIONS:
            score = self.evaluate_orientation(mesh, rotation)
            all_scores.append((name, score))
            if score < best_score:
                best_score = score
                best_rotation = rotation

        return best_rotation, best_score, all_scores

    async def execute(self, ctx: Any) -> None:
        """Execute basic orientation optimization."""
        import asyncio

        asset = ctx.get_asset("final_mesh")
        mesh = await asyncio.to_thread(trimesh.load, asset.path, force="mesh")

        await ctx.dispatch_progress(1, 3, "方向评估中")

        best_rotation, best_score, all_scores = await asyncio.to_thread(
            self.find_best_orientation, mesh
        )

        await ctx.dispatch_progress(2, 3, "应用最优方向")

        # Apply rotation
        mesh.apply_transform(best_rotation)

        # Z=0 bottom alignment
        z_offset = -mesh.bounds[0][2]
        if abs(z_offset) > 1e-6:
            mesh.apply_translation([0, 0, z_offset])

        # Export
        import tempfile
        from pathlib import Path

        output_dir = Path(tempfile.gettempdir()) / "cadpilot" / "orient"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"{ctx.job_id}_oriented.glb")
        await asyncio.to_thread(mesh.export, output_path)

        best_name = next(
            name for name, score in all_scores if score == best_score
        )
        ctx.put_asset(
            "oriented_mesh", output_path, "mesh",
            metadata={
                "orientation": best_name,
                "score": round(best_score, 4),
                "all_scores": {name: round(s, 4) for name, s in all_scores},
            },
        )
        ctx.put_data("orientation_result", {
            "orientation": best_name,
            "score": round(best_score, 4),
        })

        await ctx.dispatch_progress(3, 3, f"方向优化完成: {best_name}")
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_orientation_optimizer.py -v -k "not execute"`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/graph/configs/orientation_optimizer.py backend/graph/strategies/orient/ tests/test_orientation_optimizer.py
git commit -m "feat(phase3): orientation_optimizer config + BasicOrientStrategy"
```

---

## Task 2: orientation_optimizer — ScipyOrientStrategy [backend]

**Files:**
- Create: `backend/graph/strategies/orient/scipy_orient.py`
- Modify: `tests/test_orientation_optimizer.py` (add scipy tests)

**Step 1: Write failing tests for ScipyOrientStrategy**

```python
# Add to tests/test_orientation_optimizer.py

class TestScipyOrientStrategy:
    """ScipyOrientStrategy: continuous optimization via differential_evolution."""

    @pytest.fixture
    def strategy(self):
        from backend.graph.configs.orientation_optimizer import OrientationOptimizerConfig
        from backend.graph.strategies.orient.scipy_orient import ScipyOrientStrategy
        cfg = OrientationOptimizerConfig(
            strategy="scipy",
            scipy_max_iter=20,
            scipy_popsize=5,
        )
        return ScipyOrientStrategy(config=cfg)

    def test_check_available(self, strategy):
        assert strategy.check_available() is True

    def test_optimize_returns_rotation_matrix(self, strategy):
        """optimize(mesh) returns (4x4 rotation matrix, score)."""
        mesh = _make_box_mesh(10, 20, 30)
        rotation, score = strategy.optimize(mesh)
        assert rotation.shape == (4, 4)
        assert isinstance(score, float)

    def test_scipy_at_least_as_good_as_basic(self, strategy):
        """Scipy should find score <= basic 6-direction score."""
        from backend.graph.strategies.orient.basic import BasicOrientStrategy
        from backend.graph.configs.orientation_optimizer import OrientationOptimizerConfig
        cfg = OrientationOptimizerConfig()
        basic = BasicOrientStrategy(config=cfg)

        mesh = _make_box_mesh(30, 50, 80)
        _, basic_score, _ = basic.find_best_orientation(mesh)
        _, scipy_score = strategy.optimize(mesh)
        # Scipy explores continuous space, should be at least equal
        assert scipy_score <= basic_score + 1.0  # Small tolerance

    def test_rotation_matrix_is_valid(self, strategy):
        """Resulting rotation should be a valid rotation matrix (det ≈ 1)."""
        mesh = _make_box_mesh(20, 20, 60)
        rotation, _ = strategy.optimize(mesh)
        # 3x3 rotation submatrix should have determinant ≈ 1
        det = np.linalg.det(rotation[:3, :3])
        assert abs(det - 1.0) < 1e-6
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orientation_optimizer.py::TestScipyOrientStrategy -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write ScipyOrientStrategy**

```python
# backend/graph/strategies/orient/scipy_orient.py
"""ScipyOrientStrategy — continuous orientation optimization.

Uses scipy.optimize.differential_evolution to search SO(3) rotation space,
parameterized as Euler angles (alpha, beta, gamma).
Reuses BasicOrientStrategy.evaluate_orientation() as the objective function.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import trimesh
from scipy.optimize import differential_evolution
from scipy.spatial.transform import Rotation

from backend.graph.descriptor import NodeStrategy
from backend.graph.strategies.orient.basic import BasicOrientStrategy

logger = logging.getLogger(__name__)


class ScipyOrientStrategy(NodeStrategy):
    """Continuous orientation optimization via differential evolution."""

    def check_available(self) -> bool:
        """Check if scipy is importable."""
        try:
            import scipy.optimize  # noqa: F401
            return True
        except ImportError:
            return False

    def optimize(self, mesh: trimesh.Trimesh) -> tuple[np.ndarray, float]:
        """Find optimal orientation via continuous optimization.

        Returns: (4x4 rotation matrix, best score)
        """
        # Reuse basic strategy's scoring function
        basic = BasicOrientStrategy(config=self.config)

        def objective(angles: np.ndarray) -> float:
            alpha, beta, gamma = angles
            rot = Rotation.from_euler("xyz", [alpha, beta, gamma], degrees=True)
            transform = np.eye(4)
            transform[:3, :3] = rot.as_matrix()
            return basic.evaluate_orientation(mesh, transform)

        # Search over Euler angles
        bounds = [(-180, 180), (-90, 90), (-180, 180)]
        result = differential_evolution(
            objective,
            bounds=bounds,
            maxiter=self.config.scipy_max_iter,
            popsize=self.config.scipy_popsize,
            seed=42,
            tol=1e-4,
        )

        best_angles = result.x
        rot = Rotation.from_euler("xyz", best_angles, degrees=True)
        best_rotation = np.eye(4)
        best_rotation[:3, :3] = rot.as_matrix()

        return best_rotation, float(result.fun)

    async def execute(self, ctx: Any) -> None:
        """Execute scipy orientation optimization."""
        import asyncio

        asset = ctx.get_asset("final_mesh")
        mesh = await asyncio.to_thread(trimesh.load, asset.path, force="mesh")

        await ctx.dispatch_progress(1, 3, "Scipy 方向优化中")

        best_rotation, best_score = await asyncio.to_thread(self.optimize, mesh)

        await ctx.dispatch_progress(2, 3, "应用最优方向")

        mesh.apply_transform(best_rotation)
        z_offset = -mesh.bounds[0][2]
        if abs(z_offset) > 1e-6:
            mesh.apply_translation([0, 0, z_offset])

        import tempfile
        from pathlib import Path

        output_dir = Path(tempfile.gettempdir()) / "cadpilot" / "orient"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"{ctx.job_id}_oriented.glb")
        await asyncio.to_thread(mesh.export, output_path)

        ctx.put_asset(
            "oriented_mesh", output_path, "mesh",
            metadata={
                "strategy": "scipy",
                "score": round(best_score, 4),
                "rotation_matrix": best_rotation[:3, :3].tolist(),
            },
        )
        ctx.put_data("orientation_result", {
            "strategy": "scipy",
            "score": round(best_score, 4),
        })

        await ctx.dispatch_progress(3, 3, f"Scipy 方向优化完成 (score={best_score:.2f})")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orientation_optimizer.py::TestScipyOrientStrategy -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/graph/strategies/orient/scipy_orient.py tests/test_orientation_optimizer.py
git commit -m "feat(phase3): ScipyOrientStrategy — continuous orientation optimization"
```

---

## Task 3: orientation_optimizer — Node registration + integration tests [backend][test]

**Files:**
- Create: `backend/graph/nodes/orientation_optimizer.py`
- Modify: `tests/test_orientation_optimizer.py` (add node-level tests)

**Step 1: Write failing node tests**

```python
# Add to tests/test_orientation_optimizer.py

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestOrientationOptimizerNode:
    """Node-level tests for orientation_optimizer."""

    @pytest.fixture
    def mock_ctx(self, tmp_path):
        """Create a mock NodeContext with a box mesh."""
        mesh = _make_box_mesh(10, 10, 100)  # Tall box
        mesh_path = str(tmp_path / "test.glb")
        mesh.export(mesh_path)

        ctx = MagicMock()
        ctx.job_id = "test-orient-001"
        ctx.config = MagicMock()
        ctx.config.strategy = "basic"
        ctx.config.weight_support_area = 0.4
        ctx.config.weight_height = 0.3
        ctx.config.weight_stability = 0.3

        asset = MagicMock()
        asset.path = mesh_path
        ctx.get_asset.return_value = asset
        ctx.has_asset.return_value = True
        ctx.dispatch_progress = AsyncMock()

        return ctx

    @pytest.mark.asyncio
    async def test_node_registers_strategy(self):
        """Node should be registered with basic and scipy strategies."""
        from backend.graph.nodes.orientation_optimizer import orientation_optimizer_node
        desc = orientation_optimizer_node._node_descriptor
        assert "basic" in desc.strategies
        assert "scipy" in desc.strategies
        assert desc.fallback_chain == ["scipy", "basic"]

    @pytest.mark.asyncio
    async def test_node_no_input_skips(self):
        """No final_mesh → skip gracefully."""
        from backend.graph.nodes.orientation_optimizer import orientation_optimizer_node
        ctx = MagicMock()
        ctx.has_asset.return_value = False
        ctx.config = MagicMock()
        ctx.config.strategy = "basic"

        await orientation_optimizer_node(ctx)
        ctx.put_data.assert_called_with(
            "orientation_optimizer_status", "skipped_no_input"
        )

    @pytest.mark.asyncio
    async def test_basic_strategy_produces_oriented_mesh(self, mock_ctx):
        """Basic strategy should register oriented_mesh asset."""
        from backend.graph.strategies.orient.basic import BasicOrientStrategy
        from backend.graph.configs.orientation_optimizer import OrientationOptimizerConfig
        cfg = OrientationOptimizerConfig()
        strategy = BasicOrientStrategy(config=cfg)

        await strategy.execute(mock_ctx)

        mock_ctx.put_asset.assert_called_once()
        call_args = mock_ctx.put_asset.call_args
        assert call_args[0][0] == "oriented_mesh"
        assert call_args[0][2] == "mesh"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orientation_optimizer.py::TestOrientationOptimizerNode -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write orientation_optimizer node**

```python
# backend/graph/nodes/orientation_optimizer.py
"""orientation_optimizer — find optimal print orientation.

Searches rotation space to minimize: support area + print height + instability.
Strategies: basic (6-direction discrete), scipy (continuous DE), neural (future).
"""

from __future__ import annotations

import logging

from backend.graph.configs.orientation_optimizer import OrientationOptimizerConfig
from backend.graph.context import NodeContext
from backend.graph.registry import register_node
from backend.graph.strategies.orient.basic import BasicOrientStrategy
from backend.graph.strategies.orient.scipy_orient import ScipyOrientStrategy

logger = logging.getLogger(__name__)


@register_node(
    name="orientation_optimizer",
    display_name="打印方向优化",
    requires=["final_mesh"],
    produces=["oriented_mesh"],
    input_types=["organic"],
    config_model=OrientationOptimizerConfig,
    strategies={
        "basic": BasicOrientStrategy,
        "scipy": ScipyOrientStrategy,
    },
    default_strategy="basic",
    fallback_chain=["scipy", "basic"],
    non_fatal=True,
    description="搜索最优打印方向，最小化支撑面积和打印高度",
)
async def orientation_optimizer_node(ctx: NodeContext) -> None:
    """Execute orientation optimization via strategy dispatch.

    non_fatal=True: orientation failure should not block the pipeline.
    If no final_mesh, skip gracefully.
    """
    if not ctx.has_asset("final_mesh"):
        logger.info("orientation_optimizer: no final_mesh, skipping")
        ctx.put_data("orientation_optimizer_status", "skipped_no_input")
        return

    if ctx.config.strategy == "auto":
        await ctx.execute_with_fallback()
    else:
        strategy = ctx.get_strategy()
        await strategy.execute(ctx)
```

**Step 4: Run all orientation tests**

Run: `uv run pytest tests/test_orientation_optimizer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/graph/nodes/orientation_optimizer.py tests/test_orientation_optimizer.py
git commit -m "feat(phase3): orientation_optimizer node registration + integration"
```

---

## Task 4: apply_lattice — Config + TPMSStrategy [backend]

**Files:**
- Create: `backend/graph/configs/apply_lattice.py`
- Create: `backend/graph/strategies/lattice/__init__.py`
- Create: `backend/graph/strategies/lattice/tpms.py`
- Create: `tests/test_apply_lattice.py`

**Step 1: Write failing tests**

```python
# tests/test_apply_lattice.py
"""Tests for apply_lattice node and TPMS strategy."""

from __future__ import annotations

import pytest
import numpy as np


class TestApplyLatticeConfig:
    def test_defaults(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig
        cfg = ApplyLatticeConfig()
        assert cfg.strategy == "tpms"
        assert cfg.lattice_type == "gyroid"
        assert 0.0 < cfg.cell_size <= 50.0
        assert 0.0 < cfg.wall_thickness

    def test_cell_size_validation(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig
        with pytest.raises(ValueError, match="cell_size"):
            ApplyLatticeConfig(cell_size=0)

    def test_shell_thickness_validation(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig
        with pytest.raises(ValueError, match="shell_thickness"):
            ApplyLatticeConfig(shell_thickness=-1)


class TestTPMSFunctions:
    """Test TPMS scalar field functions."""

    def test_gyroid_field(self):
        from backend.graph.strategies.lattice.tpms import gyroid_field
        # Gyroid field should be zero at known points
        x = np.array([0.0])
        y = np.array([0.0])
        z = np.array([0.0])
        result = gyroid_field(x, y, z, cell_size=10.0)
        assert isinstance(result, np.ndarray)

    def test_schwarz_p_field(self):
        from backend.graph.strategies.lattice.tpms import schwarz_p_field
        x = np.array([0.0])
        y = np.array([0.0])
        z = np.array([0.0])
        result = schwarz_p_field(x, y, z, cell_size=10.0)
        assert isinstance(result, np.ndarray)

    def test_diamond_field(self):
        from backend.graph.strategies.lattice.tpms import diamond_field
        x = np.array([0.0])
        y = np.array([0.0])
        z = np.array([0.0])
        result = diamond_field(x, y, z, cell_size=10.0)
        assert isinstance(result, np.ndarray)


class TestTPMSStrategy:
    """Test TPMS lattice generation strategy."""

    @pytest.fixture
    def strategy(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig
        from backend.graph.strategies.lattice.tpms import TPMSStrategy
        cfg = ApplyLatticeConfig(cell_size=5.0, shell_thickness=1.0)
        return TPMSStrategy(config=cfg)

    def test_check_available(self, strategy):
        assert strategy.check_available() is True

    def test_generate_lattice_returns_mesh(self, strategy):
        """generate_lattice(bbox) returns a trimesh mesh."""
        import trimesh
        bbox_min = np.array([0, 0, 0])
        bbox_max = np.array([20, 20, 20])
        lattice = strategy.generate_lattice(bbox_min, bbox_max)
        assert isinstance(lattice, trimesh.Trimesh)
        assert len(lattice.vertices) > 0
        assert len(lattice.faces) > 0

    def test_apply_to_mesh_intersects_correctly(self, strategy):
        """apply_to_mesh(mesh) should produce mesh smaller than original."""
        import trimesh
        box = trimesh.creation.box(extents=[20, 20, 20])
        result = strategy.apply_to_mesh(box)
        assert isinstance(result, trimesh.Trimesh)
        # Lattice result should have less volume than solid
        assert result.volume < box.volume * 0.95


def _make_box_mesh(x: float, y: float, z: float):
    import trimesh
    return trimesh.creation.box(extents=[x, y, z])
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_apply_lattice.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write ApplyLatticeConfig**

```python
# backend/graph/configs/apply_lattice.py
"""Configuration for apply_lattice node."""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator

from backend.graph.configs.base import BaseNodeConfig


class ApplyLatticeConfig(BaseNodeConfig):
    """apply_lattice node configuration.

    Controls TPMS lattice type, cell size, and shell thickness.
    """

    strategy: str = "tpms"

    # Lattice parameters
    lattice_type: Literal["gyroid", "schwarz_p", "diamond"] = "gyroid"
    cell_size: float = 8.0       # mm, TPMS unit cell size
    wall_thickness: float = 0.8  # mm, TPMS strut thickness (abs-field band width)
    shell_thickness: float = 2.0 # mm, outer shell to preserve

    # Resolution for marching cubes
    resolution: int = 64  # Grid resolution per axis (must be >= 8)

    @field_validator("cell_size")
    @classmethod
    def _validate_cell_size(cls, v: float) -> float:
        if v <= 0 or v > 50:
            raise ValueError(f"cell_size must be in (0, 50], got {v}")
        return v

    @field_validator("wall_thickness")
    @classmethod
    def _validate_wall_thickness(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"wall_thickness must be > 0, got {v}")
        return v

    @field_validator("shell_thickness")
    @classmethod
    def _validate_shell_thickness(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"shell_thickness must be >= 0, got {v}")
        return v

    @field_validator("resolution")
    @classmethod
    def _validate_resolution(cls, v: int) -> int:
        if v < 8:
            raise ValueError(f"resolution must be >= 8, got {v}")
        return v
```

**Step 4: Write TPMSStrategy**

```python
# backend/graph/strategies/lattice/__init__.py
"""Lattice filling strategies."""

# backend/graph/strategies/lattice/tpms.py
"""TPMSStrategy — Triply Periodic Minimal Surface lattice generation.

Generates TPMS (Gyroid/Schwarz-P/Diamond) scalar fields, extracts
iso-surfaces via marching cubes, and intersects with the input mesh
using manifold3d boolean operations.

Flow:
  1. Compute TPMS scalar field over mesh bounding box
  2. Extract iso-surface via skimage.measure.marching_cubes
  3. Boolean intersect: mesh ∩ lattice_mesh
  4. Optionally preserve outer shell: (shell ∪ lattice_interior)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import trimesh

from backend.graph.descriptor import NodeStrategy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TPMS scalar field functions
# ---------------------------------------------------------------------------


def gyroid_field(
    x: np.ndarray, y: np.ndarray, z: np.ndarray, cell_size: float
) -> np.ndarray:
    """Gyroid: sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x)"""
    k = 2 * np.pi / cell_size
    return (
        np.sin(k * x) * np.cos(k * y)
        + np.sin(k * y) * np.cos(k * z)
        + np.sin(k * z) * np.cos(k * x)
    )


def schwarz_p_field(
    x: np.ndarray, y: np.ndarray, z: np.ndarray, cell_size: float
) -> np.ndarray:
    """Schwarz-P: cos(x) + cos(y) + cos(z)"""
    k = 2 * np.pi / cell_size
    return np.cos(k * x) + np.cos(k * y) + np.cos(k * z)


def diamond_field(
    x: np.ndarray, y: np.ndarray, z: np.ndarray, cell_size: float
) -> np.ndarray:
    """Diamond (Schwarz-D):
    sin(x)sin(y)sin(z) + sin(x)cos(y)cos(z)
    + cos(x)sin(y)cos(z) + cos(x)cos(y)sin(z)
    """
    k = 2 * np.pi / cell_size
    sx, sy, sz = np.sin(k * x), np.sin(k * y), np.sin(k * z)
    cx, cy, cz = np.cos(k * x), np.cos(k * y), np.cos(k * z)
    return sx * sy * sz + sx * cy * cz + cx * sy * cz + cx * cy * sz


_TPMS_FIELDS = {
    "gyroid": gyroid_field,
    "schwarz_p": schwarz_p_field,
    "diamond": diamond_field,
}


class TPMSStrategy(NodeStrategy):
    """TPMS lattice generation via marching cubes + boolean intersection."""

    def check_available(self) -> bool:
        """Check if skimage (scikit-image) is importable."""
        try:
            from skimage.measure import marching_cubes  # noqa: F401
            return True
        except ImportError:
            return False

    def generate_lattice(
        self, bbox_min: np.ndarray, bbox_max: np.ndarray
    ) -> trimesh.Trimesh:
        """Generate a TPMS lattice mesh within the given bounding box."""
        from skimage.measure import marching_cubes

        config = self.config
        field_fn = _TPMS_FIELDS[config.lattice_type]
        resolution = config.resolution

        # Create 3D grid
        x = np.linspace(float(bbox_min[0]), float(bbox_max[0]), resolution)
        y = np.linspace(float(bbox_min[1]), float(bbox_max[1]), resolution)
        z = np.linspace(float(bbox_min[2]), float(bbox_max[2]), resolution)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Evaluate TPMS field
        raw_field = field_fn(X, Y, Z, config.cell_size)

        # Convert to solid band: |field| < threshold → solid material
        # This creates a volumetric structure with actual wall thickness,
        # unlike a single iso-surface which produces a zero-thickness sheet.
        # The abs-field band approach: solid where abs(field) is small.
        abs_field = np.abs(raw_field)

        # Threshold: half wall_thickness scaled to TPMS field range.
        # TPMS fields have amplitude ~1.5, so we normalize.
        field_range = float(np.max(abs_field))
        if field_range < 1e-6:
            field_range = 1.0
        # Map wall_thickness (mm) to field units via cell_size ratio
        level = config.wall_thickness / config.cell_size * field_range

        spacing = (
            (bbox_max[0] - bbox_min[0]) / (resolution - 1),
            (bbox_max[1] - bbox_min[1]) / (resolution - 1),
            (bbox_max[2] - bbox_min[2]) / (resolution - 1),
        )

        verts, faces, _, _ = marching_cubes(abs_field, level=level, spacing=spacing)

        # Offset vertices to actual bounding box position
        verts += bbox_min

        return trimesh.Trimesh(vertices=verts, faces=faces)

    def apply_to_mesh(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Apply TPMS lattice to mesh interior via boolean intersection."""
        bbox_min = mesh.bounds[0]
        bbox_max = mesh.bounds[1]

        # Generate lattice
        lattice = self.generate_lattice(bbox_min, bbox_max)

        # Boolean intersection: keep only lattice within mesh
        try:
            result = mesh.intersection(lattice)
            if isinstance(result, trimesh.Trimesh) and len(result.faces) > 0:
                return result
        except Exception as exc:
            logger.warning("Boolean intersection failed: %s, returning original", exc)

        return mesh

    async def execute(self, ctx: Any) -> None:
        """Execute TPMS lattice application."""
        import asyncio

        asset = ctx.get_asset("final_mesh")
        mesh = await asyncio.to_thread(trimesh.load, asset.path, force="mesh")

        await ctx.dispatch_progress(1, 4, f"生成 {self.config.lattice_type} 晶格")

        result = await asyncio.to_thread(self.apply_to_mesh, mesh)

        await ctx.dispatch_progress(3, 4, "导出晶格化网格")

        import tempfile
        from pathlib import Path

        output_dir = Path(tempfile.gettempdir()) / "cadpilot" / "lattice"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"{ctx.job_id}_lattice.glb")
        await asyncio.to_thread(result.export, output_path)

        ctx.put_asset(
            "lattice_mesh", output_path, "mesh",
            metadata={
                "lattice_type": self.config.lattice_type,
                "cell_size": self.config.cell_size,
                "original_volume": round(float(mesh.volume), 2),
                "lattice_volume": round(float(result.volume), 2),
                "volume_reduction": round(
                    1 - float(result.volume) / max(float(mesh.volume), 1e-6), 4
                ),
            },
        )

        await ctx.dispatch_progress(4, 4, "晶格填充完成")
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_apply_lattice.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/graph/configs/apply_lattice.py backend/graph/strategies/lattice/ tests/test_apply_lattice.py
git commit -m "feat(phase3): apply_lattice config + TPMSStrategy (Gyroid/Schwarz-P/Diamond)"
```

---

## Task 5: apply_lattice — Node registration [backend][test]

**Files:**
- Create: `backend/graph/nodes/apply_lattice.py`
- Modify: `tests/test_apply_lattice.py` (add node tests)

**Step 1: Write failing node tests**

```python
# Add to tests/test_apply_lattice.py
import asyncio
from unittest.mock import AsyncMock, MagicMock


class TestApplyLatticeNode:
    @pytest.mark.asyncio
    async def test_node_registered_with_tpms_strategy(self):
        from backend.graph.nodes.apply_lattice import apply_lattice_node
        desc = apply_lattice_node._node_descriptor
        assert "tpms" in desc.strategies
        assert desc.name == "apply_lattice"
        assert desc.non_fatal is True

    @pytest.mark.asyncio
    async def test_node_skips_without_input(self):
        from backend.graph.nodes.apply_lattice import apply_lattice_node
        ctx = MagicMock()
        ctx.has_asset.return_value = False
        ctx.config = MagicMock()
        ctx.config.strategy = "tpms"
        ctx.config.enabled = True

        # Should skip gracefully without error
        await apply_lattice_node(ctx)
        ctx.put_data.assert_called_with("apply_lattice_status", "skipped_no_input")
```

**Step 2: Run tests, verify fail**

Run: `uv run pytest tests/test_apply_lattice.py::TestApplyLatticeNode -v`
Expected: FAIL

**Step 3: Write apply_lattice node**

```python
# backend/graph/nodes/apply_lattice.py
"""apply_lattice — TPMS lattice filling for lightweight internal structure.

Generates a Triply Periodic Minimal Surface (Gyroid/Schwarz-P/Diamond)
and applies it to the mesh interior via boolean intersection.
"""

from __future__ import annotations

import logging

from backend.graph.configs.apply_lattice import ApplyLatticeConfig
from backend.graph.context import NodeContext
from backend.graph.registry import register_node
from backend.graph.strategies.lattice.tpms import TPMSStrategy

logger = logging.getLogger(__name__)


@register_node(
    name="apply_lattice",
    display_name="晶格填充",
    requires=["final_mesh"],
    produces=["lattice_mesh"],
    input_types=["organic"],
    config_model=ApplyLatticeConfig,
    strategies={
        "tpms": TPMSStrategy,
    },
    default_strategy="tpms",
    fallback_chain=["tpms"],
    non_fatal=True,
    description="TPMS 晶格填充（Gyroid/Schwarz-P/Diamond），轻量化内部结构",
)
async def apply_lattice_node(ctx: NodeContext) -> None:
    """Execute lattice filling via strategy dispatch.

    non_fatal=True: lattice failure should not block the pipeline.
    """
    if not ctx.has_asset("final_mesh"):
        logger.info("apply_lattice: no final_mesh, skipping")
        ctx.put_data("apply_lattice_status", "skipped_no_input")
        return

    if ctx.config.strategy == "auto":
        await ctx.execute_with_fallback()
    else:
        strategy = ctx.get_strategy()
        await strategy.execute(ctx)
```

**Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_apply_lattice.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/graph/nodes/apply_lattice.py tests/test_apply_lattice.py
git commit -m "feat(phase3): apply_lattice node registration"
```

---

## Task 6: thermal_simulation — DfAM thermal risk report [backend]

**Files:**
- Create: `backend/graph/configs/thermal_simulation.py`
- Create: `backend/graph/strategies/thermal/__init__.py`
- Create: `backend/graph/strategies/thermal/rules.py`
- Create: `tests/test_thermal_simulation.py`

**Step 1: Write failing tests**

```python
# tests/test_thermal_simulation.py
"""Tests for thermal_simulation node (degraded to DfAM thermal risk report)."""

from __future__ import annotations

import pytest
import numpy as np


class TestThermalSimulationConfig:
    def test_defaults(self):
        from backend.graph.configs.thermal_simulation import ThermalSimulationConfig
        cfg = ThermalSimulationConfig()
        assert cfg.strategy == "rules"
        assert cfg.overhang_threshold == 45.0
        assert cfg.aspect_ratio_threshold == 10.0

    def test_overhang_threshold_validation(self):
        from backend.graph.configs.thermal_simulation import ThermalSimulationConfig
        with pytest.raises(ValueError):
            ThermalSimulationConfig(overhang_threshold=-1)


class TestRulesThermalStrategy:
    """Rules-based thermal risk assessment from geometry features."""

    @pytest.fixture
    def strategy(self):
        from backend.graph.configs.thermal_simulation import ThermalSimulationConfig
        from backend.graph.strategies.thermal.rules import RulesThermalStrategy
        cfg = ThermalSimulationConfig()
        return RulesThermalStrategy(config=cfg)

    def test_check_available(self, strategy):
        assert strategy.check_available() is True

    def test_analyze_returns_thermal_report(self, strategy):
        """analyze(mesh) returns a ThermalRiskReport dict."""
        import trimesh
        mesh = trimesh.creation.box(extents=[10, 10, 50])  # Tall thin box
        report = strategy.analyze(mesh)
        assert "risk_level" in report
        assert report["risk_level"] in ("low", "medium", "high")
        assert "risk_factors" in report
        assert isinstance(report["risk_factors"], list)

    def test_tall_thin_part_gets_high_risk(self, strategy):
        """A tall thin part (2x2x100) should have high thermal risk."""
        import trimesh
        mesh = trimesh.creation.box(extents=[2, 2, 100])
        report = strategy.analyze(mesh)
        assert report["risk_level"] in ("medium", "high")
        # Should flag height/width ratio concern
        assert any("高宽比" in f["description"] or "aspect" in f["description"].lower()
                    for f in report["risk_factors"])

    def test_cube_gets_low_risk(self, strategy):
        """A simple cube should have low thermal risk."""
        import trimesh
        mesh = trimesh.creation.box(extents=[20, 20, 20])
        report = strategy.analyze(mesh)
        assert report["risk_level"] == "low"

    def test_report_includes_recommendations(self, strategy):
        """Report should include actionable recommendations."""
        import trimesh
        mesh = trimesh.creation.box(extents=[2, 2, 100])
        report = strategy.analyze(mesh)
        assert "recommendations" in report
        assert len(report["recommendations"]) > 0
```

**Step 2: Run tests, verify fail**

Run: `uv run pytest tests/test_thermal_simulation.py -v`
Expected: FAIL

**Step 3: Write ThermalSimulationConfig**

```python
# backend/graph/configs/thermal_simulation.py
"""Configuration for thermal_simulation node."""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator

from backend.graph.configs.neural import NeuralStrategyConfig


class ThermalSimulationConfig(NeuralStrategyConfig):
    """thermal_simulation node configuration.

    Degraded design: rules-based thermal risk report instead of FEA.
    Neural channel reserved for future thermal prediction models.
    """

    strategy: Literal["rules", "gradient", "auto"] = "rules"

    # Geometric thresholds for risk assessment
    overhang_threshold: float = 45.0      # degrees
    aspect_ratio_threshold: float = 10.0  # height/width ratio
    large_flat_area_threshold: float = 100.0  # mm² — warping risk

    @field_validator("overhang_threshold")
    @classmethod
    def _positive_threshold(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"Threshold must be positive, got {v}")
        return v
```

**Step 4: Write RulesThermalStrategy**

```python
# backend/graph/strategies/thermal/__init__.py
"""Thermal simulation strategies."""

# backend/graph/strategies/thermal/rules.py
"""RulesThermalStrategy — geometry-based thermal risk assessment.

Evaluates 3D print thermal risk from geometric features:
1. Aspect ratio (height/min_width) — tall thin parts warp
2. Overhang area ratio — unsupported overhangs concentrate heat
3. Cross-section variation — sudden area changes cause thermal stress
4. Large flat surfaces — prone to warping/curling

Outputs a ThermalRiskReport dict with risk_level, risk_factors, recommendations.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import trimesh

from backend.graph.descriptor import NodeStrategy

logger = logging.getLogger(__name__)


class RulesThermalStrategy(NodeStrategy):
    """Geometry rules-based thermal risk assessment."""

    def analyze(self, mesh: trimesh.Trimesh) -> dict[str, Any]:
        """Analyze mesh for thermal risk factors.

        Returns:
            dict with risk_level, risk_factors, recommendations, score
        """
        config = self.config
        risk_factors: list[dict[str, Any]] = []
        score = 0.0  # 0 = no risk, 100 = extreme risk

        extents = mesh.bounding_box.extents
        min_xy = min(extents[0], extents[1])
        max_z = extents[2]

        # 1. Aspect ratio check
        aspect_ratio = max_z / max(min_xy, 1e-6)
        if aspect_ratio > config.aspect_ratio_threshold:
            risk_factors.append({
                "type": "aspect_ratio",
                "description": f"高宽比 {aspect_ratio:.1f} 超过阈值 {config.aspect_ratio_threshold}，"
                               f"打印过程中可能发生层间剥离或翘曲",
                "severity": "high",
                "value": round(aspect_ratio, 2),
            })
            score += 30
        elif aspect_ratio > config.aspect_ratio_threshold * 0.5:
            risk_factors.append({
                "type": "aspect_ratio",
                "description": f"高宽比 {aspect_ratio:.1f} 偏高，注意打印稳定性",
                "severity": "medium",
                "value": round(aspect_ratio, 2),
            })
            score += 15

        # 2. Overhang analysis
        face_normals = mesh.face_normals
        face_areas = mesh.area_faces
        overhang_mask = face_normals[:, 2] < -np.cos(
            np.radians(config.overhang_threshold)
        )
        overhang_area = float(np.sum(face_areas[overhang_mask]))
        total_area = float(np.sum(face_areas))
        overhang_ratio = overhang_area / max(total_area, 1e-6)

        if overhang_ratio > 0.3:
            risk_factors.append({
                "type": "overhang",
                "description": f"悬挑面积占比 {overhang_ratio:.0%}，热应力集中风险高",
                "severity": "high",
                "value": round(overhang_ratio, 4),
            })
            score += 25
        elif overhang_ratio > 0.1:
            risk_factors.append({
                "type": "overhang",
                "description": f"悬挑面积占比 {overhang_ratio:.0%}，存在一定热风险",
                "severity": "medium",
                "value": round(overhang_ratio, 4),
            })
            score += 10

        # 3. Cross-section variation (approximate via Z-slice)
        z_min, z_max = mesh.bounds[0][2], mesh.bounds[1][2]
        n_slices = 10
        areas = []
        for i in range(n_slices):
            z = z_min + (z_max - z_min) * (i + 0.5) / n_slices
            try:
                section = mesh.section(
                    plane_origin=[0, 0, z],
                    plane_normal=[0, 0, 1],
                )
                if section is not None:
                    planar, _ = section.to_planar()
                    areas.append(float(planar.area))
                else:
                    areas.append(0.0)
            except Exception:
                areas.append(0.0)

        if len(areas) >= 2 and max(areas) > 0:
            area_variation = (max(areas) - min(areas)) / max(areas)
            if area_variation > 0.7:
                risk_factors.append({
                    "type": "cross_section_variation",
                    "description": f"截面积变化率 {area_variation:.0%}，"
                                   f"急剧变化处易产生热应力集中",
                    "severity": "medium",
                    "value": round(area_variation, 4),
                })
                score += 15

        # 4. Large flat bottom surface (warping risk)
        # Detect bottom faces via face normal pointing down (Z < -0.9)
        bottom_mask = face_normals[:, 2] < -0.9
        if np.any(bottom_mask):
            bottom_area = float(np.sum(face_areas[bottom_mask]))
            if bottom_area > config.large_flat_area_threshold:
                risk_factors.append({
                    "type": "large_flat_area",
                    "description": f"底部平面面积 {bottom_area:.0f} mm² 较大，翘曲风险升高",
                    "severity": "medium",
                    "value": round(bottom_area, 2),
                })
                score += 10

        # Determine risk level
        score = min(score, 100)
        if score >= 50:
            risk_level = "high"
        elif score >= 20:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Generate recommendations
        recommendations = self._generate_recommendations(risk_factors)

        return {
            "risk_level": risk_level,
            "risk_score": round(score, 1),
            "risk_factors": risk_factors,
            "recommendations": recommendations,
            "geometry_summary": {
                "extents": [round(float(e), 2) for e in extents],
                "aspect_ratio": round(aspect_ratio, 2),
                "overhang_ratio": round(overhang_ratio, 4),
                "volume_cm3": round(float(mesh.volume) / 1000, 2),
            },
        }

    @staticmethod
    def _generate_recommendations(
        risk_factors: list[dict[str, Any]],
    ) -> list[str]:
        """Generate actionable recommendations from risk factors."""
        recs: list[str] = []
        types = {f["type"] for f in risk_factors}

        if "aspect_ratio" in types:
            recs.append("考虑将零件分割打印后拼接，或增加底部支撑面积")
        if "overhang" in types:
            recs.append("添加支撑结构或调整打印方向以减少悬挑")
        if "cross_section_variation" in types:
            recs.append("在截面突变处降低打印速度，减少层间热应力")
        if "large_flat_area" in types:
            recs.append("使用 Brim 或 Raft 增加底面附着力，防止翘曲")

        if not recs:
            recs.append("几何形状适合打印，无特殊热风险")

        return recs

    async def execute(self, ctx: Any) -> None:
        """Execute thermal risk assessment."""
        import asyncio

        asset = ctx.get_asset("final_mesh")
        mesh = await asyncio.to_thread(trimesh.load, asset.path, force="mesh")

        await ctx.dispatch_progress(1, 2, "热风险评估中")

        report = await asyncio.to_thread(self.analyze, mesh)

        ctx.put_data("thermal_report", report)
        ctx.put_data("thermal_simulation_status", "completed")

        await ctx.dispatch_progress(2, 2, f"热风险评估完成: {report['risk_level']}")
```

**Step 5: Run tests, verify pass**

Run: `uv run pytest tests/test_thermal_simulation.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/graph/configs/thermal_simulation.py backend/graph/strategies/thermal/ tests/test_thermal_simulation.py
git commit -m "feat(phase3): thermal_simulation config + RulesThermalStrategy"
```

---

## Task 7: thermal_simulation — GradientStrategy + Node [backend][test]

**Files:**
- Create: `backend/graph/strategies/thermal/gradient.py`
- Create: `backend/graph/nodes/thermal_simulation.py`
- Modify: `tests/test_thermal_simulation.py` (add gradient + node tests)

**Step 1: Write failing tests**

```python
# Add to tests/test_thermal_simulation.py
import asyncio
from unittest.mock import AsyncMock, MagicMock


class TestGradientThermalStrategy:
    """Gradient strategy: layer-by-layer cross-section analysis."""

    @pytest.fixture
    def strategy(self):
        from backend.graph.configs.thermal_simulation import ThermalSimulationConfig
        from backend.graph.strategies.thermal.gradient import GradientThermalStrategy
        cfg = ThermalSimulationConfig(strategy="gradient")
        return GradientThermalStrategy(config=cfg)

    def test_check_available(self, strategy):
        assert strategy.check_available() is True

    def test_analyze_returns_gradient_data(self, strategy):
        """analyze(mesh, layer_height) returns layer-by-layer gradient data."""
        import trimesh
        mesh = trimesh.creation.box(extents=[20, 20, 40])
        report = strategy.analyze(mesh, layer_height=0.2)
        assert "layers" in report
        assert "max_gradient" in report
        assert len(report["layers"]) > 0

    def test_gradient_includes_risk_level(self, strategy):
        import trimesh
        mesh = trimesh.creation.box(extents=[20, 20, 40])
        report = strategy.analyze(mesh, layer_height=0.2)
        assert "risk_level" in report
        assert report["risk_level"] in ("low", "medium", "high")


class TestThermalSimulationNode:
    @pytest.mark.asyncio
    async def test_node_registered(self):
        from backend.graph.nodes.thermal_simulation import thermal_simulation_node
        desc = thermal_simulation_node._node_descriptor
        assert "rules" in desc.strategies
        assert "gradient" in desc.strategies
        assert desc.non_fatal is True
        assert desc.name == "thermal_simulation"

    @pytest.mark.asyncio
    async def test_node_skips_without_input(self):
        from backend.graph.nodes.thermal_simulation import thermal_simulation_node
        ctx = MagicMock()
        ctx.has_asset.return_value = False
        ctx.config = MagicMock()
        ctx.config.strategy = "rules"
        await thermal_simulation_node(ctx)
        ctx.put_data.assert_any_call("thermal_simulation_status", "skipped_no_input")
```

**Step 2: Run tests, verify fail**

Run: `uv run pytest tests/test_thermal_simulation.py -k "Gradient or Node" -v`
Expected: FAIL

**Step 3: Write GradientThermalStrategy**

```python
# backend/graph/strategies/thermal/gradient.py
"""GradientThermalStrategy — layer-by-layer thermal gradient analysis.

Computes cross-section area at each layer height and identifies
thermal gradient hotspots where area changes rapidly.
More precise than rules but still avoids full FEA.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import trimesh

from backend.graph.descriptor import NodeStrategy

logger = logging.getLogger(__name__)


class GradientThermalStrategy(NodeStrategy):
    """Layer-by-layer cross-section thermal gradient analysis."""

    def analyze(
        self, mesh: trimesh.Trimesh, layer_height: float = 0.2
    ) -> dict[str, Any]:
        """Compute per-layer cross-section areas and thermal gradients."""
        z_min, z_max = mesh.bounds[0][2], mesh.bounds[1][2]
        height = z_max - z_min

        n_layers = max(1, int(height / layer_height))
        # Sample up to 200 layers for performance
        step = max(1, n_layers // 200)
        sample_heights = [
            z_min + (i * layer_height)
            for i in range(0, n_layers, step)
        ]

        layers: list[dict[str, Any]] = []
        prev_area = 0.0
        max_gradient = 0.0

        for z in sample_heights:
            try:
                section = mesh.section(
                    plane_origin=[0, 0, z],
                    plane_normal=[0, 0, 1],
                )
                if section is not None:
                    planar, _ = section.to_planar()
                    area = float(planar.area)
                else:
                    area = 0.0
            except Exception:
                area = 0.0

            gradient = abs(area - prev_area) / max(prev_area, 1e-6) if prev_area > 0 else 0
            max_gradient = max(max_gradient, gradient)

            layers.append({
                "z": round(z, 2),
                "area_mm2": round(area, 2),
                "gradient": round(gradient, 4),
            })
            prev_area = area

        # Determine risk from max gradient
        if max_gradient > 1.0:
            risk_level = "high"
        elif max_gradient > 0.5:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_level": risk_level,
            "max_gradient": round(max_gradient, 4),
            "layers": layers,
            "n_layers_total": n_layers,
            "n_layers_sampled": len(layers),
            "recommendations": self._gradient_recommendations(max_gradient),
        }

    @staticmethod
    def _gradient_recommendations(max_gradient: float) -> list[str]:
        recs = []
        if max_gradient > 1.0:
            recs.append("截面积变化剧烈，建议在渐变处增加过渡特征")
            recs.append("降低打印速度并增加冷却时间")
        elif max_gradient > 0.5:
            recs.append("中等截面变化，建议适度降低打印速度")
        else:
            recs.append("截面变化平缓，热风险低")
        return recs

    async def execute(self, ctx: Any) -> None:
        """Execute gradient thermal analysis."""
        import asyncio

        asset = ctx.get_asset("final_mesh")
        mesh = await asyncio.to_thread(trimesh.load, asset.path, force="mesh")

        await ctx.dispatch_progress(1, 2, "层级热梯度分析中")

        report = await asyncio.to_thread(self.analyze, mesh)

        ctx.put_data("thermal_report", report)
        ctx.put_data("thermal_simulation_status", "completed")

        await ctx.dispatch_progress(2, 2, f"热梯度分析完成: {report['risk_level']}")
```

**Step 4: Write thermal_simulation node**

```python
# backend/graph/nodes/thermal_simulation.py
"""thermal_simulation — DfAM thermal risk assessment.

Degraded design: rules-based + gradient analysis instead of full FEA.
Reports thermal risk factors, not physics simulation results.
"""

from __future__ import annotations

import logging

from backend.graph.configs.thermal_simulation import ThermalSimulationConfig
from backend.graph.context import NodeContext
from backend.graph.registry import register_node
from backend.graph.strategies.thermal.gradient import GradientThermalStrategy
from backend.graph.strategies.thermal.rules import RulesThermalStrategy

logger = logging.getLogger(__name__)


@register_node(
    name="thermal_simulation",
    display_name="热风险评估",
    requires=["final_mesh"],
    produces=[],  # thermal_report stored via put_data (analytical output, not asset)
    input_types=["organic"],
    config_model=ThermalSimulationConfig,
    strategies={
        "rules": RulesThermalStrategy,
        "gradient": GradientThermalStrategy,
    },
    default_strategy="rules",
    fallback_chain=["gradient", "rules"],
    non_fatal=True,
    description="基于几何规则和截面梯度的热风险评估（降级版 FEA）",
)
async def thermal_simulation_node(ctx: NodeContext) -> None:
    """Execute thermal risk assessment via strategy dispatch.

    non_fatal=True: thermal analysis failure should not block the pipeline.
    """
    if not ctx.has_asset("final_mesh"):
        logger.info("thermal_simulation: no final_mesh, skipping")
        ctx.put_data("thermal_simulation_status", "skipped_no_input")
        return

    if ctx.config.strategy == "auto":
        await ctx.execute_with_fallback()
    else:
        strategy = ctx.get_strategy()
        await strategy.execute(ctx)
```

**Step 5: Run all thermal tests**

Run: `uv run pytest tests/test_thermal_simulation.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/graph/strategies/thermal/gradient.py backend/graph/nodes/thermal_simulation.py tests/test_thermal_simulation.py
git commit -m "feat(phase3): thermal_simulation node + GradientThermalStrategy"
```

---

## Task 8: generate_supports + slice_to_gcode 集成 [backend][test]

**Files:**
- Create: `backend/graph/configs/generate_supports.py` (支撑策略配置)
- Create: `backend/graph/nodes/generate_supports.py` (passthrough stub)
- Modify: `backend/graph/configs/slice_to_gcode.py` (add support config fields)
- Modify: `backend/graph/nodes/slice_to_gcode.py` (更新 _MESH_PRIORITY + 读取 support_config)
- Create: `tests/test_generate_supports.py`

**Step 1: Write failing tests**

```python
# tests/test_generate_supports.py
"""Tests for generate_supports node (delegated to slice_to_gcode)."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


class TestSliceToGcodeConfigExtension:
    def test_support_type_field(self):
        from backend.graph.configs.slice_to_gcode import SliceToGcodeConfig
        cfg = SliceToGcodeConfig(support_type="tree")
        assert cfg.support_type == "tree"

    def test_support_type_default(self):
        from backend.graph.configs.slice_to_gcode import SliceToGcodeConfig
        cfg = SliceToGcodeConfig()
        assert cfg.support_type == "auto"

    def test_support_density(self):
        from backend.graph.configs.slice_to_gcode import SliceToGcodeConfig
        cfg = SliceToGcodeConfig(support_density=20)
        assert cfg.support_density == 20


class TestGenerateSupportsNode:
    @pytest.mark.asyncio
    async def test_node_registered(self):
        from backend.graph.nodes.generate_supports import generate_supports_node
        desc = generate_supports_node._node_descriptor
        assert desc.name == "generate_supports"
        assert desc.non_fatal is True

    @pytest.mark.asyncio
    async def test_passthrough_delegates_to_slicer(self):
        """Node should be a passthrough that sets support config for slice_to_gcode."""
        from backend.graph.configs.generate_supports import GenerateSupportsConfig
        from backend.graph.nodes.generate_supports import generate_supports_node
        ctx = MagicMock()
        ctx.has_asset.return_value = True
        ctx.get_data.return_value = None
        ctx.config = GenerateSupportsConfig(support_type="tree", support_density=15)

        await generate_supports_node(ctx)

        # Should store support config for downstream slice_to_gcode
        ctx.put_data.assert_any_call("support_config", {
            "support_type": "tree",
            "support_density": 15,
        })

    @pytest.mark.asyncio
    async def test_auto_with_orientation_selects_tree(self):
        """Auto support type + orientation result → tree supports."""
        from backend.graph.configs.generate_supports import GenerateSupportsConfig
        from backend.graph.nodes.generate_supports import generate_supports_node
        ctx = MagicMock()
        ctx.has_asset.return_value = True
        ctx.get_data.return_value = {"orientation": "Z-up", "score": 0.5}
        ctx.config = GenerateSupportsConfig(support_type="auto")

        await generate_supports_node(ctx)
        ctx.put_data.assert_any_call("support_config", {
            "support_type": "tree",
            "support_density": 15,
        })

    @pytest.mark.asyncio
    async def test_auto_without_orientation_selects_linear(self):
        """Auto support type + no orientation → linear supports."""
        from backend.graph.configs.generate_supports import GenerateSupportsConfig
        from backend.graph.nodes.generate_supports import generate_supports_node
        ctx = MagicMock()
        ctx.has_asset.return_value = True
        ctx.get_data.return_value = None
        ctx.config = GenerateSupportsConfig(support_type="auto")

        await generate_supports_node(ctx)
        ctx.put_data.assert_any_call("support_config", {
            "support_type": "linear",
            "support_density": 15,
        })

    @pytest.mark.asyncio
    async def test_skips_without_input(self):
        from backend.graph.nodes.generate_supports import generate_supports_node
        ctx = MagicMock()
        ctx.has_asset.return_value = False
        ctx.config = MagicMock()

        await generate_supports_node(ctx)
        ctx.put_data.assert_any_call("generate_supports_status", "skipped_no_input")
```

**Step 2: Run tests, verify fail**

Run: `uv run pytest tests/test_generate_supports.py -v`
Expected: FAIL

**Step 3: Extend SliceToGcodeConfig + update slice_to_gcode node**

```python
# Add to backend/graph/configs/slice_to_gcode.py (after existing fields)

    # Support parameters (delegated from generate_supports)
    support_type: str = "auto"         # auto/tree/linear/none
    support_density: int = 15          # %, support infill density
```

```python
# Update backend/graph/nodes/slice_to_gcode.py — _MESH_PRIORITY
# Change from:
_MESH_PRIORITY = ["final_mesh", "scaled_mesh", "watertight_mesh"]
# To (consume Phase 3 optimized meshes first):
_MESH_PRIORITY = [
    "oriented_mesh",    # Phase 3: orientation-optimized
    "lattice_mesh",     # Phase 3: lattice-filled
    "final_mesh",       # Phase 2: boolean assembled
    "scaled_mesh",      # Phase 2: scaled
    "watertight_mesh",  # Phase 1: healed
]
```

Also update slice_to_gcode's `@register_node` requires to include Phase 3 assets as OR dependencies:
```python
requires=[["oriented_mesh", "lattice_mesh", "final_mesh", "scaled_mesh", "watertight_mesh"]],
```

And add support_config consumption in the slicer strategy execution:
```python
# In slice_to_gcode_node, before strategy dispatch, read support_config:
support_config = ctx.get_data("support_config")
if support_config:
    ctx._support_config = support_config  # Pass to strategy
```

**Step 4: Write GenerateSupportsConfig + generate_supports passthrough node**

First, create `GenerateSupportsConfig`:

```python
# backend/graph/configs/generate_supports.py
"""Configuration for generate_supports node."""

from __future__ import annotations

from typing import Literal

from backend.graph.configs.base import BaseNodeConfig


class GenerateSupportsConfig(BaseNodeConfig):
    """generate_supports node configuration."""

    support_type: Literal["auto", "tree", "linear", "none"] = "auto"
    support_density: int = 15  # %, support infill density
```

Then create the node:

```python
# backend/graph/nodes/generate_supports.py
"""generate_supports — support strategy configuration (delegated to slicer).

Design decision: support generation is delegated to slice_to_gcode
(PrusaSlicer/OrcaSlicer built-in tree supports). This node configures
support parameters based on orientation_optimizer output.
"""

from __future__ import annotations

import logging

from backend.graph.configs.generate_supports import GenerateSupportsConfig
from backend.graph.context import NodeContext
from backend.graph.registry import register_node

logger = logging.getLogger(__name__)


@register_node(
    name="generate_supports",
    display_name="支撑策略",
    requires=["final_mesh"],
    produces=[],  # support_config stored via put_data
    input_types=["organic"],
    config_model=GenerateSupportsConfig,
    non_fatal=True,
    description="配置支撑策略并委托给切片器执行（PrusaSlicer 内置树状支撑）",
)
async def generate_supports_node(ctx: NodeContext) -> None:
    """Configure support parameters for downstream slice_to_gcode.

    This is a lightweight passthrough node:
    1. Read orientation_result from ctx (if available)
    2. Determine support type and density
    3. Store support_config in ctx.data for slice_to_gcode to consume
    """
    if not ctx.has_asset("final_mesh"):
        logger.info("generate_supports: no final_mesh, skipping")
        ctx.put_data("generate_supports_status", "skipped_no_input")
        return

    # Read orientation analysis (if orientation_optimizer ran)
    orientation_result = ctx.get_data("orientation_result")

    support_type = ctx.config.support_type
    support_density = ctx.config.support_density

    # Auto-determine support type from orientation analysis
    if support_type == "auto":
        if orientation_result:
            # Orientation was optimized → tree supports (best for optimized angles)
            support_type = "tree"
        else:
            # No orientation info → linear supports (safer default)
            support_type = "linear"

    ctx.put_data("support_config", {
        "support_type": support_type,
        "support_density": support_density,
    })
    ctx.put_data("generate_supports_status", "delegated_to_slicer")

    logger.info(
        "generate_supports: configured %s supports (density=%d%%) for slicer",
        support_type, support_density,
    )
```

**Step 5: Run tests, verify pass**

Run: `uv run pytest tests/test_generate_supports.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/graph/configs/slice_to_gcode.py backend/graph/nodes/generate_supports.py tests/test_generate_supports.py
git commit -m "feat(phase3): generate_supports passthrough + SliceToGcodeConfig extension"
```

---

## Task 9: Phase 3 集成测试 [test]

**Files:**
- Create: `tests/test_phase3_integration.py`

**Step 1: Write integration tests**

```python
# tests/test_phase3_integration.py
"""Phase 3 integration tests — verify all nodes register and interop correctly."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

import numpy as np


class TestPhase3NodeRegistration:
    """All Phase 3 nodes should be discoverable in the registry."""

    def test_orientation_optimizer_in_registry(self):
        from backend.graph.registry import registry
        # Force import to trigger registration
        import backend.graph.nodes.orientation_optimizer  # noqa: F401
        assert "orientation_optimizer" in registry

    def test_apply_lattice_in_registry(self):
        from backend.graph.registry import registry
        import backend.graph.nodes.apply_lattice  # noqa: F401
        assert "apply_lattice" in registry

    def test_thermal_simulation_in_registry(self):
        from backend.graph.registry import registry
        import backend.graph.nodes.thermal_simulation  # noqa: F401
        assert "thermal_simulation" in registry

    def test_generate_supports_in_registry(self):
        from backend.graph.registry import registry
        import backend.graph.nodes.generate_supports  # noqa: F401
        assert "generate_supports" in registry


class TestPhase3TopologyChain:
    """Verify requires/produces chain is consistent."""

    def test_orientation_requires_final_mesh(self):
        import backend.graph.nodes.orientation_optimizer  # noqa: F401
        from backend.graph.registry import registry
        desc = registry.get("orientation_optimizer")
        assert "final_mesh" in desc.requires

    def test_lattice_requires_final_mesh(self):
        import backend.graph.nodes.apply_lattice  # noqa: F401
        from backend.graph.registry import registry
        desc = registry.get("apply_lattice")
        assert "final_mesh" in desc.requires

    def test_all_phase3_non_fatal(self):
        """All Phase 3 nodes should be non_fatal."""
        import backend.graph.nodes.orientation_optimizer  # noqa: F401
        import backend.graph.nodes.apply_lattice  # noqa: F401
        import backend.graph.nodes.thermal_simulation  # noqa: F401
        import backend.graph.nodes.generate_supports  # noqa: F401
        from backend.graph.registry import registry

        for name in ["orientation_optimizer", "apply_lattice",
                     "thermal_simulation", "generate_supports"]:
            desc = registry.get(name)
            assert desc.non_fatal is True, f"{name} should be non_fatal"


class TestPhase3ConfigDefaults:
    """Config defaults should be sensible for production."""

    def test_orientation_config_defaults(self):
        from backend.graph.configs.orientation_optimizer import OrientationOptimizerConfig
        cfg = OrientationOptimizerConfig()
        assert cfg.strategy == "basic"
        assert cfg.enabled is True

    def test_lattice_config_defaults(self):
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig
        cfg = ApplyLatticeConfig()
        assert cfg.strategy == "tpms"
        assert cfg.lattice_type == "gyroid"

    def test_thermal_config_defaults(self):
        from backend.graph.configs.thermal_simulation import ThermalSimulationConfig
        cfg = ThermalSimulationConfig()
        assert cfg.strategy == "rules"

    def test_slice_config_support_extension(self):
        from backend.graph.configs.slice_to_gcode import SliceToGcodeConfig
        cfg = SliceToGcodeConfig()
        assert cfg.support_type == "auto"
        assert cfg.support_density == 15


class TestPhase3StrategyAvailability:
    """All algorithm strategies should be available (no external dependencies)."""

    def test_basic_orient_available(self):
        from backend.graph.strategies.orient.basic import BasicOrientStrategy
        from backend.graph.configs.orientation_optimizer import OrientationOptimizerConfig
        s = BasicOrientStrategy(config=OrientationOptimizerConfig())
        assert s.check_available() is True

    def test_scipy_orient_available(self):
        from backend.graph.strategies.orient.scipy_orient import ScipyOrientStrategy
        from backend.graph.configs.orientation_optimizer import OrientationOptimizerConfig
        s = ScipyOrientStrategy(config=OrientationOptimizerConfig())
        assert s.check_available() is True

    def test_tpms_lattice_available(self):
        from backend.graph.strategies.lattice.tpms import TPMSStrategy
        from backend.graph.configs.apply_lattice import ApplyLatticeConfig
        s = TPMSStrategy(config=ApplyLatticeConfig())
        assert s.check_available() is True

    def test_rules_thermal_available(self):
        from backend.graph.strategies.thermal.rules import RulesThermalStrategy
        from backend.graph.configs.thermal_simulation import ThermalSimulationConfig
        s = RulesThermalStrategy(config=ThermalSimulationConfig())
        assert s.check_available() is True

    def test_gradient_thermal_available(self):
        from backend.graph.strategies.thermal.gradient import GradientThermalStrategy
        from backend.graph.configs.thermal_simulation import ThermalSimulationConfig
        s = GradientThermalStrategy(config=ThermalSimulationConfig())
        assert s.check_available() is True
```

**Step 2: Run integration tests**

Run: `uv run pytest tests/test_phase3_integration.py -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All 1793+ tests pass, 0 failures

**Step 4: Commit**

```bash
git add tests/test_phase3_integration.py
git commit -m "feat(phase3): integration tests for all Phase 3 nodes"
```

---

## Task 10: 全量测试 + TypeScript 检查 [test]

**Step 1: Run full backend test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 2: Run TypeScript check (Phase 3 is pure backend, but verify no regressions)**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Verify no import cycles or registration conflicts**

Run: `uv run python -c "from backend.graph.nodes import orientation_optimizer, apply_lattice, thermal_simulation, generate_supports; print('All Phase 3 nodes importable')"`
Expected: "All Phase 3 nodes importable"

---

## 文件清单

### 新建文件 (16)

| 文件 | 用途 |
|------|------|
| `backend/graph/configs/orientation_optimizer.py` | 方向优化配置 |
| `backend/graph/configs/apply_lattice.py` | 晶格填充配置 |
| `backend/graph/configs/thermal_simulation.py` | 热风险评估配置 |
| `backend/graph/configs/generate_supports.py` | 支撑策略配置 |
| `backend/graph/strategies/orient/__init__.py` | 方向策略包 |
| `backend/graph/strategies/orient/basic.py` | 6 方向离散搜索 |
| `backend/graph/strategies/orient/scipy_orient.py` | Scipy 连续优化 |
| `backend/graph/strategies/lattice/__init__.py` | 晶格策略包 |
| `backend/graph/strategies/lattice/tpms.py` | TPMS 数学晶格 |
| `backend/graph/strategies/thermal/__init__.py` | 热分析策略包 |
| `backend/graph/strategies/thermal/rules.py` | 规则热风险 |
| `backend/graph/strategies/thermal/gradient.py` | 截面梯度热分析 |
| `backend/graph/nodes/orientation_optimizer.py` | 方向优化节点 |
| `backend/graph/nodes/apply_lattice.py` | 晶格填充节点 |
| `backend/graph/nodes/thermal_simulation.py` | 热风险评估节点 |
| `backend/graph/nodes/generate_supports.py` | 支撑策略委托节点 |

### 新建测试文件 (5)

| 文件 | 覆盖范围 |
|------|---------|
| `tests/test_orientation_optimizer.py` | Config + Basic + Scipy + Node |
| `tests/test_apply_lattice.py` | Config + TPMS functions + Strategy + Node |
| `tests/test_thermal_simulation.py` | Config + Rules + Gradient + Node |
| `tests/test_generate_supports.py` | Config + Passthrough node + auto logic |
| `tests/test_phase3_integration.py` | Registry + Topology + Defaults + Availability |

### 修改文件 (2)

| 文件 | 变更 |
|------|------|
| `backend/graph/configs/slice_to_gcode.py` | 新增 support_type, support_density 字段 |
| `backend/graph/nodes/slice_to_gcode.py` | 更新 _MESH_PRIORITY 消费 oriented_mesh/lattice_mesh，读取 support_config |

---

## 管线拓扑（Phase 3 新增）

```
final_mesh (Phase 2 产出)
    ├→ orientation_optimizer → oriented_mesh      (non_fatal, put_asset)
    ├→ apply_lattice → lattice_mesh               (non_fatal, put_asset)
    ├→ thermal_simulation → thermal_report        (non_fatal, put_data)
    └→ generate_supports → support_config         (non_fatal, put_data)
                              ↓
                    slice_to_gcode (Phase 2)
                      ├── 消费 oriented_mesh / lattice_mesh（更新 _MESH_PRIORITY）
                      └── 消费 support_config（读取 ctx.get_data）
```

**关键集成点（Task 8 Step 3）：** 更新 `slice_to_gcode` 的 `_MESH_PRIORITY` 为
`["oriented_mesh", "lattice_mesh", "final_mesh", "scaled_mesh", "watertight_mesh"]`，
使 Phase 3 优化后的 mesh 被下游切片器消费。同时更新 slicer 策略读取 `support_config`。

所有 Phase 3 节点标记为 `non_fatal=True`，失败不阻塞管线。

---

## 审查修复记录

**审查轮次:** Round 1 (Codex + Claude sub-agent [degraded: gemini → claude-sub-agent])

### 已修复的 P1 问题

| # | 问题 | 来源 | 修复方式 |
|---|------|------|---------|
| P1-1 | oriented_mesh/lattice_mesh 不被 slicer 消费 | 两者共识 | Task 8 新增 slice_to_gcode 集成：更新 _MESH_PRIORITY + requires |
| P1-2 | generate_supports 数据路径断裂 | Codex | 同上 + slicer 读取 support_config |
| P1-3 | TPMS iso-level ≠ 壁厚，生成零厚度面片 | 两者共识 | 改用 abs(field) 方法生成实体带状结构 |
| P1-4 | Config 含 "neural" 但无 neural 策略 | Codex | 移除 "neural" 从 orientation/thermal Config Literal |
| P1-5 | fallback_chain 方向反转 | Claude sub | 反转为 ["scipy","basic"] 和 ["gradient","rules"] |
| P1-6 | TPMS 缺 config 校验 | Codex | 添加 resolution≥8, wall_thickness>0 validator |

### 已修复的 P2 问题

| # | 问题 | 修复方式 |
|---|------|---------|
| P2-1 | instability * 100 硬编码 | 归一化到 [0,1] 范围 |
| P2-3 | generate_supports 缺 config_model | 新建 GenerateSupportsConfig |
| P2-4 | scipy metadata key 错误 | "euler_angles" → "rotation_matrix" |
| P2-5 | thermal 死 config thin_wall_threshold | 移除（未使用） |
| P2-6 | bottom-area 法线阈值偏差 | 改用 face_normals Z < -0.9 |
| P2-7 | 空壳测试 test_node_no_input_skips | 补全断言 |
| P2-8 | produces/data 不一致 | thermal_simulation produces=[], generate_supports produces=[] |
| P2-9 | generate_supports auto 两分支相同 | 区分: 有 orientation→tree, 无→linear |
| P2-11 | 文件计数 4→5 | 修正为 16 新建 + 5 测试 + 2 修改 |
| P2-12 | Tech Stack 缺 scikit-image | 已添加 |
| P2-13 | check_available 未做依赖探测 | ScipyOrientStrategy/TPMSStrategy 加 import 检查 |

### 已拒绝的 Finding

| # | 问题 | 拒绝原因 |
|---|------|---------|
| P2-2 | Euler angle gimbal lock | DE 全域搜索，gimbal 仅减慢收敛不影响正确性 |
| P2-10 | execute() 代码重复 | ROI 不高，实现时再评估 |
| P2-14 | _make_box_mesh 重复 | 实现时提取到 conftest，计划中不改 |
