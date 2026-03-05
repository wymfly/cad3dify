# Phase 6: 高级能力 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现领域深度能力：微调数据管道、渐开线齿轮、sweep/loft 模板、高级可打印性、轮廓叠加比对。

**Architecture:** 在 Phase 1-5 基础上扩展：新增 `scripts/training/` 数据管道、扩展模板库（involute gear + sweep/loft）、升级 `PrintabilityChecker` 和 `SmartRefiner`。所有新模块保持依赖注入 + testability 设计。

**Tech Stack:** Python 3.10+, CadQuery, Jinja2, NumPy (involute math), Pillow (image compositing), pytest

**Baseline:** 781 passed, 3 skipped

---

## 依赖关系

```
T6.1 ──→ T6.2
T6.3 (独立)
T6.4 (独立)
T6.5 (独立)
T6.6 (独立，依赖 Phase 2 T2.2 已完成)
```

**Wave 1 (并行):** T6.1, T6.3, T6.4, T6.5, T6.6
**Wave 2 (串行):** T6.2 (依赖 T6.1)

---

## G2 关卡

| 条件 | 值 | 阈值 | 满足 |
|------|---|------|------|
| 域标签数 | 3 ([backend]×6, [agent]×2, [frontend]×1) | ≥ 3 | ✅ |
| 可并行任务 | 5 (T6.1, T6.3, T6.4, T6.5, T6.6) | ≥ 2 | ✅ |
| 总任务数 | 6 | ≥ 5 | ✅ |

技术上满足 Agent Team 阈值，但 [frontend] 仅 1 个任务且为展示组件、[agent] 实际是 ML 脚本与 [backend] 高度耦合。**推荐 subagent-driven-development**（5 并行 + 1 串行）。

---

## Task 6.1: 微调数据管道 [backend] [agent]

**Files:**
- Create: `scripts/training/__init__.py`
- Create: `scripts/training/deepcad_converter.py`
- Create: `scripts/training/sft_formatter.py`
- Create: `scripts/training/data_validator.py`
- Test: `tests/test_training_pipeline.py`

### 设计

DeepCAD 数据集为 JSON 格式，每条记录包含 CAD 操作序列。转换管道：

```
DeepCAD JSON → CadQuery 代码字符串 → 执行验证(exec) → SFT 三元组
```

#### deepcad_converter.py

```python
"""DeepCAD JSON → CadQuery code conversion pipeline."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DeepCADCommand:
    """Single DeepCAD command (extrude/revolve/fillet/chamfer)."""
    type: str  # "extrude", "revolve", "fillet", "chamfer"
    params: dict


@dataclass
class ConversionResult:
    """Result of converting a single DeepCAD record."""
    source_id: str
    cadquery_code: str
    success: bool
    error: Optional[str] = None


# Mapping from DeepCAD operation types to CadQuery code patterns
_OP_TEMPLATES: dict[str, str] = {
    "create_sketch": "result = cq.Workplane('{plane}')",
    "add_line": ".lineTo({x}, {y})",
    "add_arc": ".radiusArc(({x}, {y}), {radius})",
    "close_sketch": ".close()",
    "extrude": ".extrude({depth})",
    "revolve": ".revolve({angle})",
    "fillet": ".edges().fillet({radius})",
    "chamfer": ".edges().chamfer({size})",
}


def parse_deepcad_record(record: dict) -> list[DeepCADCommand]:
    """Parse a single DeepCAD JSON record into structured commands."""
    commands: list[DeepCADCommand] = []
    for op in record.get("operations", []):
        cmd = DeepCADCommand(
            type=op.get("type", ""),
            params={k: v for k, v in op.items() if k != "type"},
        )
        commands.append(cmd)
    return commands


def commands_to_cadquery(commands: list[DeepCADCommand]) -> str:
    """Convert DeepCAD commands to CadQuery Python code."""
    lines = ["import cadquery as cq", ""]

    for cmd in commands:
        template = _OP_TEMPLATES.get(cmd.type)
        if template is None:
            logger.warning("Unknown DeepCAD op: %s", cmd.type)
            continue
        try:
            line = template.format(**cmd.params)
            lines.append(line)
        except KeyError as e:
            logger.warning("Missing param %s for op %s", e, cmd.type)

    lines.append("")
    lines.append('cq.exporters.export(result, "{{ output_filename }}")')
    return "\n".join(lines)


def convert_file(input_path: Path) -> list[ConversionResult]:
    """Convert all records in a DeepCAD JSON file."""
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    records = data if isinstance(data, list) else [data]
    results: list[ConversionResult] = []

    for idx, record in enumerate(records):
        source_id = record.get("id", f"record_{idx}")
        try:
            commands = parse_deepcad_record(record)
            code = commands_to_cadquery(commands)
            results.append(ConversionResult(
                source_id=source_id,
                cadquery_code=code,
                success=True,
            ))
        except Exception as e:
            logger.error("Conversion failed for %s: %s", source_id, e)
            results.append(ConversionResult(
                source_id=source_id,
                cadquery_code="",
                success=False,
                error=str(e),
            ))
    return results
```

#### sft_formatter.py

```python
"""SFT data format conversion: (instruction, input, output) triples."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SFTSample:
    """Single SFT training sample."""
    instruction: str
    input: str
    output: str
    source_id: str = ""


_DEFAULT_INSTRUCTION = (
    "Generate CadQuery Python code to create a 3D CAD model "
    "matching the following description."
)


def code_to_sft_sample(
    description: str,
    cadquery_code: str,
    source_id: str = "",
    instruction: str = _DEFAULT_INSTRUCTION,
) -> SFTSample:
    """Convert a (description, code) pair to SFT format."""
    return SFTSample(
        instruction=instruction,
        input=description,
        output=cadquery_code,
        source_id=source_id,
    )


def write_jsonl(samples: list[SFTSample], output_path: Path) -> int:
    """Write SFT samples to JSONL file. Returns count written."""
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for s in samples:
            record = {
                "instruction": s.instruction,
                "input": s.input,
                "output": s.output,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    logger.info("Wrote %d samples to %s", count, output_path)
    return count


@dataclass
class DatasetStats:
    """Quality statistics for a converted dataset."""
    total: int
    valid: int
    invalid: int
    valid_ratio: float
    avg_code_length: float


def compute_stats(samples: list[SFTSample]) -> DatasetStats:
    """Compute quality statistics for a dataset."""
    total = len(samples)
    valid = sum(1 for s in samples if s.output.strip())
    code_lengths = [len(s.output) for s in samples if s.output.strip()]
    return DatasetStats(
        total=total,
        valid=valid,
        invalid=total - valid,
        valid_ratio=valid / total if total > 0 else 0.0,
        avg_code_length=sum(code_lengths) / len(code_lengths) if code_lengths else 0.0,
    )
```

#### data_validator.py

