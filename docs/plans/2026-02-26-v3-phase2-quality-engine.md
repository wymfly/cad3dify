# Phase 2: 生成质量引擎 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 管道级质量提升 — Best-of-N 多路生成、多视角渲染、回滚机制、拓扑验证、结构化 VL 反馈、截面分析，精度从 3-5% 提升到 1-2%。

**Architecture:** 在 Phase 1 已有管道基础上，逐一集成 7 个质量增强模块。每个模块由 `PipelineConfig` 中已定义的开关控制（`best_of_n`, `api_whitelist`, `ast_pre_check`, `multi_view_render`, `structured_feedback`, `rollback_on_degrade`, `topology_check`, `cross_section_check`）。所有模块独立可测、互不依赖（除 Task 2.7 汇总对比）。

**Tech Stack:** Python 3.10+, CadQuery 2.4 (OCCT), LangChain, pytest, Pydantic v2

---

## Task 1: AST 静态预检 + CadQuery API 白名单

**Files:**
- Create: `backend/core/ast_checker.py`
- Create: `backend/core/api_whitelist.py`
- Test: `tests/test_ast_checker.py`

### Step 1: Write the failing tests for AST pre-check

```python
# tests/test_ast_checker.py
"""Tests for AST pre-check and CadQuery API whitelist."""

from __future__ import annotations

import textwrap

import pytest


class TestAstPreCheck:
    def test_valid_code_passes(self) -> None:
        from backend.core.ast_checker import ast_pre_check

        code = textwrap.dedent("""\
            import cadquery as cq
            result = cq.Workplane("XY").box(10, 10, 10)
            cq.exporters.export(result, "output.step")
        """)
        result = ast_pre_check(code)
        assert result.passed is True
        assert result.errors == []

    def test_missing_export_fails(self) -> None:
        from backend.core.ast_checker import ast_pre_check

        code = textwrap.dedent("""\
            import cadquery as cq
            result = cq.Workplane("XY").box(10, 10, 10)
        """)
        result = ast_pre_check(code)
        assert result.passed is False
        assert any("export" in e.lower() for e in result.errors)

    def test_syntax_error_fails(self) -> None:
        from backend.core.ast_checker import ast_pre_check

        result = ast_pre_check("def foo(:\n  pass")
        assert result.passed is False
        assert any("syntax" in e.lower() for e in result.errors)

    def test_blocked_import_fails(self) -> None:
        from backend.core.ast_checker import ast_pre_check

        code = textwrap.dedent("""\
            import os
            import cadquery as cq
            os.system("rm -rf /")
            cq.exporters.export(result, "output.step")
        """)
        result = ast_pre_check(code)
        assert result.passed is False
        assert any("os" in e for e in result.errors)

    def test_undefined_export_variable_warns(self) -> None:
        from backend.core.ast_checker import ast_pre_check

        code = textwrap.dedent("""\
            import cadquery as cq
            box = cq.Workplane("XY").box(10, 10, 10)
            cq.exporters.export(undefined_var, "output.step")
        """)
        result = ast_pre_check(code)
        assert len(result.warnings) > 0


class TestApiWhitelist:
    def test_whitelist_contains_core_apis(self) -> None:
        from backend.core.api_whitelist import CADQUERY_WHITELIST

        assert "Workplane" in CADQUERY_WHITELIST
        assert "exporters.export" in CADQUERY_WHITELIST
        assert "importers.importStep" in CADQUERY_WHITELIST

    def test_whitelist_prompt_injection(self) -> None:
        from backend.core.api_whitelist import get_whitelist_prompt_section

        section = get_whitelist_prompt_section()
        assert "## CadQuery API 使用规范" in section
        assert "Workplane" in section

    def test_blocked_apis_listed(self) -> None:
        from backend.core.api_whitelist import BLOCKED_APIS

        assert "show_object" in BLOCKED_APIS
        assert "addAnnotation" in BLOCKED_APIS
```

### Step 2: Run tests to verify they fail

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_ast_checker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.core.ast_checker'`

### Step 3: Implement AST pre-check and API whitelist

**File: `backend/core/api_whitelist.py`**

```python
"""CadQuery API whitelist — restrict LLM-generated code to verified APIs.

Injected into the code generation prompt when PipelineConfig.api_whitelist=True.
"""

from __future__ import annotations

# Verified CadQuery APIs that LLM code may use.
CADQUERY_WHITELIST: frozenset[str] = frozenset({
    # Workplane creation
    "Workplane",
    # 2D sketch primitives
    "circle", "rect", "ellipse", "polygon", "polyline", "slot2D",
    "moveTo", "lineTo", "hLineTo", "vLineTo", "line", "close",
    "sagittaArc", "radiusArc", "tangentArcPoint", "threePointArc",
    "spline",
    # 3D operations
    "extrude", "revolve", "loft", "sweep", "cut", "cutThruAll",
    "cutBlind", "hole",
    # Selections
    "faces", "edges", "vertices", "wires", "solids", "shells",
    "workplane", "workplaneFromTagged", "tag",
    # Selectors
    ">Z", "<Z", ">X", "<X", ">Y", "<Y",
    # Transforms
    "translate", "rotate", "mirror", "offset",
    # Fillets / chamfers
    "fillet", "chamfer",
    # Arrays
    "polarArray", "rarray",
    # Boolean ops
    "union", "intersect",
    # Export
    "exporters.export",
    # Import
    "importers.importStep",
    # Assembly (limited)
    "Assembly", "add", "save",
})

# APIs that must NOT appear in generated code.
BLOCKED_APIS: frozenset[str] = frozenset({
    "show_object",      # CQ-Editor only
    "addAnnotation",    # not a CadQuery API
    "addText",          # not standard CQ
    "debug",            # CQ-Editor debugging
    "log",              # not CQ
    "cqgi",             # CQ-Editor gateway
})


def get_whitelist_prompt_section() -> str:
    """Return a prompt section listing allowed and blocked APIs."""
    allowed = sorted(CADQUERY_WHITELIST)
    blocked = sorted(BLOCKED_APIS)
    return (
        "## CadQuery API 使用规范\n"
        "### 允许使用的 API\n"
        + ", ".join(f"`{a}`" for a in allowed)
        + "\n\n### 禁止使用的 API（会导致执行失败）\n"
        + ", ".join(f"`{b}`" for b in blocked)
        + "\n"
    )
```

**File: `backend/core/ast_checker.py`**