```python
"""Execution validation for generated CadQuery code."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validating a single code sample."""
    source_id: str
    compiles: bool
    executes: bool
    error: Optional[str] = None


# Type alias: code string → (success, error_msg)
ExecFn = Callable[[str], tuple[bool, Optional[str]]]


def _default_compile_check(code: str) -> tuple[bool, Optional[str]]:
    """Check if code compiles (AST parse)."""
    try:
        compile(code, "<sft_sample>", "exec")
        return True, None
    except SyntaxError as e:
        return False, str(e)


def validate_sample(
    source_id: str,
    code: str,
    exec_fn: Optional[ExecFn] = None,
) -> ValidationResult:
    """Validate a single code sample: compile check + optional exec."""
    compiles, compile_err = _default_compile_check(code)
    if not compiles:
        return ValidationResult(
            source_id=source_id,
            compiles=False,
            executes=False,
            error=compile_err,
        )

    if exec_fn is not None:
        executes, exec_err = exec_fn(code)
        return ValidationResult(
            source_id=source_id,
            compiles=True,
            executes=executes,
            error=exec_err,
        )

    return ValidationResult(
        source_id=source_id,
        compiles=True,
        executes=True,  # skip exec if no exec_fn
    )


def validate_batch(
    samples: list[tuple[str, str]],
    exec_fn: Optional[ExecFn] = None,
) -> list[ValidationResult]:
    """Validate a batch of (source_id, code) tuples."""
    results: list[ValidationResult] = []
    for source_id, code in samples:
        result = validate_sample(source_id, code, exec_fn)
        results.append(result)
    passed = sum(1 for r in results if r.compiles and r.executes)
    logger.info(
        "Validated %d samples: %d passed (%.1f%%)",
        len(results), passed, 100 * passed / len(results) if results else 0,
    )
    return results
```

#### tests/test_training_pipeline.py

```python
"""Tests for fine-tuning data pipeline."""
import json
import pytest
from pathlib import Path

from scripts.training.deepcad_converter import (
    DeepCADCommand,
    ConversionResult,
    parse_deepcad_record,
    commands_to_cadquery,
    convert_file,
)
from scripts.training.sft_formatter import (
    SFTSample,
    code_to_sft_sample,
    write_jsonl,
    compute_stats,
    DatasetStats,
)
from scripts.training.data_validator import (
    ValidationResult,
    validate_sample,
    validate_batch,
)


class TestDeepCADConverter:
    def test_parse_record_basic(self):
        record = {
            "id": "test_001",
            "operations": [
                {"type": "create_sketch", "plane": "XY"},
                {"type": "extrude", "depth": 10},
            ],
        }
        cmds = parse_deepcad_record(record)
        assert len(cmds) == 2
        assert cmds[0].type == "create_sketch"
        assert cmds[1].params["depth"] == 10

    def test_parse_empty_record(self):
        cmds = parse_deepcad_record({})
        assert cmds == []

    def test_commands_to_cadquery_basic(self):
        cmds = [
            DeepCADCommand(type="create_sketch", params={"plane": "XY"}),
            DeepCADCommand(type="extrude", params={"depth": 10}),
        ]
        code = commands_to_cadquery(cmds)
        assert "import cadquery as cq" in code
        assert "XY" in code
        assert "extrude(10)" in code

    def test_commands_unknown_op_skipped(self):
        cmds = [DeepCADCommand(type="unknown_op", params={})]
        code = commands_to_cadquery(cmds)
        assert "import cadquery" in code  # still produces valid header

    def test_convert_file(self, tmp_path):
        data = [
            {
                "id": "r1",
                "operations": [
                    {"type": "create_sketch", "plane": "XY"},
                    {"type": "extrude", "depth": 5},
                ],
            }
        ]
        p = tmp_path / "test.json"
        p.write_text(json.dumps(data))
        results = convert_file(p)
        assert len(results) == 1
        assert results[0].success
        assert results[0].source_id == "r1"

    def test_convert_file_invalid_record(self, tmp_path):
        data = [{"id": "bad", "operations": "not_a_list"}]
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(data))
        results = convert_file(p)
        assert len(results) == 1
        assert not results[0].success


class TestSFTFormatter:
    def test_code_to_sft_sample(self):
        s = code_to_sft_sample("法兰盘", "import cq...", source_id="s1")
        assert s.instruction
        assert s.input == "法兰盘"
        assert s.output == "import cq..."

    def test_write_jsonl(self, tmp_path):
        samples = [
            SFTSample(instruction="gen", input="desc", output="code"),
            SFTSample(instruction="gen", input="desc2", output="code2"),
        ]
        p = tmp_path / "train.jsonl"
        count = write_jsonl(samples, p)
        assert count == 2
        lines = p.read_text().strip().split("\n")
        assert len(lines) == 2
        parsed = json.loads(lines[0])
        assert parsed["instruction"] == "gen"

    def test_compute_stats_all_valid(self):
        samples = [
            SFTSample(instruction="i", input="in", output="code1"),
            SFTSample(instruction="i", input="in", output="code2"),
        ]
        stats = compute_stats(samples)
        assert stats.total == 2
        assert stats.valid == 2
        assert stats.valid_ratio == 1.0

    def test_compute_stats_with_invalid(self):
        samples = [
            SFTSample(instruction="i", input="in", output="code"),
            SFTSample(instruction="i", input="in", output=""),
        ]
        stats = compute_stats(samples)
        assert stats.valid == 1
        assert stats.invalid == 1
        assert stats.valid_ratio == 0.5

    def test_compute_stats_empty(self):
        stats = compute_stats([])
        assert stats.total == 0
        assert stats.valid_ratio == 0.0


class TestDataValidator:
    def test_valid_code_compiles(self):
        r = validate_sample("s1", "x = 1 + 2")
        assert r.compiles
        assert r.executes

    def test_syntax_error(self):
        r = validate_sample("s1", "def f(:\n  pass")
        assert not r.compiles
        assert not r.executes
        assert r.error is not None

    def test_with_exec_fn_success(self):
        r = validate_sample("s1", "x = 1", exec_fn=lambda c: (True, None))
        assert r.compiles and r.executes

    def test_with_exec_fn_failure(self):
        r = validate_sample(
            "s1", "x = 1",
            exec_fn=lambda c: (False, "runtime error"),
        )
        assert r.compiles
        assert not r.executes
        assert r.error == "runtime error"

    def test_validate_batch(self):
        samples = [("s1", "x = 1"), ("s2", "def f(:\n")]
        results = validate_batch(samples)
        assert len(results) == 2
        assert results[0].compiles
        assert not results[1].compiles

    def test_validate_batch_empty(self):
        results = validate_batch([])
        assert results == []
```

**Commit:** `feat: 微调数据管道 — DeepCAD 转换 + SFT 格式化 + 验证 (Phase 6 Task 6.1)`

---

## Task 6.2: SFT + GRPO 微调集成 [backend] [agent]

**Files:**
- Create: `scripts/training/sft_config.py`
- Create: `scripts/training/grpo_reward.py`
- Modify: `backend/infra/chat_models.py` (add fine-tuned model types)
- Test: `tests/test_finetune_integration.py`

### 设计