```python
"""AST pre-check for LLM-generated CadQuery code.

Performs static analysis before execution:
1. Syntax validity
2. Export statement present
3. No blocked imports (os, subprocess, etc.)
4. Undefined variable warnings for export target
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from .api_whitelist import BLOCKED_APIS

# Modules that must not be imported in generated code.
_BLOCKED_IMPORTS: frozenset[str] = frozenset({
    "os", "subprocess", "shutil", "signal", "ctypes", "socket",
    "sys", "importlib", "pathlib",
})


@dataclass
class AstCheckResult:
    """Result of AST pre-check."""
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def ast_pre_check(code: str) -> AstCheckResult:
    """Run static checks on generated code before execution.

    Returns AstCheckResult with passed=False if any hard errors found.
    """
    result = AstCheckResult()

    # 1. Parse
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        result.passed = False
        result.errors.append(f"Syntax error: {e.msg} (line {e.lineno})")
        return result

    # 2. Check for export statement
    has_export = False
    export_var: str | None = None
    assigned_names: set[str] = set()

    for node in ast.walk(tree):
        # Collect all assigned variable names
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned_names.add(target.id)
                elif isinstance(target, ast.Tuple):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name):
                            assigned_names.add(elt.id)

        # Detect export call: cq.exporters.export(var, path)
        if isinstance(node, ast.Call):
            call_str = _call_to_str(node)
            if "export" in call_str:
                has_export = True
                # Extract the first argument as the variable name
                if node.args and isinstance(node.args[0], ast.Name):
                    export_var = node.args[0].id

        # Check for blocked imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BLOCKED_IMPORTS:
                    result.passed = False
                    result.errors.append(
                        f"Blocked import: '{alias.name}' — module '{root}' is not allowed"
                    )

        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in _BLOCKED_IMPORTS:
                result.passed = False
                result.errors.append(
                    f"Blocked import: 'from {node.module}' — module '{root}' is not allowed"
                )

    if not has_export:
        result.passed = False
        result.errors.append(
            "Missing export statement: code must call cq.exporters.export()"
        )

    # 3. Check if export variable is defined
    if export_var and export_var not in assigned_names:
        result.warnings.append(
            f"Export variable '{export_var}' may not be defined in the code"
        )

    return result


def _call_to_str(node: ast.Call) -> str:
    """Best-effort string representation of a call node's function."""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""
```

### Step 4: Run tests to verify they pass

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_ast_checker.py -v`
Expected: PASS — all 8 tests green

### Step 5: Commit

```bash
git add backend/core/ast_checker.py backend/core/api_whitelist.py tests/test_ast_checker.py
git commit -m "feat: AST pre-check + CadQuery API whitelist (Task 2.1a)"
```

---

## Task 2: Best-of-N 多路生成 + 候选评分

**Files:**
- Create: `backend/core/candidate_scorer.py`
- Modify: `backend/core/code_generator.py:42-82` — add `generate_best_of_n()`
- Modify: `backend/pipeline/pipeline.py:125-140` — route through Best-of-N
- Test: `tests/test_best_of_n.py`

### Step 1: Write the failing tests for candidate scoring

```python
# tests/test_best_of_n.py
"""Tests for Best-of-N generation and candidate scoring."""

from __future__ import annotations

import pytest


class TestCandidateScorer:
    def test_compiled_candidate_scores_50(self) -> None:
        from backend.core.candidate_scorer import score_candidate

        score = score_candidate(
            compiled=True, volume_ok=False, bbox_ok=False, topology_ok=False,
        )
        assert score == 50

    def test_all_pass_scores_100(self) -> None:
        from backend.core.candidate_scorer import score_candidate

        score = score_candidate(
            compiled=True, volume_ok=True, bbox_ok=True, topology_ok=True,
        )
        assert score == 100

    def test_uncompiled_scores_zero(self) -> None:
        from backend.core.candidate_scorer import score_candidate

        score = score_candidate(
            compiled=False, volume_ok=True, bbox_ok=True, topology_ok=True,
        )
        assert score == 0

    def test_partial_scores(self) -> None:
        from backend.core.candidate_scorer import score_candidate

        # compiled(50) + volume(20) = 70
        score = score_candidate(
            compiled=True, volume_ok=True, bbox_ok=False, topology_ok=False,
        )
        assert score == 70


class TestSelectBestCandidate:
    def test_selects_highest_score(self) -> None:
        from backend.core.candidate_scorer import select_best

        candidates = [
            {"code": "a", "score": 50},
            {"code": "b", "score": 90},
            {"code": "c", "score": 70},
        ]
        best = select_best(candidates)
        assert best["code"] == "b"
        assert best["score"] == 90

    def test_empty_candidates_returns_none(self) -> None:
        from backend.core.candidate_scorer import select_best

        assert select_best([]) is None

    def test_single_candidate(self) -> None:
        from backend.core.candidate_scorer import select_best

        best = select_best([{"code": "a", "score": 50}])
        assert best["code"] == "a"
```

### Step 2: Run tests to verify they fail

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_best_of_n.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Implement candidate scorer

**File: `backend/core/candidate_scorer.py`**

```python
"""Candidate scoring for Best-of-N code generation.

Score breakdown (total 100):
- Compiled successfully: 50 points
- Volume within tolerance: 20 points
- Bounding box within tolerance: 20 points
- Topology valid: 10 points

A candidate that fails compilation gets 0 (the other checks require a STEP file).
"""

from __future__ import annotations


def score_candidate(
    *,
    compiled: bool,
    volume_ok: bool = False,
    bbox_ok: bool = False,
    topology_ok: bool = False,
) -> int:
    """Score a single code candidate. Returns 0-100."""
    if not compiled:
        return 0
    score = 50
    if volume_ok:
        score += 20
    if bbox_ok:
        score += 20
    if topology_ok:
        score += 10
    return score


def select_best(candidates: list[dict]) -> dict | None:
    """Select the highest-scoring candidate from a list.

    Each item should have at minimum: {"code": str, "score": int}.
    Returns None if the list is empty.
    """
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["score"])
```

### Step 4: Run tests to verify they pass

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_best_of_n.py -v`
Expected: PASS

### Step 5: Integrate Best-of-N into CodeGeneratorChain

Modify `backend/core/code_generator.py` — add `generate_n_candidates()` method to `CodeGeneratorChain`.

Key changes:
- Add method that calls the chain N times and returns a list of code strings
- Each call uses the same `ModelingContext` but different random seed (temperature > 0)
- Filter out None results (parse failures)

### Step 6: Integrate Best-of-N into pipeline

Modify `backend/pipeline/pipeline.py:125-140` — when `config.best_of_n > 1`:
1. Generate N code candidates
2. For each candidate: AST pre-check → execute → geometry validate → score
3. Select best candidate
4. Pass best into SmartRefiner loop

When `config.best_of_n == 1`: use existing single-generation path (no behavior change).

### Step 7: Run all existing tests

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/ -v`
Expected: All existing tests still PASS

### Step 8: Commit

```bash
git add backend/core/candidate_scorer.py backend/core/code_generator.py backend/pipeline/pipeline.py tests/test_best_of_n.py
git commit -m "feat: Best-of-N multi-candidate generation + scoring (Task 2.1b)"
```

---

## Task 3: 多视角渲染

**Files:**
- Modify: `backend/infra/render.py:1-22` — add `render_multi_view()`
- Modify: `backend/core/smart_refiner.py:112-157` — accept multi-view images
- Test: `tests/test_multi_view_render.py`

### Step 1: Write the failing tests

```python
# tests/test_multi_view_render.py
"""Tests for multi-view rendering."""