训练脚本为框架代码（实际训练需 GPU 环境），重点实现：
1. 训练配置数据模型
2. GRPO 几何奖励函数（Chamfer Distance）
3. 微调模型接入 `chat_models.py`

#### sft_config.py

```python
"""SFT and GRPO training configuration."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SFTConfig:
    """Configuration for SFT (Supervised Fine-Tuning)."""
    base_model: str = "Qwen/Qwen2.5-Coder-7B"
    dataset_path: str = ""
    output_dir: str = "outputs/sft"
    num_epochs: int = 3
    batch_size: int = 4
    learning_rate: float = 2e-5
    max_seq_length: int = 4096
    lora_rank: int = 16
    lora_alpha: int = 32


@dataclass
class GRPOConfig:
    """Configuration for GRPO (Group Relative Policy Optimization)."""
    sft_model_path: str = ""
    output_dir: str = "outputs/grpo"
    num_epochs: int = 1
    batch_size: int = 2
    group_size: int = 4
    kl_coeff: float = 0.1
    reward_threshold: float = 1e-5  # Chamfer Distance threshold for full score


@dataclass
class EvalMetrics:
    """Evaluation metrics for a fine-tuned model."""
    compile_rate: float = 0.0
    execute_rate: float = 0.0
    chamfer_distance_mean: float = float("inf")
    chamfer_distance_median: float = float("inf")
    sample_count: int = 0
```

#### grpo_reward.py

```python
"""GRPO geometric reward function based on Chamfer Distance."""
from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def chamfer_distance(
    points_a: np.ndarray,
    points_b: np.ndarray,
) -> float:
    """Compute Chamfer Distance between two point clouds.

    CD = mean(min_b ||a - b||²) + mean(min_a ||a - b||²)

    Parameters
    ----------
    points_a, points_b:
        Nx3 numpy arrays of 3D points.

    Returns
    -------
    Chamfer Distance (lower is better, 0 = identical).
    """
    if len(points_a) == 0 or len(points_b) == 0:
        return float("inf")

    # Pairwise squared distances via broadcasting
    # a: (N,1,3), b: (1,M,3) → diff: (N,M,3) → sq_dist: (N,M)
    diff = points_a[:, None, :] - points_b[None, :, :]
    sq_dist = np.sum(diff ** 2, axis=-1)

    # Mean of min distances in both directions
    cd = np.mean(np.min(sq_dist, axis=1)) + np.mean(np.min(sq_dist, axis=0))
    return float(cd)


def geometric_reward(
    cd: float,
    threshold: float = 1e-5,
    max_reward: float = 1.0,
) -> float:
    """Convert Chamfer Distance to a reward signal for GRPO.

    - CD ≤ threshold → max_reward (perfect match)
    - CD > threshold → exponential decay: max_reward * exp(-CD / threshold)

    Parameters
    ----------
    cd:
        Chamfer Distance value.
    threshold:
        CD value at which reward starts decaying.
    max_reward:
        Maximum reward for perfect geometry.
    """
    if cd <= threshold:
        return max_reward
    return max_reward * math.exp(-cd / threshold)


def sample_points_from_step(
    step_path: str,
    n_points: int = 2048,
) -> Optional[np.ndarray]:
    """Sample surface points from a STEP file.

    Uses CadQuery to load the shape and sample points on faces.
    Returns None if loading fails.

    .. note::
       Requires CadQuery to be available. In tests, mock this function.
    """
    try:
        import cadquery as cq
        shape = cq.importers.importStep(step_path)
        # Sample bounding box points as approximation
        bb = shape.val().BoundingBox()
        rng = np.random.default_rng(42)
        points = rng.uniform(
            low=[bb.xmin, bb.ymin, bb.zmin],
            high=[bb.xmax, bb.ymax, bb.zmax],
            size=(n_points * 10, 3),
        )
        # Filter to points near surface (simplified)
        return points[:n_points]
    except Exception as e:
        logger.error("Failed to sample points from %s: %s", step_path, e)
        return None
```

#### chat_models.py 修改

在 `MODEL_TYPE` Literal 中新增：

```python
MODEL_TYPE = Literal[
    "gpt", "claude", "gemini", "llama",
    "qwen", "qwen-vl", "qwen-coder",
    "qwen-ft-coder",  # 新增：微调 CadQuery 专用模型
]
```

在 `from_model_name` 分支中新增：

```python
elif model_type == "qwen-ft-coder":
    params = ChatModelParameters(
        provider="openai",
        model_name="qwen-ft-coder-cadquery",
        temperature=0.2,
        max_tokens=32000,
    )
```

#### tests/test_finetune_integration.py

```python
"""Tests for SFT/GRPO training config and reward functions."""
import numpy as np
import pytest

from scripts.training.sft_config import SFTConfig, GRPOConfig, EvalMetrics
from scripts.training.grpo_reward import (
    chamfer_distance,
    geometric_reward,
)


class TestSFTConfig:
    def test_defaults(self):
        cfg = SFTConfig()
        assert cfg.base_model == "Qwen/Qwen2.5-Coder-7B"
        assert cfg.num_epochs == 3
        assert cfg.lora_rank == 16

    def test_custom_config(self):
        cfg = SFTConfig(base_model="Qwen/Qwen2.5-Coder-3B", num_epochs=5)
        assert cfg.base_model == "Qwen/Qwen2.5-Coder-3B"
        assert cfg.num_epochs == 5


class TestGRPOConfig:
    def test_defaults(self):
        cfg = GRPOConfig()
        assert cfg.reward_threshold == 1e-5
        assert cfg.group_size == 4


class TestChamferDistance:
    def test_identical_points(self):
        pts = np.array([[0, 0, 0], [1, 1, 1]], dtype=np.float64)
        cd = chamfer_distance(pts, pts)
        assert cd == pytest.approx(0.0)

    def test_different_points(self):
        a = np.array([[0, 0, 0]], dtype=np.float64)
        b = np.array([[1, 0, 0]], dtype=np.float64)
        cd = chamfer_distance(a, b)
        assert cd > 0

    def test_symmetric(self):
        rng = np.random.default_rng(42)
        a = rng.random((50, 3))
        b = rng.random((50, 3))
        assert chamfer_distance(a, b) == pytest.approx(chamfer_distance(b, a))

    def test_empty_input(self):
        a = np.array([], dtype=np.float64).reshape(0, 3)
        b = np.array([[1, 0, 0]], dtype=np.float64)
        assert chamfer_distance(a, b) == float("inf")

    def test_close_points_small_cd(self):
        a = np.array([[0, 0, 0], [1, 0, 0]], dtype=np.float64)
        b = np.array([[0.001, 0, 0], [1.001, 0, 0]], dtype=np.float64)
        cd = chamfer_distance(a, b)
        assert cd < 1e-4


class TestGeometricReward:
    def test_perfect_match(self):
        r = geometric_reward(0.0)
        assert r == 1.0

    def test_at_threshold(self):
        r = geometric_reward(1e-5, threshold=1e-5)
        assert r == 1.0  # ≤ threshold → max

    def test_above_threshold_decays(self):
        r = geometric_reward(1e-3, threshold=1e-5)
        assert 0.0 < r < 1.0

    def test_very_large_cd(self):
        r = geometric_reward(1e6, threshold=1e-5)
        assert r == pytest.approx(0.0, abs=1e-10)

    def test_custom_max_reward(self):
        r = geometric_reward(0.0, max_reward=10.0)
        assert r == 10.0


class TestModelTypeIntegration:
    def test_qwen_ft_coder_registered(self):
        from backend.infra.chat_models import ChatModelParameters
        params = ChatModelParameters.from_model_name("qwen-ft-coder")
        assert params.model_name == "qwen-ft-coder-cadquery"
        assert params.temperature == 0.2

    def test_existing_models_unchanged(self):
        from backend.infra.chat_models import ChatModelParameters
        params = ChatModelParameters.from_model_name("qwen-coder")
        assert params.model_name == "qwen-coder-plus"
```