from __future__ import annotations

import pytest


class TestMultiViewConfig:
    def test_standard_views_defined(self) -> None:
        from backend.infra.render import STANDARD_VIEWS

        assert len(STANDARD_VIEWS) == 4
        assert "front" in STANDARD_VIEWS
        assert "top" in STANDARD_VIEWS
        assert "side" in STANDARD_VIEWS
        assert "isometric" in STANDARD_VIEWS

    def test_each_view_has_camera_params(self) -> None:
        from backend.infra.render import STANDARD_VIEWS

        for name, params in STANDARD_VIEWS.items():
            assert "direction" in params, f"View '{name}' missing direction"
            assert len(params["direction"]) == 3, f"View '{name}' direction must be (x,y,z)"


class TestRenderMultiView:
    def test_renders_four_views(self, tmp_path) -> None:
        """Generate a simple STEP and render 4 views."""
        import cadquery as cq

        step_path = str(tmp_path / "test.step")
        result = cq.Workplane("XY").box(100, 50, 30)
        cq.exporters.export(result, step_path)

        from backend.infra.render import render_multi_view

        images = render_multi_view(step_path, str(tmp_path))
        assert len(images) == 4
        for view_name, img_path in images.items():
            from pathlib import Path
            assert Path(img_path).exists(), f"View '{view_name}' image not created"

    def test_single_view_fallback(self, tmp_path) -> None:
        """When called with a single view name, renders only that view."""
        import cadquery as cq

        step_path = str(tmp_path / "test.step")
        result = cq.Workplane("XY").box(100, 50, 30)
        cq.exporters.export(result, step_path)

        from backend.infra.render import render_multi_view

        images = render_multi_view(step_path, str(tmp_path), views=["front"])
        assert len(images) == 1
        assert "front" in images
```

### Step 2: Run tests to verify they fail

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_multi_view_render.py -v`
Expected: FAIL — `ImportError: cannot import name 'STANDARD_VIEWS'`

### Step 3: Implement multi-view rendering

Modify `backend/infra/render.py`:
- Add `STANDARD_VIEWS` dict with 4 camera configurations
- Add `render_multi_view(step_path, output_dir, views=None)` that:
  1. Loads STEP with CadQuery
  2. For each view: exports SVG with appropriate camera → converts to PNG
  3. Returns `dict[str, str]` mapping view name → PNG path

CadQuery SVG export supports `opt` parameter for camera direction:
```python
exporters.export(shape, path, exportType=exporters.ExportTypes.SVG,
                 opt={"projectionDir": direction})
```

### Step 4: Run tests to verify they pass

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_multi_view_render.py -v`
Expected: PASS

### Step 5: Update SmartRefiner to accept multi-view images

Modify `backend/core/smart_refiner.py`:
- `SmartCompareChain.__init__`: accept a list of rendered images instead of single image
- `_COMPARE_PROMPT`: update to instruct VL to compare each view
- `SmartRefiner.refine()`: accept `rendered_images: dict[str, ImageData]` parameter
- When `multi_view=True`, pass all view images; when `False`, keep single image behavior

### Step 6: Run all tests

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/ -v`
Expected: All tests PASS

### Step 7: Commit

```bash
git add backend/infra/render.py backend/core/smart_refiner.py tests/test_multi_view_render.py
git commit -m "feat: multi-view rendering for VL comparison (Task 2.2)"
```

---

## Task 4: 回滚机制

**Files:**
- Create: `backend/core/rollback.py`
- Modify: `backend/pipeline/pipeline.py:159-207` — integrate rollback into refine loop
- Test: `tests/test_rollback.py`

### Step 1: Write the failing tests

```python
# tests/test_rollback.py
"""Tests for refinement rollback mechanism."""

from __future__ import annotations

import pytest


class TestRollbackTracker:
    def test_initial_state_empty(self) -> None:
        from backend.core.rollback import RollbackTracker

        tracker = RollbackTracker()
        assert tracker.current_code is None
        assert tracker.current_score == 0.0
        assert tracker.rollback_count == 0

    def test_save_snapshot(self) -> None:
        from backend.core.rollback import RollbackTracker

        tracker = RollbackTracker()
        tracker.save("code_v1", 80.0)
        assert tracker.current_code == "code_v1"
        assert tracker.current_score == 80.0

    def test_no_rollback_on_improvement(self) -> None:
        from backend.core.rollback import RollbackTracker

        tracker = RollbackTracker()
        tracker.save("code_v1", 80.0)
        should_rollback, _ = tracker.check_and_update("code_v2", 85.0)
        assert should_rollback is False
        assert tracker.current_code == "code_v2"
        assert tracker.current_score == 85.0

    def test_rollback_on_degradation(self) -> None:
        from backend.core.rollback import RollbackTracker

        tracker = RollbackTracker(threshold=0.10)
        tracker.save("code_v1", 80.0)
        # 80 → 60 is 25% drop, exceeds 10% threshold
        should_rollback, prev_code = tracker.check_and_update("code_v2", 60.0)
        assert should_rollback is True
        assert prev_code == "code_v1"
        assert tracker.rollback_count == 1
        # After rollback, current should revert to v1
        assert tracker.current_code == "code_v1"
        assert tracker.current_score == 80.0

    def test_no_rollback_on_small_degradation(self) -> None:
        from backend.core.rollback import RollbackTracker

        tracker = RollbackTracker(threshold=0.10)
        tracker.save("code_v1", 80.0)
        # 80 → 75 is 6.25% drop, below 10% threshold
        should_rollback, _ = tracker.check_and_update("code_v2", 75.0)
        assert should_rollback is False
        assert tracker.current_code == "code_v2"

    def test_zero_score_baseline_no_division_error(self) -> None:
        from backend.core.rollback import RollbackTracker

        tracker = RollbackTracker()
        tracker.save("code_v1", 0.0)
        should_rollback, _ = tracker.check_and_update("code_v2", 50.0)
        assert should_rollback is False
```

### Step 2: Run tests to verify they fail

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_rollback.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Implement rollback tracker

**File: `backend/core/rollback.py`**

```python
"""Rollback mechanism for SmartRefiner — prevents quality degradation.

Tracks code snapshots and geometry scores across refinement rounds.
If a refinement degrades the score by more than the threshold,
automatically rolls back to the previous version.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger


@dataclass
class RollbackTracker:
    """Track refinement quality and rollback on degradation."""

    threshold: float = 0.10  # 10% degradation triggers rollback
    current_code: str | None = None
    current_score: float = 0.0
    rollback_count: int = 0

    def save(self, code: str, score: float) -> None:
        """Save a code snapshot with its quality score."""
        self.current_code = code
        self.current_score = score

    def check_and_update(
        self, new_code: str, new_score: float
    ) -> tuple[bool, str | None]:
        """Check if new code degrades quality beyond threshold.

        Returns (should_rollback, previous_code).
        If should_rollback is True, the tracker reverts to the previous state.
        """
        if self.current_score <= 0:
            # No meaningful baseline — accept the new code
            self.current_code = new_code
            self.current_score = new_score
            return False, None

        degradation = (self.current_score - new_score) / self.current_score

        if degradation > self.threshold:
            logger.warning(
                f"Rollback triggered: score {self.current_score:.1f} → {new_score:.1f} "
                f"(degradation {degradation:.1%} > threshold {self.threshold:.1%})"
            )
            self.rollback_count += 1
            prev_code = self.current_code
            # Keep current state (rollback = don't update)
            return True, prev_code

        # Accept improvement or minor degradation
        self.current_code = new_code
        self.current_score = new_score
        return False, None
```