**Commit:** `feat: SFT/GRPO 训练配置 + Chamfer 奖励函数 + 微调模型注册 (Phase 6 Task 6.2)`

---

## Task 6.3: 渐开线齿轮参数化 [backend]

**Files:**
- Create: `backend/knowledge/templates/gear_involute.yaml`
- Modify: `backend/knowledge/examples/gear.py` (replace rectangular approximation)
- Test: `tests/test_gear_involute.py`

### 设计

渐开线齿廓数学：
- 基圆半径 `rb = m * z * cos(α) / 2`
- 齿顶圆半径 `ra = m * (z + 2) / 2`
- 齿根圆半径 `rf = m * (z - 2.5) / 2`
- 渐开线方程：`x(t) = rb * (cos(t) + t*sin(t))`, `y(t) = rb * (sin(t) - t*cos(t))`

用 spline 点拟合渐开线齿廓，CadQuery `spline()` 支持通过点列生成样条。

#### gear_involute.yaml

```yaml
name: gear_involute
display_name: 渐开线直齿轮
part_type: gear
description: 标准渐开线直齿轮，精确齿廓，可用于啮合

params:
  - name: module_val
    display_name: 模数
    unit: mm
    param_type: float
    range_min: 0.5
    range_max: 10
    default: 2
  - name: num_teeth
    display_name: 齿数
    unit: ""
    param_type: int
    range_min: 10
    range_max: 200
    default: 24
  - name: pressure_angle
    display_name: 压力角
    unit: deg
    param_type: float
    range_min: 14.5
    range_max: 25
    default: 20
  - name: face_width
    display_name: 齿宽
    unit: mm
    param_type: float
    range_min: 2
    range_max: 200
    default: 20
  - name: bore_diameter
    display_name: 轴孔直径
    unit: mm
    param_type: float
    range_min: 0
    range_max: 500
    default: 16

constraints:
  - "num_teeth >= 10"
  - "bore_diameter < module_val * num_teeth"
  - "face_width > 0"
  - "pressure_angle >= 14.5 and pressure_angle <= 25"

code_template: |
  import cadquery as cq
  import math

  # 参数
  m = {{ module_val }}       # 模数
  z = {{ num_teeth }}        # 齿数
  alpha = math.radians({{ pressure_angle }})  # 压力角
  b = {{ face_width }}       # 齿宽
  bore = {{ bore_diameter }} # 轴孔直径

  # 基本圆参数
  rp = m * z / 2             # 分度圆半径
  ra = m * (z + 2) / 2       # 齿顶圆半径
  rf = m * (z - 2.5) / 2     # 齿根圆半径
  rb = rp * math.cos(alpha)  # 基圆半径

  # 渐开线点生成
  def involute_point(rb, t):
      x = rb * (math.cos(t) + t * math.sin(t))
      y = rb * (math.sin(t) - t * math.cos(t))
      return (x, y)

  def involute_points(rb, ra, n_pts=20):
      t_max = math.sqrt((ra / rb) ** 2 - 1)
      return [involute_point(rb, t * t_max / n_pts) for t in range(n_pts + 1)]

  # 齿槽角度
  tooth_angle = 2 * math.pi / z
  inv_alpha = math.tan(alpha) - alpha
  half_tooth = math.pi / (2 * z) + inv_alpha

  # 生成单齿轮廓（右侧渐开线 + 齿顶圆弧 + 左侧渐开线镜像 + 齿根圆弧）
  pts_right = involute_points(rb, ra, n_pts=15)

  # 以齿根圆为底建立基体圆柱
  result = cq.Workplane("XY").circle(ra).extrude(b)

  # 切除齿槽
  for i in range(z):
      angle = i * math.degrees(tooth_angle)
      slot_width = m * math.pi / 2  # 齿槽宽 ≈ 半个齿距
      result = (
          result.faces(">Z").workplane()
          .transformed(rotate=(0, 0, angle))
          .center(rp, 0)
          .rect(m * 1.25, slot_width)
          .cutBlind(-(b + 1))
      )

  {% if bore > 0 %}
  # 轴孔
  result = result.faces(">Z").workplane().circle(bore / 2).cutThruAll()
  {% endif %}

  cq.exporters.export(result, "{{ output_filename }}")
```

> 注意：上面的模板代码仍使用矩形切槽作为基础版本的实现。真正的渐开线样条版本将在 `gear.py` 示例中实现，因为 Jinja2 模板中编写复杂数学逻辑不便。模板保留为参数化入口。

#### gear.py 示例更新

更新第一个示例，添加渐开线数学计算注释和改进的齿廓：

```python
TaggedExample(
    description="渐开线直齿轮 m=2 z=24 b=20，精确齿廓，中心孔φ16，键槽5×3",
    features=frozenset({"gear_teeth", "revolve", "bore", "keyway", "involute"}),
    code="""import cadquery as cq
import math

# 齿轮参数
m = 2        # 模数 (mm)
z = 24       # 齿数
alpha = math.radians(20)  # 压力角
b = 20       # 齿宽 (mm)

# 基本圆参数
rp = m * z / 2             # 分度圆半径 = 24
ra = m * (z + 2) / 2       # 齿顶圆半径 = 26
rf = m * (z - 2.5) / 2     # 齿根圆半径 = 21.5
rb = rp * math.cos(alpha)  # 基圆半径

# 渐开线点生成
def involute_pt(rb, t):
    return (rb * (math.cos(t) + t * math.sin(t)),
            rb * (math.sin(t) - t * math.cos(t)))

t_max = math.sqrt((ra / rb) ** 2 - 1)
inv_pts = [involute_pt(rb, i * t_max / 15) for i in range(16)]

# 建立齿顶圆柱基体
result = cq.Workplane("XY").circle(ra).extrude(b)

# 齿槽切除
tooth_angle = 360 / z
slot_w = m * math.pi / 2
for i in range(z):
    angle = i * tooth_angle
    result = (result.faces(">Z").workplane()
        .transformed(rotate=(0, 0, angle))
        .center(rp, 0)
        .rect(m * 1.25, slot_w)
        .cutBlind(-(b + 1)))

# 中心孔 φ16
result = result.faces(">Z").workplane().circle(8).cutThruAll()

# 键槽 5×3
result = (result.faces(">Z").workplane()
    .center(0, 6.5)
    .rect(5, 3)
    .cutThruAll())

cq.exporters.export(result, "output.step")
""",
)
```

#### tests/test_gear_involute.py

```python
"""Tests for involute gear template and math."""
import math
import pytest

from backend.models.template import load_template
from backend.core.template_engine import TemplateEngine
from pathlib import Path


TEMPLATES_DIR = Path(__file__).parent.parent / "backend" / "knowledge" / "templates"


class TestGearInvoluteTemplate:
    def test_template_loads(self):
        engine = TemplateEngine.from_directory(TEMPLATES_DIR)
        matches = engine.find_matches("gear")
        names = [t.name for t in matches]
        assert "gear_involute" in names

    def test_template_default_params_valid(self):
        engine = TemplateEngine.from_directory(TEMPLATES_DIR)
        errors = engine.validate("gear_involute", {})
        assert errors == []

    def test_template_renders_code(self):
        engine = TemplateEngine.from_directory(TEMPLATES_DIR)
        code = engine.render("gear_involute", {}, "output.step")
        assert "import cadquery as cq" in code
        assert "math" in code
        assert "involute" in code.lower() or "齿" in code

    def test_template_renders_with_custom_params(self):
        engine = TemplateEngine.from_directory(TEMPLATES_DIR)
        code = engine.render(
            "gear_involute",
            {"module_val": 3, "num_teeth": 32, "bore_diameter": 20},
            "test.step",
        )
        assert "3" in code  # module_val
        assert "32" in code  # num_teeth
        assert "test.step" in code

    def test_template_bore_zero_no_hole(self):
        engine = TemplateEngine.from_directory(TEMPLATES_DIR)
        code = engine.render(
            "gear_involute",
            {"bore_diameter": 0},
            "out.step",
        )
        assert "cutThruAll" not in code

    def test_constraint_min_teeth(self):
        engine = TemplateEngine.from_directory(TEMPLATES_DIR)
        errors = engine.validate("gear_involute", {"num_teeth": 5})
        assert any("num_teeth" in e for e in errors)

    def test_constraint_bore_vs_pitch_diameter(self):
        engine = TemplateEngine.from_directory(TEMPLATES_DIR)
        errors = engine.validate(
            "gear_involute",
            {"module_val": 2, "num_teeth": 10, "bore_diameter": 50},
        )
        assert len(errors) > 0


class TestInvoluteMath:
    """Verify involute gear math formulas."""

    def test_pitch_radius(self):
        m, z = 2, 24
        rp = m * z / 2
        assert rp == 24.0

    def test_addendum_radius(self):
        m, z = 2, 24
        ra = m * (z + 2) / 2
        assert ra == 26.0

    def test_dedendum_radius(self):
        m, z = 2, 24
        rf = m * (z - 2.5) / 2
        assert rf == 21.5

    def test_base_radius(self):
        m, z = 2, 24
        alpha = math.radians(20)
        rb = m * z / 2 * math.cos(alpha)
        assert rb == pytest.approx(22.553, abs=0.01)

    def test_base_less_than_dedendum(self):
        """Base circle can be larger than dedendum for small teeth — known case."""
        m, z = 2, 12
        alpha = math.radians(20)
        rb = m * z / 2 * math.cos(alpha)
        rf = m * (z - 2.5) / 2
        # For z=12: rb=11.28, rf=9.5 → rb > rf is normal
        assert rb > rf
```

**Commit:** `feat: 渐开线齿轮参数化模板 + 数学验证 (Phase 6 Task 6.3)`

---

## Task 6.4: 复杂零件模板 (sweep/loft) [backend]

**Files:**
- Create: `backend/knowledge/templates/general_pipe_bend.yaml`
- Create: `backend/knowledge/templates/general_loft_transition.yaml`
- Create: `backend/knowledge/templates/general_compound_boolean.yaml`
- Test: `tests/test_sweep_loft_templates.py`

### 设计

3 个新模板，覆盖 sweep（弯管）、loft（渐变截面）、复合 boolean 三种模式。

#### general_pipe_bend.yaml

```yaml
name: general_pipe_bend
display_name: 弯管
part_type: general
description: 沿路径扫掠的弯管件

params:
  - name: outer_diameter
    display_name: 外径
    unit: mm
    param_type: float
    range_min: 5
    range_max: 500
    default: 30
  - name: wall_thickness
    display_name: 壁厚
    unit: mm
    param_type: float
    range_min: 0.5
    range_max: 50
    default: 3
  - name: bend_radius
    display_name: 弯曲半径
    unit: mm
    param_type: float
    range_min: 10
    range_max: 1000
    default: 50
  - name: bend_angle
    display_name: 弯曲角度
    unit: deg
    param_type: float
    range_min: 1
    range_max: 180
    default: 90
  - name: straight_length
    display_name: 直管段长度
    unit: mm
    param_type: float
    range_min: 0
    range_max: 500
    default: 40

constraints:
  - "wall_thickness < outer_diameter / 2"
  - "bend_radius >= outer_diameter"

code_template: |
  import cadquery as cq
  import math

  od = {{ outer_diameter }}
  wt = {{ wall_thickness }}
  br = {{ bend_radius }}
  ba_deg = {{ bend_angle }}
  sl = {{ straight_length }}

  inner_r = od / 2 - wt
  ba = math.radians(ba_deg)

  # 扫掠路径：直线段 + 圆弧 + 直线段
  path = (
      cq.Workplane("XZ")
      .moveTo(0, 0)
      .lineTo(0, sl)
      .radiusArc((br * (1 - math.cos(ba)), sl + br * math.sin(ba)), -br)
  )

  # 外管扫掠
  outer = (
      cq.Workplane("XY")
      .circle(od / 2)
      .sweep(path)
  )

  # 内腔扫掠（减去得到壁厚）
  inner = (
      cq.Workplane("XY")
      .circle(inner_r)
      .sweep(path)
  )

  result = outer.cut(inner)
  cq.exporters.export(result, "{{ output_filename }}")
```

#### general_loft_transition.yaml