### Step 4: Run tests to verify they pass

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_rollback.py -v`
Expected: PASS — all 6 tests green

### Step 5: Integrate rollback into pipeline refinement loop

Modify `backend/pipeline/pipeline.py:159-207`:
- Before refine loop: create `RollbackTracker`, save initial code + score
- After each refinement round: compute new score, call `tracker.check_and_update()`
- If rollback triggered: restore previous code, log SSE rollback event, continue loop
- When `config.rollback_on_degrade=False`: skip rollback check

### Step 6: Run all tests

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/ -v`
Expected: All tests PASS

### Step 7: Commit

```bash
git add backend/core/rollback.py backend/pipeline/pipeline.py tests/test_rollback.py
git commit -m "feat: rollback mechanism for refinement degradation (Task 2.3)"
```

---

## Task 5: 拓扑验证

**Files:**
- Modify: `backend/core/validators.py:440-510` — add `count_topology()`
- Modify: `backend/core/smart_refiner.py:220-254` — inject topology diagnostics
- Test: `tests/test_topology.py`

### Step 1: Write the failing tests

```python
# tests/test_topology.py
"""Tests for topology validation."""

from __future__ import annotations

import pytest


class TestCountTopology:
    def test_simple_box(self, tmp_path) -> None:
        """A box has 6 faces, 12 edges, 8 vertices, 1 solid, 1 shell."""
        import cadquery as cq

        step_path = str(tmp_path / "box.step")
        result = cq.Workplane("XY").box(100, 50, 30)
        cq.exporters.export(result, step_path)

        from backend.core.validators import count_topology

        topo = count_topology(step_path)
        assert topo.num_solids == 1
        assert topo.num_shells == 1
        assert topo.num_faces == 6
        assert topo.num_planar_faces == 6
        assert topo.num_cylindrical_faces == 0

    def test_cylinder_with_hole(self, tmp_path) -> None:
        """A cylinder with a through-hole has cylindrical faces."""
        import cadquery as cq

        step_path = str(tmp_path / "cyl_hole.step")
        result = (
            cq.Workplane("XY")
            .circle(50).extrude(30)
            .faces(">Z").workplane()
            .hole(20)
        )
        cq.exporters.export(result, step_path)

        from backend.core.validators import count_topology

        topo = count_topology(step_path)
        assert topo.num_solids == 1
        assert topo.num_cylindrical_faces >= 2  # outer + inner

    def test_nonexistent_file(self) -> None:
        from backend.core.validators import count_topology

        topo = count_topology("/nonexistent.step")
        assert topo.error != ""

    def test_topology_comparison(self) -> None:
        """Compare topology counts with expected from spec."""
        from backend.core.validators import TopologyResult, compare_topology

        actual = TopologyResult(
            num_solids=1, num_shells=1, num_faces=8,
            num_cylindrical_faces=2, num_planar_faces=6,
        )
        expected_holes = 1  # 1 through-hole = 2 cylindrical faces (inner + outer)
        result = compare_topology(actual, expected_holes=expected_holes)
        assert result.passed is True

    def test_topology_mismatch(self) -> None:
        from backend.core.validators import TopologyResult, compare_topology

        actual = TopologyResult(
            num_solids=1, num_shells=1, num_faces=6,
            num_cylindrical_faces=0, num_planar_faces=6,
        )
        expected_holes = 3  # expect 3 holes but got 0 cylindrical faces
        result = compare_topology(actual, expected_holes=expected_holes)
        assert result.passed is False
        assert len(result.mismatches) > 0
```

### Step 2: Run tests to verify they fail

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_topology.py -v`
Expected: FAIL — `ImportError: cannot import name 'count_topology'`

### Step 3: Implement topology counting

Add to `backend/core/validators.py` (after the `estimate_volume` function):

```python
@dataclass
class TopologyResult:
    """Result of topology analysis on a STEP file."""
    num_solids: int = 0
    num_shells: int = 0
    num_faces: int = 0
    num_cylindrical_faces: int = 0
    num_planar_faces: int = 0
    error: str = ""


def count_topology(step_filepath: str) -> TopologyResult:
    """Count topological entities in a STEP file.

    Counts solids, shells, faces (total, cylindrical, planar).
    Cylindrical face count is useful for detecting holes and bores.
    """
    try:
        import cadquery as cq
        shape = cq.importers.importStep(step_filepath)
        solid = shape.val()

        # Count face types using OCCT
        from OCP.BRep import BRep_Tool
        from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer

        num_solids = 0
        exp = TopExp_Explorer(solid.wrapped, TopAbs_SOLID)
        while exp.More():
            num_solids += 1
            exp.Next()

        num_shells = 0
        exp = TopExp_Explorer(solid.wrapped, TopAbs_SHELL)
        while exp.More():
            num_shells += 1
            exp.Next()

        num_faces = 0
        num_cylindrical = 0
        num_planar = 0
        exp = TopExp_Explorer(solid.wrapped, TopAbs_FACE)
        while exp.More():
            num_faces += 1
            face = exp.Value()
            adaptor = BRepAdaptor_Surface(face)
            surface_type = adaptor.GetType()
            if surface_type == GeomAbs_Cylinder:
                num_cylindrical += 1
            elif surface_type == GeomAbs_Plane:
                num_planar += 1
            exp.Next()

        return TopologyResult(
            num_solids=num_solids,
            num_shells=num_shells,
            num_faces=num_faces,
            num_cylindrical_faces=num_cylindrical,
            num_planar_faces=num_planar,
        )
    except FileNotFoundError:
        return TopologyResult(error=f"File not found: {step_filepath}")
    except Exception as e:
        return TopologyResult(error=str(e))


@dataclass
class TopologyCompareResult:
    """Result of comparing actual topology with expected."""
    passed: bool = True
    mismatches: list[str] = field(default_factory=list)