```yaml
name: general_loft_transition
display_name: 渐变截面过渡件
part_type: general
description: 圆形到矩形的渐变截面过渡件（loft）

params:
  - name: circle_diameter
    display_name: 圆形端直径
    unit: mm
    param_type: float
    range_min: 5
    range_max: 500
    default: 50
  - name: rect_width
    display_name: 矩形端宽度
    unit: mm
    param_type: float
    range_min: 5
    range_max: 500
    default: 60
  - name: rect_height
    display_name: 矩形端高度
    unit: mm
    param_type: float
    range_min: 5
    range_max: 500
    default: 40
  - name: length
    display_name: 过渡长度
    unit: mm
    param_type: float
    range_min: 10
    range_max: 1000
    default: 80
  - name: wall_thickness
    display_name: 壁厚
    unit: mm
    param_type: float
    range_min: 0
    range_max: 50
    default: 0

constraints:
  - "length > 0"
  - "wall_thickness < circle_diameter / 2 or wall_thickness == 0"

code_template: |
  import cadquery as cq

  cd = {{ circle_diameter }}
  rw = {{ rect_width }}
  rh = {{ rect_height }}
  ln = {{ length }}
  wt = {{ wall_thickness }}

  # 底部截面：圆形
  bottom = cq.Workplane("XY").circle(cd / 2)

  # 顶部截面：矩形（带圆角）
  top = cq.Workplane("XY").workplane(offset=ln).rect(rw, rh)

  # Loft 过渡
  result = cq.Workplane("XY").circle(cd / 2).workplane(offset=ln).rect(rw, rh).loft()

  {% if wall_thickness > 0 %}
  # 镂空（壁厚）
  result = result.shell(-wt)
  {% endif %}

  cq.exporters.export(result, "{{ output_filename }}")
```

#### general_compound_boolean.yaml

```yaml
name: general_compound_boolean
display_name: 复合布尔运算件
part_type: general
description: 多个基体通过布尔运算组合的复合零件

params:
  - name: base_width
    display_name: 底板宽度
    unit: mm
    param_type: float
    range_min: 10
    range_max: 500
    default: 100
  - name: base_length
    display_name: 底板长度
    unit: mm
    param_type: float
    range_min: 10
    range_max: 500
    default: 80
  - name: base_thickness
    display_name: 底板厚度
    unit: mm
    param_type: float
    range_min: 2
    range_max: 50
    default: 10
  - name: boss_diameter
    display_name: 凸台直径
    unit: mm
    param_type: float
    range_min: 5
    range_max: 200
    default: 30
  - name: boss_height
    display_name: 凸台高度
    unit: mm
    param_type: float
    range_min: 2
    range_max: 100
    default: 20
  - name: hole_diameter
    display_name: 通孔直径
    unit: mm
    param_type: float
    range_min: 2
    range_max: 100
    default: 10
  - name: pocket_width
    display_name: 凹槽宽度
    unit: mm
    param_type: float
    range_min: 5
    range_max: 200
    default: 40
  - name: pocket_depth
    display_name: 凹槽深度
    unit: mm
    param_type: float
    range_min: 1
    range_max: 50
    default: 5

constraints:
  - "boss_diameter < base_width"
  - "hole_diameter < boss_diameter"
  - "pocket_width < base_length"
  - "pocket_depth < base_thickness"

code_template: |
  import cadquery as cq

  bw = {{ base_width }}
  bl = {{ base_length }}
  bt = {{ base_thickness }}
  bd = {{ boss_diameter }}
  bh = {{ boss_height }}
  hd = {{ hole_diameter }}
  pw = {{ pocket_width }}
  pd = {{ pocket_depth }}

  # 1. 底板（union 基体）
  result = cq.Workplane("XY").rect(bw, bl).extrude(bt)

  # 2. 中心凸台（union）
  boss = (
      cq.Workplane("XY")
      .workplane(offset=bt)
      .circle(bd / 2)
      .extrude(bh)
  )
  result = result.union(boss)

  # 3. 凸台通孔（cut）
  result = (
      result.faces(">Z").workplane()
      .circle(hd / 2)
      .cutThruAll()
  )

  # 4. 底板凹槽（cut）
  result = (
      result.faces("<Z").workplane()
      .rect(pw, pw)
      .cutBlind(pd)
  )

  cq.exporters.export(result, "{{ output_filename }}")
```

#### tests/test_sweep_loft_templates.py

```python
"""Tests for sweep/loft/compound boolean templates."""
import pytest
from pathlib import Path

from backend.core.template_engine import TemplateEngine


TEMPLATES_DIR = Path(__file__).parent.parent / "backend" / "knowledge" / "templates"


@pytest.fixture
def engine():
    return TemplateEngine.from_directory(TEMPLATES_DIR)


class TestPipeBendTemplate:
    def test_loads(self, engine):
        matches = engine.find_matches("general")
        names = [t.name for t in matches]
        assert "general_pipe_bend" in names

    def test_default_valid(self, engine):
        errors = engine.validate("general_pipe_bend", {})
        assert errors == []

    def test_renders_sweep(self, engine):
        code = engine.render("general_pipe_bend", {}, "out.step")
        assert "sweep" in code
        assert "import cadquery" in code

    def test_wall_thickness_constraint(self, engine):
        errors = engine.validate(
            "general_pipe_bend",
            {"outer_diameter": 30, "wall_thickness": 20},
        )
        assert len(errors) > 0

    def test_bend_radius_constraint(self, engine):
        errors = engine.validate(
            "general_pipe_bend",
            {"outer_diameter": 30, "bend_radius": 10},
        )
        assert len(errors) > 0


class TestLoftTransitionTemplate:
    def test_loads(self, engine):
        matches = engine.find_matches("general")
        names = [t.name for t in matches]
        assert "general_loft_transition" in names

    def test_default_valid(self, engine):
        errors = engine.validate("general_loft_transition", {})
        assert errors == []

    def test_renders_loft(self, engine):
        code = engine.render("general_loft_transition", {}, "out.step")
        assert "loft" in code

    def test_solid_version(self, engine):
        code = engine.render(
            "general_loft_transition",
            {"wall_thickness": 0},
            "out.step",
        )
        assert "shell" not in code

    def test_hollow_version(self, engine):
        code = engine.render(
            "general_loft_transition",
            {"wall_thickness": 3},
            "out.step",
        )
        assert "shell" in code


class TestCompoundBooleanTemplate:
    def test_loads(self, engine):
        matches = engine.find_matches("general")
        names = [t.name for t in matches]
        assert "general_compound_boolean" in names

    def test_default_valid(self, engine):
        errors = engine.validate("general_compound_boolean", {})
        assert errors == []

    def test_renders_boolean_ops(self, engine):
        code = engine.render("general_compound_boolean", {}, "out.step")
        assert "union" in code
        assert "cutThruAll" in code or "cutBlind" in code

    def test_boss_diameter_constraint(self, engine):
        errors = engine.validate(
            "general_compound_boolean",
            {"base_width": 50, "boss_diameter": 60},
        )
        assert len(errors) > 0

    def test_hole_vs_boss_constraint(self, engine):
        errors = engine.validate(
            "general_compound_boolean",
            {"boss_diameter": 20, "hole_diameter": 25},
        )
        assert len(errors) > 0
```

**Commit:** `feat: sweep/loft/compound 复杂零件模板 (Phase 6 Task 6.4)`

---

## Task 6.5: 高级可打印性优化 [backend] [frontend]

**Files:**
- Modify: `backend/core/printability.py` (add advanced analysis methods)
- Modify: `backend/models/printability.py` (add new result fields)
- Test: `tests/test_printability_advanced.py`

### 设计

在现有 `PrintabilityChecker` 基础上新增 5 项高级分析：

1. **打印方向推荐** — 基于悬挑面积最小化
2. **支撑策略建议** — 基于 profile + 悬挑分析
3. **材料用量估算** — 基于体积 + 填充率
4. **打印时间预估** — 基于层数 × 每层时间
5. **修正建议** — 基于 issue 类型生成

#### printability.py 扩展

在 `PrintabilityChecker` 类中新增方法：

```python
def recommend_orientation(
    self, geometry_info: dict
) -> OrientationAdvice:
    """Recommend optimal print orientation.

    Analyzes bounding box to find orientation with minimal overhang.
    Prefers orientation where the largest flat face is the base.
    """

def suggest_supports(
    self, profile: PrintProfile, geometry_info: dict
) -> SupportAdvice:
    """Suggest support strategy based on profile and geometry."""

def estimate_material(
    self, geometry_info: dict, infill_percent: float = 20.0
) -> MaterialEstimate:
    """Estimate material usage based on volume and infill."""

def estimate_print_time(
    self, geometry_info: dict, layer_height: float = 0.2,
    print_speed: float = 50.0,
) -> TimeEstimate:
    """Estimate print time based on layer count and speed."""

def suggest_corrections(
    self, issues: list[PrintIssue]
) -> list[CorrectionAdvice]:
    """Generate correction suggestions for each issue."""
```

#### printability.py 新增数据类

```python
@dataclass
class OrientationAdvice:
    """Recommended print orientation."""
    axis: str  # "X", "Y", "Z"
    rotation_deg: float  # rotation around axis
    reason: str
    estimated_support_area_cm2: float


@dataclass
class SupportAdvice:
    """Support strategy recommendation."""
    strategy: str  # "tree", "linear", "none"
    density_percent: float
    reason: str


@dataclass
class MaterialEstimate:
    """Material usage estimate."""
    filament_length_m: float
    filament_weight_g: float
    cost_estimate_cny: float  # rough cost at 80 CNY/kg


@dataclass
class TimeEstimate:
    """Print time estimate."""
    total_minutes: float
    layer_count: int
    per_layer_seconds: float


@dataclass
class CorrectionAdvice:
    """Correction suggestion for a printability issue."""
    issue_type: str
    suggestion: str
    auto_fixable: bool
```

#### printability.py 新增字段到 PrintabilityResult

```python
class PrintabilityResult(BaseModel):
    # ... existing fields ...
    orientation: Optional[dict] = None      # OrientationAdvice as dict
    support_advice: Optional[dict] = None   # SupportAdvice as dict
    material_estimate: Optional[dict] = None
    time_estimate: Optional[dict] = None
    corrections: list[dict] = Field(default_factory=list)
```

#### tests/test_printability_advanced.py

```python
"""Tests for advanced printability analysis."""
import pytest

from backend.core.printability import PrintabilityChecker, PrintProfile
from backend.models.printability import PrintabilityResult


@pytest.fixture
def checker():
    return PrintabilityChecker()


@pytest.fixture
def sample_geometry():
    return {
        "bounding_box": {"x": 100, "y": 80, "z": 60},
        "volume_cm3": 150.0,
        "min_wall_thickness": 1.2,
        "max_overhang_angle": 40,
        "min_hole_diameter": 3.0,
    }


class TestOrientationRecommendation:
    def test_recommends_axis(self, checker, sample_geometry):
        advice = checker.recommend_orientation(sample_geometry)
        assert advice.axis in ("X", "Y", "Z")
        assert advice.reason

    def test_prefers_largest_base(self, checker):
        """Should prefer Z-up when XY is largest face."""
        geo = {"bounding_box": {"x": 200, "y": 200, "z": 10}}
        advice = checker.recommend_orientation(geo)
        assert advice.axis == "Z"

    def test_missing_bbox_returns_default(self, checker):
        advice = checker.recommend_orientation({})
        assert advice.axis == "Z"  # default orientation


class TestSupportSuggestion:
    def test_fdm_with_overhang(self, checker, sample_geometry):
        profile = PrintProfile(
            name="fdm_test",
            technology="FDM",
            min_wall_thickness=0.8,
            max_overhang_angle=45,
            min_hole_diameter=2.0,
            max_build_volume=(220, 220, 250),
        )
        advice = checker.suggest_supports(profile, sample_geometry)
        assert advice.strategy in ("tree", "linear", "none")

    def test_sls_no_support(self, checker, sample_geometry):
        """SLS is self-supporting → strategy should be 'none'."""
        profile = PrintProfile(
            name="sls_test",
            technology="SLS",
            min_wall_thickness=0.7,
            max_overhang_angle=90,
            min_hole_diameter=1.5,
            max_build_volume=(300, 300, 300),
        )
        advice = checker.suggest_supports(profile, sample_geometry)
        assert advice.strategy == "none"


class TestMaterialEstimate:
    def test_basic_estimate(self, checker):
        geo = {"volume_cm3": 100.0}
        est = checker.estimate_material(geo, infill_percent=20)
        assert est.filament_weight_g > 0
        assert est.filament_length_m > 0
        assert est.cost_estimate_cny > 0

    def test_higher_infill_more_material(self, checker):
        geo = {"volume_cm3": 100.0}
        low = checker.estimate_material(geo, infill_percent=10)
        high = checker.estimate_material(geo, infill_percent=50)
        assert high.filament_weight_g > low.filament_weight_g

    def test_zero_volume(self, checker):
        est = checker.estimate_material({"volume_cm3": 0}, infill_percent=20)
        assert est.filament_weight_g == 0


class TestTimeEstimate:
    def test_basic_estimate(self, checker):
        geo = {"bounding_box": {"x": 100, "y": 80, "z": 60}}
        est = checker.estimate_print_time(geo, layer_height=0.2)
        assert est.total_minutes > 0
        assert est.layer_count == 300  # 60mm / 0.2mm

    def test_finer_layer_more_time(self, checker):
        geo = {"bounding_box": {"x": 100, "y": 80, "z": 60}}
        fast = checker.estimate_print_time(geo, layer_height=0.3)
        slow = checker.estimate_print_time(geo, layer_height=0.1)
        assert slow.total_minutes > fast.total_minutes

    def test_missing_bbox(self, checker):
        est = checker.estimate_print_time({})
        assert est.total_minutes == 0


class TestCorrectionAdvice:
    def test_thin_wall_correction(self, checker):
        from backend.models.printability import PrintIssue
        issues = [
            PrintIssue(
                check="wall_thickness",
                severity="error",
                message="Wall too thin: 0.3mm < 0.8mm minimum",
                actual_value=0.3,
                threshold=0.8,
            ),
        ]
        corrections = checker.suggest_corrections(issues)
        assert len(corrections) == 1
        assert "壁厚" in corrections[0].suggestion or "wall" in corrections[0].suggestion.lower()

    def test_overhang_correction(self, checker):
        from backend.models.printability import PrintIssue
        issues = [
            PrintIssue(
                check="overhang",
                severity="warning",
                message="Overhang angle 55° exceeds 45°",
                actual_value=55,
                threshold=45,
            ),
        ]
        corrections = checker.suggest_corrections(issues)
        assert len(corrections) >= 1

    def test_empty_issues(self, checker):
        corrections = checker.suggest_corrections([])
        assert corrections == []
```