def compare_topology(
    actual: TopologyResult,
    *,
    expected_holes: int = 0,
) -> TopologyCompareResult:
    """Compare topology counts with expected features.

    Each through-hole contributes ~2 cylindrical faces (inner bore wall).
    Tolerance: ±1 face per expected hole.
    """
    result = TopologyCompareResult()

    if expected_holes > 0:
        # Each hole typically adds at least 1 cylindrical face
        min_expected_cyl = expected_holes
        if actual.num_cylindrical_faces < min_expected_cyl:
            result.passed = False
            result.mismatches.append(
                f"Expected at least {min_expected_cyl} cylindrical faces "
                f"for {expected_holes} hole(s), got {actual.num_cylindrical_faces}"
            )

    if actual.num_solids == 0:
        result.passed = False
        result.mismatches.append("No solids found in STEP file")

    return result
```

### Step 4: Run tests to verify they pass

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_topology.py -v`
Expected: PASS

### Step 5: Inject topology into SmartRefiner diagnostics

Modify `backend/core/smart_refiner.py:220-254` — after Layer 2 (bbox), add:
```python
# ---- Layer 2.5: Topology check (diagnostic, does not affect VL) ----
if step_filepath and topology_check:
    from .validators import count_topology, compare_topology
    topo = count_topology(step_filepath)
    if topo.error == "":
        # Count expected holes from spec features
        expected_holes = sum(
            1 for f in drawing_spec.features
            if f.get("type") in ("hole_pattern", "bore", "hole")
        )
        topo_result = compare_topology(topo, expected_holes=expected_holes)
        if not topo_result.passed:
            static_notes.extend(topo_result.mismatches)
```

### Step 6: Run all tests

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/ -v`
Expected: All tests PASS

### Step 7: Commit

```bash
git add backend/core/validators.py backend/core/smart_refiner.py tests/test_topology.py
git commit -m "feat: topology validation — count faces/shells/solids (Task 2.4)"
```

---

## Task 6: 结构化 VL 反馈

**Files:**
- Modify: `backend/core/smart_refiner.py:24-61` — rewrite `_COMPARE_PROMPT`
- Modify: `backend/core/smart_refiner.py:94-107` — rewrite `_extract_comparison()`
- Create: `backend/core/vl_feedback.py` — JSON parsing + fallback
- Test: `tests/test_structured_feedback.py`

### Step 1: Write the failing tests

```python
# tests/test_structured_feedback.py
"""Tests for structured VL feedback parsing."""

from __future__ import annotations

import json
import textwrap

import pytest


class TestParseVLFeedback:
    def test_valid_json_issues(self) -> None:
        from backend.core.vl_feedback import parse_vl_feedback

        raw = json.dumps({
            "verdict": "FAIL",
            "issues": [
                {
                    "type": "dimension",
                    "severity": "high",
                    "description": "大端直径偏小",
                    "expected": "100mm",
                    "actual": "80mm",
                    "location": "底部法兰",
                },
            ],
        })
        result = parse_vl_feedback(raw)
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0]["type"] == "dimension"

    def test_pass_verdict(self) -> None:
        from backend.core.vl_feedback import parse_vl_feedback

        raw = json.dumps({"verdict": "PASS", "issues": []})
        result = parse_vl_feedback(raw)
        assert result.passed is True
        assert result.issues == []

    def test_fallback_on_free_text(self) -> None:
        """When VL returns free text instead of JSON, gracefully fall back."""
        from backend.core.vl_feedback import parse_vl_feedback

        raw = "问题1: 直径偏小\n预期: 100mm\n修改: 增大 d1"
        result = parse_vl_feedback(raw)
        assert result.passed is False
        assert result.raw_text == raw

    def test_pass_keyword_in_short_text(self) -> None:
        from backend.core.vl_feedback import parse_vl_feedback

        result = parse_vl_feedback("PASS")
        assert result.passed is True

    def test_to_fix_instructions(self) -> None:
        from backend.core.vl_feedback import parse_vl_feedback

        raw = json.dumps({
            "verdict": "FAIL",
            "issues": [
                {
                    "type": "dimension",
                    "severity": "high",
                    "description": "大端直径偏小",
                    "expected": "100mm",
                    "actual": "80mm",
                    "location": "底部法兰",
                },
                {
                    "type": "structural",
                    "severity": "medium",
                    "description": "缺少通孔",
                    "expected": "中心通孔 25mm",
                    "actual": "无",
                    "location": "中心",
                },
            ],
        })
        result = parse_vl_feedback(raw)
        instructions = result.to_fix_instructions()
        assert "大端直径偏小" in instructions
        assert "缺少通孔" in instructions
```

### Step 2: Run tests to verify they fail

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_structured_feedback.py -v`
Expected: FAIL

### Step 3: Implement structured feedback parser

**File: `backend/core/vl_feedback.py`**

```python
"""Structured VL feedback parser.

Parses JSON feedback from VL model with graceful fallback for free-text.

Expected JSON format:
{
    "verdict": "PASS" | "FAIL",
    "issues": [
        {
            "type": "dimension" | "structural" | "feature" | "orientation",
            "severity": "high" | "medium" | "low",
            "description": "...",
            "expected": "...",
            "actual": "...",
            "location": "..."
        }
    ]
}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class VLFeedback:
    """Parsed VL comparison feedback."""
    passed: bool = False
    issues: list[dict] = field(default_factory=list)
    raw_text: str = ""

    def to_fix_instructions(self) -> str:
        """Convert issues to fix instructions for Coder model."""
        if self.passed:
            return ""
        if not self.issues:
            return self.raw_text

        lines = []
        for i, issue in enumerate(self.issues, 1):
            severity = issue.get("severity", "medium")
            desc = issue.get("description", "")
            expected = issue.get("expected", "")
            location = issue.get("location", "")
            lines.append(
                f"问题{i} [{severity}]: {desc}"
                + (f"\n  预期: {expected}" if expected else "")
                + (f"\n  位置: {location}" if location else "")
            )
        return "\n\n".join(lines)


def parse_vl_feedback(raw: str) -> VLFeedback:
    """Parse VL model output into structured feedback.

    Attempts JSON parsing first, falls back to free-text heuristic.
    """
    text = raw.strip()

    # Short PASS response
    if text.upper() == "PASS" or (len(text) < 20 and "PASS" in text.upper()):
        return VLFeedback(passed=True)

    # Try JSON parsing (may be wrapped in markdown code block)
    json_text = text
    if "```" in text:
        # Extract JSON from code block
        import re
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            json_text = match.group(1).strip()

    try:
        data = json.loads(json_text)
        verdict = data.get("verdict", "").upper()
        issues = data.get("issues", [])
        return VLFeedback(
            passed=(verdict == "PASS"),
            issues=issues,
            raw_text=raw,
        )
    except (json.JSONDecodeError, AttributeError):
        logger.debug("VL output is not valid JSON, using free-text fallback")

    # Free-text fallback
    return VLFeedback(passed=False, raw_text=raw)
```

### Step 4: Run tests to verify they pass

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_structured_feedback.py -v`
Expected: PASS

### Step 5: Update SmartRefiner prompts

Modify `backend/core/smart_refiner.py`:

1. **`_COMPARE_PROMPT`** — replace free-text output format with JSON schema:
```
输出格式要求：JSON
{
    "verdict": "PASS" 或 "FAIL",
    "issues": [
        {
            "type": "dimension|structural|feature|orientation",
            "severity": "high|medium|low",
            "description": "问题描述",
            "expected": "预期值",
            "actual": "实际值",
            "location": "位置"
        }
    ]
}
```

2. **`_extract_comparison`** — replace with `parse_vl_feedback()` call:
```python
from .vl_feedback import parse_vl_feedback

def _extract_comparison(input: dict) -> dict:
    feedback = parse_vl_feedback(input["text"])
    if feedback.passed:
        return {"result": None}
    return {"result": feedback.to_fix_instructions()}
```

When `PipelineConfig.structured_feedback=False`, use original free-text prompt (backward compatible).

### Step 6: Run all tests

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/ -v`
Expected: All tests PASS

### Step 7: Commit

```bash
git add backend/core/vl_feedback.py backend/core/smart_refiner.py tests/test_structured_feedback.py
git commit -m "feat: structured JSON VL feedback (Task 2.5)"
```

---

## Task 7: 截面分析验证

**Files:**
- Modify: `backend/core/validators.py` — add `cross_section_analysis()`
- Test: `tests/test_cross_section.py`

### Step 1: Write the failing tests

```python
# tests/test_cross_section.py
"""Tests for cross-section analysis validation."""

from __future__ import annotations

import math

import pytest

from cad3dify.knowledge.part_types import (
    BaseBodySpec,
    DimensionLayer,
    DrawingSpec,
    PartType,
)


def _make_stepped_spec() -> DrawingSpec:
    """Stepped shaft: d1=100 h1=30, d2=60 h2=40."""
    return DrawingSpec(
        part_type=PartType.ROTATIONAL_STEPPED,
        description="Stepped shaft",
        base_body=BaseBodySpec(
            method="revolve",
            profile=[
                DimensionLayer(diameter=100, height=30),
                DimensionLayer(diameter=60, height=40),
            ],
        ),
    )


class TestCrossSectionAnalysis:
    def test_stepped_cylinder(self, tmp_path) -> None:
        """Stepped cylinder: cut at h=15 (d=100) and h=50 (d=60)."""
        import cadquery as cq

        step_path = str(tmp_path / "stepped.step")
        # Build a stepped cylinder: base d=100 h=30, top d=60 h=40
        result = (
            cq.Workplane("XY")
            .circle(50).extrude(30)
            .faces(">Z").workplane()
            .circle(30).extrude(40)
        )
        cq.exporters.export(result, step_path)

        from backend.core.validators import cross_section_analysis

        spec = _make_stepped_spec()
        analysis = cross_section_analysis(step_path, spec)

        assert len(analysis.sections) == 2
        # Section at mid-height of layer 0: h=15, expected d~100
        assert abs(analysis.sections[0].measured_diameter - 100) < 5
        # Section at mid-height of layer 1: h=30+20=50, expected d~60
        assert abs(analysis.sections[1].measured_diameter - 60) < 5

    def test_mismatched_diameter_detected(self, tmp_path) -> None:
        """Build wrong diameter — cross section should detect mismatch."""
        import cadquery as cq

        step_path = str(tmp_path / "wrong.step")
        # Wrong: base d=80 instead of spec's 100
        result = (
            cq.Workplane("XY")
            .circle(40).extrude(30)
            .faces(">Z").workplane()
            .circle(30).extrude(40)
        )
        cq.exporters.export(result, step_path)

        from backend.core.validators import cross_section_analysis

        spec = _make_stepped_spec()
        analysis = cross_section_analysis(step_path, spec)
        assert any(not s.within_tolerance for s in analysis.sections)

    def test_nonexistent_file(self) -> None:
        from backend.core.validators import cross_section_analysis

        spec = _make_stepped_spec()
        analysis = cross_section_analysis("/nonexistent.step", spec)
        assert analysis.error != ""
```

### Step 2: Run tests to verify they fail

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_cross_section.py -v`
Expected: FAIL — `ImportError: cannot import name 'cross_section_analysis'`

### Step 3: Implement cross-section analysis

Add to `backend/core/validators.py`:

```python
@dataclass
class CrossSectionResult:
    """Result of a single cross-section measurement."""
    height: float = 0.0
    expected_diameter: float = 0.0
    measured_diameter: float = 0.0
    within_tolerance: bool = True
    deviation_pct: float = 0.0


@dataclass
class CrossSectionAnalysis:
    """Result of cross-section analysis across all spec layers."""
    sections: list[CrossSectionResult] = field(default_factory=list)
    error: str = ""


def cross_section_analysis(
    step_filepath: str,
    spec: DrawingSpec,
    tolerance: float = 0.10,
) -> CrossSectionAnalysis:
    """Cut cross-sections at spec layer mid-heights and measure diameters.

    For rotational/stepped parts, each profile layer defines a height range.
    We cut at the mid-height of each layer and measure the bounding box
    width/depth to approximate the diameter at that height.
    """
    if not spec.base_body.profile:
        return CrossSectionAnalysis(error="No profile layers in spec")

    try:
        import cadquery as cq
        shape = cq.importers.importStep(step_filepath)
        solid = shape.val()
    except FileNotFoundError:
        return CrossSectionAnalysis(error=f"File not found: {step_filepath}")
    except Exception as e:
        return CrossSectionAnalysis(error=str(e))

    sections: list[CrossSectionResult] = []
    cumulative_h = 0.0

    for layer in spec.base_body.profile:
        mid_h = cumulative_h + layer.height / 2
        cumulative_h += layer.height

        try:
            # Cut a cross-section at mid_h on the Z axis
            # Use BoundingBox of the cross-section to estimate diameter
            section_plane = cq.Workplane("XY").workplane(offset=mid_h)
            # Use OCCT section approach
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
            from OCP.gp import gp_Pln, gp_Pnt, gp_Dir

            plane = gp_Pln(gp_Pnt(0, 0, mid_h), gp_Dir(0, 0, 1))
            section = BRepAlgoAPI_Section(solid.wrapped, plane)
            section.Build()

            if section.IsDone():
                section_shape = cq.Shape(section.Shape())
                bb = section_shape.BoundingBox()
                measured_d = max(bb.xlen, bb.ylen)
            else:
                measured_d = 0.0

        except Exception:
            measured_d = 0.0

        expected_d = layer.diameter
        deviation = abs(measured_d - expected_d) / expected_d if expected_d > 0 else 0
        within_tol = deviation <= tolerance

        sections.append(CrossSectionResult(
            height=mid_h,
            expected_diameter=expected_d,
            measured_diameter=measured_d,
            within_tolerance=within_tol,
            deviation_pct=deviation * 100,
        ))

    return CrossSectionAnalysis(sections=sections)
```

### Step 4: Run tests to verify they pass

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_cross_section.py -v`
Expected: PASS

### Step 5: Run all tests

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/ -v`
Expected: All tests PASS

### Step 6: Commit

```bash
git add backend/core/validators.py tests/test_cross_section.py
git commit -m "feat: cross-section analysis for stepped parts (Task 2.6)"
```