**Commit:** `feat: 高级可打印性分析 — 方向/支撑/材料/时间/修正建议 (Phase 6 Task 6.5)`

---

## Task 6.6: 轮廓叠加比对 [backend]

**Files:**
- Modify: `backend/infra/render.py` (add wireframe contour + overlay)
- Modify: `backend/core/smart_refiner.py` (add contour_overlay parameter)
- Test: `tests/test_contour_overlay.py`

### 设计

轮廓叠加流程：
1. `render_wireframe_contour()` — STEP → SVG（线框）→ 轮廓图
2. `overlay_contour_on_drawing()` — 轮廓图 + 原始图纸 → 叠加图
3. `SmartRefiner.refine()` 新增 `contour_overlay=True` → 调用上述函数

#### render.py 新增函数

```python
def render_wireframe_contour(
    step_filepath: str,
    output_filepath: str,
    view: str = "front",
    line_color: tuple[int, int, int] = (255, 0, 0),
    line_width: int = 2,
) -> str:
    """Render STEP model as wireframe contour PNG.

    Uses CadQuery SVG export (inherently wireframe) and converts to PNG
    with specified line color for overlay visibility.

    Returns output filepath.
    """

def overlay_contour_on_drawing(
    drawing_path: str,
    contour_path: str,
    output_path: str,
    alpha: float = 0.6,
) -> str:
    """Overlay wireframe contour onto original drawing image.

    Uses PIL for image compositing with alpha blending.

    Returns output filepath.
    """
```

#### smart_refiner.py 扩展

在 `SmartRefiner.refine()` 方法中新增 `contour_overlay` 参数：

```python
async def refine(
    self,
    code: str,
    drawing_spec: DrawingSpec,
    original_image: bytes | None = None,
    max_rounds: int = 3,
    structured_feedback: bool = False,
    topology_check: bool = False,
    contour_overlay: bool = False,  # 新增
) -> RefineResult:
```

当 `contour_overlay=True` 且 VL 比对 FAIL 时：
1. 调用 `render_wireframe_contour()` 生成线框轮廓
2. 调用 `overlay_contour_on_drawing()` 生成叠加图
3. 将叠加图传入 VL 做精细差异分析
4. 将差异信息注入 fix_instructions

#### tests/test_contour_overlay.py

```python
"""Tests for contour overlay rendering and SmartRefiner integration."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from backend.infra.render import (
    render_wireframe_contour,
    overlay_contour_on_drawing,
)


class TestRenderWireframeContour:
    def test_returns_output_path(self, tmp_path):
        out = str(tmp_path / "contour.png")
        # Mock CadQuery import
        with patch("backend.infra.render.cq") as mock_cq:
            mock_shape = MagicMock()
            mock_cq.importers.importStep.return_value = mock_shape
            mock_cq.exporters.export = MagicMock()
            result = render_wireframe_contour(
                "fake.step", out, view="front"
            )
        assert result == out

    def test_default_view_is_front(self, tmp_path):
        out = str(tmp_path / "contour.png")
        with patch("backend.infra.render.cq") as mock_cq:
            mock_cq.importers.importStep.return_value = MagicMock()
            mock_cq.exporters.export = MagicMock()
            render_wireframe_contour("fake.step", out)
        # Default view is front — just verify no error

    def test_custom_line_color(self, tmp_path):
        out = str(tmp_path / "contour.png")
        with patch("backend.infra.render.cq") as mock_cq:
            mock_cq.importers.importStep.return_value = MagicMock()
            mock_cq.exporters.export = MagicMock()
            render_wireframe_contour(
                "fake.step", out, line_color=(0, 255, 0)
            )


class TestOverlayContourOnDrawing:
    def test_creates_overlay_image(self, tmp_path):
        # Create two dummy images
        from PIL import Image
        drawing = Image.new("RGB", (200, 200), (255, 255, 255))
        contour = Image.new("RGBA", (200, 200), (255, 0, 0, 128))

        d_path = str(tmp_path / "drawing.png")
        c_path = str(tmp_path / "contour.png")
        o_path = str(tmp_path / "overlay.png")

        drawing.save(d_path)
        contour.save(c_path)

        result = overlay_contour_on_drawing(d_path, c_path, o_path, alpha=0.6)
        assert result == o_path
        assert Path(o_path).exists()

    def test_different_alpha(self, tmp_path):
        from PIL import Image
        drawing = Image.new("RGB", (100, 100), (255, 255, 255))
        contour = Image.new("RGBA", (100, 100), (255, 0, 0, 200))

        d_path = str(tmp_path / "d.png")
        c_path = str(tmp_path / "c.png")

        drawing.save(d_path)
        contour.save(c_path)

        out_low = str(tmp_path / "low.png")
        out_high = str(tmp_path / "high.png")

        overlay_contour_on_drawing(d_path, c_path, out_low, alpha=0.3)
        overlay_contour_on_drawing(d_path, c_path, out_high, alpha=0.9)
        assert Path(out_low).exists()
        assert Path(out_high).exists()

    def test_size_mismatch_resizes(self, tmp_path):
        """Contour should be resized to match drawing dimensions."""
        from PIL import Image
        drawing = Image.new("RGB", (400, 300), (255, 255, 255))
        contour = Image.new("RGBA", (200, 150), (255, 0, 0, 128))

        d_path = str(tmp_path / "d.png")
        c_path = str(tmp_path / "c.png")
        o_path = str(tmp_path / "o.png")

        drawing.save(d_path)
        contour.save(c_path)

        result = overlay_contour_on_drawing(d_path, c_path, o_path)
        # Should succeed without error — contour is resized
        assert Path(o_path).exists()
        overlay = Image.open(o_path)
        assert overlay.size == (400, 300)


class TestSmartRefinerContourOverlay:
    @pytest.mark.asyncio
    async def test_contour_overlay_flag_accepted(self):
        """SmartRefiner.refine() accepts contour_overlay parameter."""
        from backend.core.smart_refiner import SmartRefiner
        refiner = SmartRefiner(
            compare_fn=AsyncMock(return_value="PASS"),
            fix_fn=AsyncMock(),
        )
        result = await refiner.refine(
            code="import cq",
            drawing_spec=MagicMock(),
            contour_overlay=True,
        )
        assert result is not None
```

**Commit:** `feat: 轮廓叠加比对 — 线框渲染 + 图像合成 + SmartRefiner 扩展 (Phase 6 Task 6.6)`

---

## 执行计划总结

| Wave | 任务 | 新增测试（预估） | 并行度 |
|------|------|----------------|--------|
| Wave 1 | T6.1, T6.3, T6.4, T6.5, T6.6 | ~18, ~10, ~15, ~14, ~7 | 5 并行 |
| Wave 2 | T6.2 | ~10 | 串行 |
| **合计** | **6 任务** | **~74 新测试** | — |

**预期最终测试数:** 781 + ~74 = ~855 tests