---

## Task 8: 管道集成 — 将所有质量增强模块接入 pipeline

**Files:**
- Modify: `backend/pipeline/pipeline.py` — full integration
- Modify: `backend/core/code_generator.py` — whitelist injection
- Modify: `backend/core/smart_refiner.py` — accept config flags
- Test: `tests/test_pipeline_integration.py`

### Step 1: Write integration test

```python
# tests/test_pipeline_integration.py
"""Integration tests for Phase 2 pipeline config flags."""

from __future__ import annotations

import pytest

from backend.models.pipeline_config import PipelineConfig, PRESETS


class TestPhase2ConfigFlags:
    def test_balanced_preset_enables_phase2_features(self) -> None:
        config = PRESETS["balanced"]
        assert config.best_of_n == 3
        assert config.api_whitelist is True
        assert config.ast_pre_check is True
        assert config.multi_view_render is True
        assert config.structured_feedback is True
        assert config.rollback_on_degrade is True
        assert config.topology_check is True

    def test_fast_preset_disables_phase2_features(self) -> None:
        config = PRESETS["fast"]
        assert config.best_of_n == 1
        assert config.multi_view_render is False
        assert config.topology_check is False

    def test_precise_preset_enables_all(self) -> None:
        config = PRESETS["precise"]
        assert config.best_of_n == 5
        assert config.cross_section_check is True
        assert config.multi_view_render is True
        assert config.structured_feedback is True
```

### Step 2: Run test to verify it passes (config already in place from Phase 1)

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_pipeline_integration.py -v`
Expected: PASS (presets already defined in `pipeline_config.py`)

### Step 3: Integrate all modules into pipeline.py

Modify `backend/pipeline/pipeline.py` — `generate_step_v2()`:

```python
def generate_step_v2(
    image_filepath: str,
    output_filepath: str,
    num_refinements: int = 3,
    config: PipelineConfig | None = None,
    on_spec_ready: callable = None,
    on_progress: callable = None,
):
    config = config or PipelineConfig()

    # ... (existing Stage 1: VL analysis, Stage 1.5: strategy) ...

    # Stage 2: Code generation
    if config.api_whitelist:
        from ..core.api_whitelist import get_whitelist_prompt_section
        # Inject whitelist into context.strategy
        context.strategy += "\n\n" + get_whitelist_prompt_section()

    if config.best_of_n > 1:
        # Best-of-N path
        from ..core.candidate_scorer import score_candidate, select_best
        from ..core.ast_checker import ast_pre_check

        candidates = []
        for i in range(config.best_of_n):
            result = generator.invoke(context)["result"]
            if result is None:
                continue
            code_i = Template(result).substitute(output_filename=output_filepath)

            # AST pre-check
            if config.ast_pre_check:
                check = ast_pre_check(code_i)
                if not check.passed:
                    candidates.append({"code": code_i, "score": 0})
                    continue

            # Execute + validate
            try:
                execute_python_code(code_i, ...)
                geo = validate_step_geometry(output_filepath)
                s = score_candidate(
                    compiled=True,
                    volume_ok=...,   # compare with estimate_volume
                    bbox_ok=...,     # compare bbox
                    topology_ok=..., # topology check
                )
            except Exception:
                s = 0
            candidates.append({"code": code_i, "score": s, "geo": geo})

        best = select_best(candidates)
        if best:
            code = best["code"]
        else:
            logger.error("[V2] All candidates failed")
            return
    else:
        # Single generation (existing path)
        ...

    # Stage 4: Smart refinement with rollback
    from ..core.rollback import RollbackTracker
    tracker = RollbackTracker() if config.rollback_on_degrade else None
    if tracker:
        tracker.save(code, initial_score)

    refiner = SmartRefiner()
    for i in range(config.max_refinements):
        # Render (multi-view or single)
        if config.multi_view_render:
            images = render_multi_view(output_filepath, tmpdir)
            rendered_images = {k: ImageData.load_from_file(v) for k, v in images.items()}
        else:
            # single view (existing path)
            ...

        refined_code = refiner.refine(
            code=code,
            original_image=image_data,
            rendered_images=rendered_images,
            drawing_spec=spec,
            step_filepath=output_filepath,
            structured_feedback=config.structured_feedback,
            topology_check=config.topology_check,
        )

        if refined_code is None:
            break  # PASS

        # Execute refined code
        code = Template(refined_code).substitute(output_filename=output_filepath)
        execute_python_code(code, ...)
        new_geo = validate_step_geometry(output_filepath)
        new_score = score_candidate(compiled=True, ...)

        # Rollback check
        if tracker:
            should_rollback, prev = tracker.check_and_update(code, new_score)
            if should_rollback:
                code = prev
                # Re-execute previous code to restore STEP
                execute_python_code(code, ...)
                if on_progress:
                    on_progress("rollback", {"round": i + 1})
                continue

    # Cross-section check (post-refinement diagnostic)
    if config.cross_section_check:
        from ..core.validators import cross_section_analysis
        cs = cross_section_analysis(output_filepath, spec)
        if on_progress:
            on_progress("cross_section", {"sections": [...]})
```

### Step 4: Run all tests

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/ -v`
Expected: All tests PASS

### Step 5: Commit

```bash
git add backend/pipeline/pipeline.py backend/core/code_generator.py backend/core/smart_refiner.py tests/test_pipeline_integration.py
git commit -m "feat: integrate all Phase 2 modules into pipeline (Task 2.1-2.6)"
```

---

## Task 9: Benchmark 对比报告 (Task 2.7)

**Files:**
- Modify: `backend/benchmark/runner.py:149-171` — integrate actual V2 pipeline
- Create: `backend/benchmark/comparator.py`
- Test: `tests/test_benchmark_comparison.py`

### Step 1: Write the failing tests

```python
# tests/test_benchmark_comparison.py
"""Tests for benchmark comparison report generation."""

from __future__ import annotations

import pytest

from backend.benchmark.metrics import BenchmarkMetrics


class TestBenchmarkComparator:
    def test_compute_delta(self) -> None:
        from backend.benchmark.comparator import compute_comparison

        baseline = BenchmarkMetrics(
            compile_rate=0.60, type_accuracy=0.40,
            param_accuracy_p50=0.50, bbox_match_rate=0.40,
            avg_duration_s=15.0, avg_tokens=1000,
        )
        enhanced = BenchmarkMetrics(
            compile_rate=0.80, type_accuracy=0.60,
            param_accuracy_p50=0.70, bbox_match_rate=0.60,
            avg_duration_s=25.0, avg_tokens=3000,
        )
        report = compute_comparison(baseline, enhanced)
        assert report["compile_rate"]["delta"] == pytest.approx(0.20)
        assert report["compile_rate"]["improved"] is True
        assert report["avg_duration_s"]["improved"] is False  # higher is worse for duration

    def test_markdown_output(self) -> None:
        from backend.benchmark.comparator import comparison_to_markdown

        comparison = {
            "compile_rate": {"baseline": 0.6, "enhanced": 0.8, "delta": 0.2, "improved": True},
            "type_accuracy": {"baseline": 0.4, "enhanced": 0.6, "delta": 0.2, "improved": True},
            "param_accuracy_p50": {"baseline": 0.5, "enhanced": 0.7, "delta": 0.2, "improved": True},
            "bbox_match_rate": {"baseline": 0.4, "enhanced": 0.6, "delta": 0.2, "improved": True},
            "avg_duration_s": {"baseline": 15.0, "enhanced": 25.0, "delta": 10.0, "improved": False},
            "avg_tokens": {"baseline": 1000, "enhanced": 3000, "delta": 2000, "improved": False},
        }
        md = comparison_to_markdown(comparison)
        assert "编译率" in md or "compile_rate" in md
        assert "↑" in md  # improvement arrow
```

### Step 2: Run tests to verify they fail

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_benchmark_comparison.py -v`
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Implement comparison report

**File: `backend/benchmark/comparator.py`**

```python
"""Benchmark comparison — baseline vs enhanced metrics."""

from __future__ import annotations

from .metrics import BenchmarkMetrics

# Metrics where lower is better
_LOWER_IS_BETTER: frozenset[str] = frozenset({"avg_duration_s", "avg_tokens"})

_METRIC_LABELS: dict[str, str] = {
    "compile_rate": "编译率",
    "type_accuracy": "类型准确率",
    "param_accuracy_p50": "参数准确率 (P50)",
    "bbox_match_rate": "几何匹配率",
    "avg_duration_s": "平均耗时",
    "avg_tokens": "平均 Token",
}


def compute_comparison(
    baseline: BenchmarkMetrics,
    enhanced: BenchmarkMetrics,
) -> dict[str, dict]:
    """Compute per-metric comparison between baseline and enhanced runs."""
    result = {}
    for field_name in ["compile_rate", "type_accuracy", "param_accuracy_p50",
                       "bbox_match_rate", "avg_duration_s", "avg_tokens"]:
        b_val = getattr(baseline, field_name)
        e_val = getattr(enhanced, field_name)
        delta = e_val - b_val
        if field_name in _LOWER_IS_BETTER:
            improved = delta < 0
        else:
            improved = delta > 0
        result[field_name] = {
            "baseline": b_val,
            "enhanced": e_val,
            "delta": delta,
            "improved": improved,
        }
    return result


def comparison_to_markdown(comparison: dict[str, dict]) -> str:
    """Generate a Markdown comparison table."""
    lines = [
        "# Phase 2 Benchmark 对比报告\n",
        "| 指标 | Baseline | Enhanced | Delta | |",
        "|------|----------|----------|-------|---|",
    ]
    for key, data in comparison.items():
        label = _METRIC_LABELS.get(key, key)
        b = data["baseline"]
        e = data["enhanced"]
        d = data["delta"]
        arrow = "↑" if data["improved"] else "↓"

        if key in ("compile_rate", "type_accuracy", "param_accuracy_p50", "bbox_match_rate"):
            fmt = lambda v: f"{v:.1%}"
            d_fmt = f"{d:+.1%}"
        elif key == "avg_duration_s":
            fmt = lambda v: f"{v:.1f}s"
            d_fmt = f"{d:+.1f}s"
        else:
            fmt = lambda v: f"{v:.0f}"
            d_fmt = f"{d:+.0f}"

        lines.append(f"| {label} | {fmt(b)} | {fmt(e)} | {d_fmt} | {arrow} |")

    return "\n".join(lines) + "\n"
```

### Step 4: Run tests to verify they pass

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/test_benchmark_comparison.py -v`
Expected: PASS

### Step 5: Update runner to use actual pipeline (integrate TODO)

Modify `backend/benchmark/runner.py:149-171` — replace placeholder `_run_single()` with actual pipeline call:

```python
async def _run_single(self, case: BenchmarkCase, config: PipelineConfig | None = None) -> BenchmarkResult:
    """Run the V2 pipeline on a single benchmark case."""
    start = time.monotonic()
    config = config or PipelineConfig(preset="balanced")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = str(Path(tmpdir) / "output.step")
            generate_step_v2(
                image_filepath=case.drawing_path,
                output_filepath=output_path,
                num_refinements=config.max_refinements,
                config=config,
            )
            # ... evaluate result against expected_spec and expected_bbox
            # ... compute param_accuracy, type_correct, bbox_match
    except Exception as e:
        return BenchmarkResult(
            case_id=case.case_id,
            compiled=False,
            duration_s=time.monotonic() - start,
            failure_category=FailureCategory.CODE_EXECUTION,
            error_detail=str(e),
        )
```

### Step 6: Run all tests

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && pytest tests/ -v`
Expected: All tests PASS

### Step 7: Commit

```bash
git add backend/benchmark/comparator.py backend/benchmark/runner.py tests/test_benchmark_comparison.py
git commit -m "feat: benchmark comparison report (Task 2.7)"
```

---

## Summary — Files Created / Modified

| Task | New Files | Modified Files | Tests |
|------|-----------|---------------|-------|
| T1: AST pre-check + API whitelist | `core/ast_checker.py`, `core/api_whitelist.py` | — | `test_ast_checker.py` |
| T2: Best-of-N + scoring | `core/candidate_scorer.py` | `core/code_generator.py`, `pipeline/pipeline.py` | `test_best_of_n.py` |
| T3: Multi-view render | — | `infra/render.py`, `core/smart_refiner.py` | `test_multi_view_render.py` |
| T4: Rollback | `core/rollback.py` | `pipeline/pipeline.py` | `test_rollback.py` |
| T5: Topology | — | `core/validators.py`, `core/smart_refiner.py` | `test_topology.py` |
| T6: Structured feedback | `core/vl_feedback.py` | `core/smart_refiner.py` | `test_structured_feedback.py` |
| T7: Cross-section | — | `core/validators.py` | `test_cross_section.py` |
| T8: Pipeline integration | — | `pipeline/pipeline.py`, `core/code_generator.py`, `core/smart_refiner.py` | `test_pipeline_integration.py` |
| T9: Benchmark comparison | `benchmark/comparator.py` | `benchmark/runner.py` | `test_benchmark_comparison.py` |

## Task Dependencies

```
T1 (AST + whitelist) ──┐
T2 (Best-of-N) ────────┤
T3 (Multi-view) ────────┤
T4 (Rollback) ──────────┼──→ T8 (Pipeline integration) ──→ T9 (Benchmark comparison)
T5 (Topology) ──────────┤
T6 (Structured VL) ─────┤
T7 (Cross-section) ─────┘
```

T1-T7 可并行开发（无互相依赖），T8 集成所有模块，T9 最后执行对比。

## 域标签分析

- `[backend]`: T1-T9（全部）
- `[test]`: T9

**G2 结论**: 2 个域标签 < 3 → **subagent-driven-development**（不启动 Agent Team）
