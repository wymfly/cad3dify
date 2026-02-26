# V2 管道 P0/P1 优化 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 SmartRefiner 过度修改问题，增强 DrawingAnalyzer 推理能力，加入几何验证，升级知识库检索

**Architecture:** 四层防线：(1) 静态代码校验拦截明显参数偏差 (2) 包围盒校验确认几何尺寸 (3) 保守化 VL 比较减少误报 (4) 特征匹配知识库提升代码生成质量。所有改动在现有 v2 管道内完成，不改变整体架构。

**Tech Stack:** Python 3.12, CadQuery, LangChain, Pydantic, ast (stdlib), DashScope API (Qwen)

---

## 项目根目录

```
/Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify/
```

所有文件路径均相对于此根目录。

---

### Task 1: 静态代码参数校验器 `[backend]`

**Files:**
- Create: `cad3dify/v2/validators.py`
- Create: `tests/test_validators.py`

**Step 1: Write the failing test**

```python
# tests/test_validators.py
import pytest
from cad3dify.knowledge.part_types import (
    BaseBodySpec, BoreSpec, DimensionLayer, DrawingSpec, PartType,
)
from cad3dify.v2.validators import validate_code_params


def _make_spec() -> DrawingSpec:
    return DrawingSpec(
        part_type=PartType.ROTATIONAL_STEPPED,
        description="test flange",
        views=["front_section", "top"],
        overall_dimensions={"max_diameter": 100, "total_height": 30},
        base_body=BaseBodySpec(
            method="revolve",
            profile=[
                DimensionLayer(diameter=100, height=10, label="base"),
                DimensionLayer(diameter=40, height=10, label="mid"),
                DimensionLayer(diameter=24, height=10, label="top"),
            ],
            bore=BoreSpec(diameter=10, through=True),
        ),
        features=[
            {"type": "hole_pattern", "count": 6, "diameter": 10, "pcd": 70},
        ],
    )


class TestValidateCodeParams:
    def test_correct_code_passes(self):
        code = '''
d_base, d_mid, d_top, d_bore = 100, 40, 24, 10
h_base, h_mid, h_top = 10, 10, 10
n_bolts, d_bolt, pcd = 6, 10, 70
'''
        result = validate_code_params(code, _make_spec())
        assert result.passed is True
        assert len(result.mismatches) == 0

    def test_wrong_diameter_fails(self):
        code = '''
d_base = 80  # should be 100
d_mid = 40
d_top = 24
d_bore = 10
'''
        result = validate_code_params(code, _make_spec())
        assert result.passed is False
        assert any("100" in str(m) or "80" in str(m) for m in result.mismatches)

    def test_missing_bore_detected(self):
        code = '''
d_base = 100
# no bore dimension at all
'''
        result = validate_code_params(code, _make_spec())
        # missing bore is a warning, not a hard fail
        assert len(result.warnings) > 0

    def test_tolerance_within_5_percent_passes(self):
        code = '''
d_base = 98  # within 5% of 100
'''
        result = validate_code_params(code, _make_spec())
        # 98 is within 5% of 100, should pass
        assert not any("d_base" in str(m) and "98" in str(m) for m in result.mismatches)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && python -m pytest tests/test_validators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cad3dify.v2.validators'`

**Step 3: Write minimal implementation**

```python
# cad3dify/v2/validators.py
import ast
import re
from dataclasses import dataclass, field

from loguru import logger

from ..knowledge.part_types import DrawingSpec


@dataclass
class ValidationResult:
    """参数校验结果"""
    passed: bool = True
    mismatches: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extracted_values: dict[str, float] = field(default_factory=dict)


def _extract_numeric_assignments(code: str) -> dict[str, float]:
    """用 AST 从代码中提取所有 name = number 赋值"""
    values: dict[str, float] = {}
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return values

    for node in ast.walk(tree):
        # x = 100
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, (ast.Constant,)):
                if isinstance(node.value.value, (int, float)):
                    values[target.id] = float(node.value.value)
        # a, b, c = 1, 2, 3
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple):
                for elt_t, elt_v in zip(target.elts, node.value.elts):
                    if isinstance(elt_t, ast.Name) and isinstance(elt_v, ast.Constant):
                        if isinstance(elt_v.value, (int, float)):
                            values[elt_t.id] = float(elt_v.value)
    return values


def _collect_expected_values(spec: DrawingSpec) -> dict[str, float]:
    """从 DrawingSpec 收集关键数值"""
    expected: dict[str, float] = {}

    # overall dimensions
    for k, v in spec.overall_dimensions.items():
        expected[f"overall_{k}"] = float(v)

    # profile layers
    for layer in spec.base_body.profile:
        expected[f"diameter_{layer.label or 'layer'}"] = layer.diameter
        expected[f"height_{layer.label or 'layer'}"] = layer.height

    # bore
    if spec.base_body.bore:
        expected["bore_diameter"] = spec.base_body.bore.diameter

    # features
    for feat in spec.features:
        if feat.get("type") == "hole_pattern":
            if "count" in feat:
                expected["bolt_count"] = float(feat["count"])
            if "diameter" in feat:
                expected["bolt_diameter"] = float(feat["diameter"])
            if "pcd" in feat:
                expected["bolt_pcd"] = float(feat["pcd"])

    return expected


_PARAM_NAME_PATTERNS: dict[str, list[str]] = {
    # expected_key -> possible variable name patterns in code
    "overall_max_diameter": ["d_base", "d_max", "max_diameter", "diameter_base"],
    "overall_total_height": ["total_height", "total_h", "h_total"],
    "bore_diameter": ["d_bore", "bore_d", "bore_diameter", "d_inner"],
    "bolt_count": ["n_bolts", "bolt_count", "num_bolts", "n_holes"],
    "bolt_diameter": ["d_bolt", "bolt_d", "bolt_diameter", "d_hole"],
    "bolt_pcd": ["pcd", "bolt_pcd", "pitch_circle"],
}


def validate_code_params(
    code: str,
    spec: DrawingSpec,
    tolerance: float = 0.05,
) -> ValidationResult:
    """
    从生成代码中提取数值参数，与 DrawingSpec 对比。
    tolerance: 允许的相对误差（默认 5%）
    """
    result = ValidationResult()
    code_values = _extract_numeric_assignments(code)
    result.extracted_values = code_values
    expected = _collect_expected_values(spec)

    if not code_values:
        result.warnings.append("No numeric assignments found in code")
        return result

    for exp_key, exp_val in expected.items():
        patterns = _PARAM_NAME_PATTERNS.get(exp_key, [])
        matched = False
        for pat in patterns:
            if pat in code_values:
                actual = code_values[pat]
                if exp_val > 0 and abs(actual - exp_val) / exp_val > tolerance:
                    result.passed = False
                    result.mismatches.append(
                        f"{pat}={actual} but spec expects {exp_key}={exp_val} "
                        f"(diff {abs(actual - exp_val) / exp_val:.0%})"
                    )
                matched = True
                break

        # Check profile layer diameters by matching any code variable
        if not matched and exp_key.startswith("diameter_"):
            for var_name, val in code_values.items():
                if "d_" in var_name or "diameter" in var_name.lower():
                    if abs(val - exp_val) < 0.01:
                        matched = True
                        break

        if not matched and exp_key.startswith("bore_"):
            result.warnings.append(f"Could not find code variable matching {exp_key}={exp_val}")

    logger.info(f"Static validation: passed={result.passed}, "
                f"{len(result.mismatches)} mismatches, {len(result.warnings)} warnings")
    return result
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && python -m pytest tests/test_validators.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
git add cad3dify/v2/validators.py tests/test_validators.py
git commit -m "feat: add static code parameter validator for SmartRefiner guard"
```

---

### Task 2: 包围盒校验器 `[backend]`

**Files:**
- Modify: `cad3dify/v2/validators.py`
- Modify: `tests/test_validators.py`

**Step 1: Write the failing test**

```python
# tests/test_validators.py — 追加
from cad3dify.v2.validators import validate_bounding_box, BBoxResult


class TestBoundingBox:
    def test_matching_bbox_passes(self):
        dims = {"max_diameter": 100, "total_height": 30}
        actual_bbox = (100.0, 100.0, 30.0)  # xlen, ylen, zlen
        result = validate_bounding_box(actual_bbox, dims)
        assert result.passed is True

    def test_wrong_height_fails(self):
        dims = {"max_diameter": 100, "total_height": 30}
        actual_bbox = (100.0, 100.0, 10.0)  # height too short
        result = validate_bounding_box(actual_bbox, dims)
        assert result.passed is False
        assert "height" in str(result.detail).lower() or "z" in str(result.detail).lower()

    def test_partial_dims_ok(self):
        """只有部分尺寸也能校验"""
        dims = {"total_height": 30}
        actual_bbox = (80.0, 80.0, 30.0)
        result = validate_bounding_box(actual_bbox, dims)
        assert result.passed is True
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && python -m pytest tests/test_validators.py::TestBoundingBox -v`
Expected: FAIL — `ImportError: cannot import name 'validate_bounding_box'`

**Step 3: Write minimal implementation**

```python
# cad3dify/v2/validators.py — 追加

@dataclass
class BBoxResult:
    passed: bool = True
    detail: str = ""
    actual: tuple[float, float, float] = (0, 0, 0)
    expected: dict[str, float] = field(default_factory=dict)


def _get_bbox_from_step(step_filepath: str) -> tuple[float, float, float] | None:
    """从 STEP 文件读取包围盒 (xlen, ylen, zlen)"""
    try:
        import cadquery as cq
        shape = cq.importers.importStep(step_filepath)
        bb = shape.val().BoundingBox()
        return (bb.xlen, bb.ylen, bb.zlen)
    except Exception as e:
        logger.error(f"Failed to read bounding box from {step_filepath}: {e}")
        return None


def validate_bounding_box(
    actual_bbox: tuple[float, float, float],
    overall_dims: dict[str, float],
    tolerance: float = 0.10,
) -> BBoxResult:
    """
    检查实际包围盒与 DrawingSpec.overall_dimensions 是否一致。
    actual_bbox: (xlen, ylen, zlen)
    tolerance: 允许的相对误差（默认 10%）
    """
    result = BBoxResult(actual=actual_bbox, expected=overall_dims)
    mismatches = []

    # 高度检查 — 通常映射到 Z 轴
    for key in ["total_height", "height", "total_length", "length"]:
        if key in overall_dims:
            exp = overall_dims[key]
            # 高度可能在 z 轴
            actual_z = actual_bbox[2]
            if exp > 0 and abs(actual_z - exp) / exp > tolerance:
                mismatches.append(f"Z-axis: actual={actual_z:.1f} vs spec {key}={exp}")

    # 直径检查 — 旋转体映射到 X 和 Y 轴
    for key in ["max_diameter", "diameter", "width"]:
        if key in overall_dims:
            exp = overall_dims[key]
            actual_x = actual_bbox[0]
            if exp > 0 and abs(actual_x - exp) / exp > tolerance:
                mismatches.append(f"X-axis: actual={actual_x:.1f} vs spec {key}={exp}")

    if mismatches:
        result.passed = False
        result.detail = "; ".join(mismatches)
    else:
        result.detail = "Bounding box within tolerance"

    logger.info(f"BBox validation: passed={result.passed}, actual={actual_bbox}, {result.detail}")
    return result
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && python -m pytest tests/test_validators.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
git add cad3dify/v2/validators.py tests/test_validators.py
git commit -m "feat: add bounding box validator for geometry verification"
```

---

### Task 3: SmartRefiner 守卫集成 + 保守化 Prompt `[backend]`

**Files:**
- Modify: `cad3dify/v2/smart_refiner.py`
- Create: `tests/test_smart_refiner.py`

**Step 1: Write the failing test**

```python
# tests/test_smart_refiner.py
import pytest
from unittest.mock import MagicMock, patch
from cad3dify.knowledge.part_types import (
    BaseBodySpec, BoreSpec, DimensionLayer, DrawingSpec, PartType,
)
from cad3dify.v2.smart_refiner import SmartRefiner


def _make_spec() -> DrawingSpec:
    return DrawingSpec(
        part_type=PartType.ROTATIONAL_STEPPED,
        description="test flange",
        views=["front_section"],
        overall_dimensions={"max_diameter": 100, "total_height": 30},
        base_body=BaseBodySpec(
            method="revolve",
            profile=[
                DimensionLayer(diameter=100, height=10, label="base"),
            ],
            bore=BoreSpec(diameter=10, through=True),
        ),
        features=[],
    )


class TestSmartRefinerGuard:
    @patch("cad3dify.v2.smart_refiner.SmartCompareChain")
    @patch("cad3dify.v2.smart_refiner.SmartFixChain")
    def test_static_validation_fail_skips_vl(self, mock_fix_cls, mock_compare_cls):
        """When static validation finds mismatches, VL comparison is skipped"""
        # Code with wrong diameter — static check should catch it
        bad_code = "d_base = 50\n"  # should be 100
        refiner = SmartRefiner()

        # VL compare should NOT be called
        mock_compare_cls.return_value.invoke = MagicMock()

        result = refiner.refine(
            code=bad_code,
            original_image=MagicMock(),
            rendered_image=MagicMock(),
            drawing_spec=_make_spec(),
            step_filepath=None,  # no file needed, static check alone catches it
        )
        # Should return fix instructions based on static validation, not VL
        assert result is not None  # Some fix is attempted
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && python -m pytest tests/test_smart_refiner.py -v`
Expected: FAIL — `TypeError: SmartRefiner.refine() got an unexpected keyword argument 'step_filepath'`

**Step 3: Rewrite smart_refiner.py with guards and conservative prompts**

完整重写 `cad3dify/v2/smart_refiner.py`：

1. `refine()` 新增 `step_filepath` 参数
2. 执行顺序：静态参数校验 → 包围盒校验 → VL 比较（仅在前两步通过时）
3. `_COMPARE_PROMPT` 增加保守化指令（"尺寸在 5% 误差内视为 PASS"，"只报告明确的结构性差异"）
4. `_FIX_CODE_PROMPT` 增加约束（"不要引入新 API"，"不要添加注释/标注代码"，"只修改数值参数"）

关键改动：
```python
# _COMPARE_PROMPT 追加
"""
## 判断标准（严格遵守）
- 如果所有尺寸在 5% 误差范围内，且结构正确（阶梯数、孔数一致），输出 "PASS"
- 只报告**明确的结构性差异**，如：缺少阶梯层、孔数不对、整体形状错误
- 不要报告：渲染角度差异、光照阴影、微小的圆角差异
- 不确定的问题不要报告
"""

# _FIX_CODE_PROMPT 追加
"""
## 绝对禁止（违反则代码无效）
1. 不要引入代码中未使用的新 API（如 addAnnotation、addText）
2. 不要修改 export 语句
3. 不要添加可视化/渲染代码
4. 不要删除已有的 try/except 安全包裹
5. 只修改数值参数和几何操作，不要重构代码结构
"""
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && python -m pytest tests/test_smart_refiner.py tests/test_validators.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
git add cad3dify/v2/smart_refiner.py tests/test_smart_refiner.py
git commit -m "feat: add static/bbox guards to SmartRefiner, conservative prompts"
```

---

### Task 4: DrawingAnalyzer CoT 增强 `[backend]`

**Files:**
- Modify: `cad3dify/v2/drawing_analyzer.py`
- Modify: `tests/test_validators.py` (追加 CoT 解析测试)

**Step 1: Write the failing test**

```python
# tests/test_drawing_analyzer.py
import pytest
from cad3dify.v2.drawing_analyzer import _parse_drawing_spec


class TestParseDrawingSpecCoT:
    def test_parse_with_reasoning(self):
        """CoT 格式：先推理后 JSON"""
        text = '''
```reasoning
1. 从正视图可见：外径标注 φ100，中间凸台 φ40，顶部 φ24
2. 从俯视图可见：6 个均布孔，PCD=70
3. 高度判断：底层 10mm + 中间 10mm + 顶部 10mm = 30mm
4. 零件类型：多层阶梯 + 中心通孔 → rotational_stepped
5. 建模方式：revolve（旋转体首选）
```

```json
{
  "part_type": "rotational_stepped",
  "description": "三层阶梯法兰盘",
  "views": ["front_section", "top"],
  "overall_dimensions": {"max_diameter": 100, "total_height": 30},
  "base_body": {
    "method": "revolve",
    "profile": [
      {"diameter": 100, "height": 10, "label": "base_flange"},
      {"diameter": 40, "height": 10, "label": "middle_boss"},
      {"diameter": 24, "height": 10, "label": "top_boss"}
    ],
    "bore": {"diameter": 10, "through": true}
  },
  "features": [
    {"type": "hole_pattern", "pattern": "circular", "count": 6, "diameter": 10, "pcd": 70}
  ],
  "notes": []
}
```
'''
        result = _parse_drawing_spec({"text": text})
        assert result["result"] is not None
        assert result["result"].part_type.value == "rotational_stepped"
        assert result.get("reasoning") is not None or result["result"] is not None

    def test_parse_without_reasoning_still_works(self):
        """向后兼容：无 CoT 也能解析"""
        text = '''```json
{"part_type": "plate", "description": "test", "views": [], "overall_dimensions": {},
 "base_body": {"method": "extrude"}, "features": [], "notes": []}
```'''
        result = _parse_drawing_spec({"text": text})
        assert result["result"] is not None
        assert result["result"].part_type.value == "plate"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && python -m pytest tests/test_drawing_analyzer.py -v`
Expected: FAIL — cannot parse reasoning block / assertion on reasoning key

**Step 3: Update drawing_analyzer.py**

1. 在 `_DRAWING_ANALYSIS_PROMPT` 开头添加 CoT 指令：

```
## 分析步骤（必须严格按顺序执行）
请先在 ```reasoning``` 代码块中逐步分析，然后再输出 JSON：

1. **视图识别**：列出图纸包含的视图类型
2. **尺寸提取**：从每个视图中提取所有标注尺寸
3. **结构分析**：识别零件的层级结构（几层、每层的直径和高度）
4. **特征识别**：孔、圆角、倒角、键槽等
5. **零件分类**：根据上述分析判断零件类型
6. **建模方式**：确定最佳的 CadQuery 构建方法

分析完成后，输出 JSON。
```

2. 更新 `_parse_drawing_spec()` 同时提取 reasoning 和 JSON：

```python
def _parse_drawing_spec(input: dict) -> dict:
    text = input["text"]

    # 提取 reasoning（如果有）
    reasoning_match = re.search(r"```reasoning\s*\n(.*?)\n```", text, re.DOTALL)
    reasoning = reasoning_match.group(1).strip() if reasoning_match else None
    if reasoning:
        logger.info(f"CoT reasoning:\n{reasoning}")

    # 提取 JSON（保持现有逻辑）
    json_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    # ... 现有解析逻辑 ...

    return {"result": spec, "reasoning": reasoning}
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && python -m pytest tests/test_drawing_analyzer.py tests/test_validators.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
git add cad3dify/v2/drawing_analyzer.py tests/test_drawing_analyzer.py
git commit -m "feat: add Chain-of-Thought reasoning to DrawingAnalyzer prompt"
```

---

### Task 5: CadQuery 几何验证注入 execute_python_code `[backend]`

**Files:**
- Modify: `cad3dify/agents.py`
- Modify: `cad3dify/v2/validators.py` (add `validate_step_geometry`)
- Modify: `tests/test_validators.py`

**Step 1: Write the failing test**

```python
# tests/test_validators.py — 追加

class TestValidateStepGeometry:
    def test_valid_step_file(self, tmp_path):
        """生成一个简单的 STEP 文件并验证"""
        import cadquery as cq
        step_path = str(tmp_path / "test.step")
        result = cq.Workplane("XY").box(100, 100, 30)
        cq.exporters.export(result, step_path)

        from cad3dify.v2.validators import validate_step_geometry
        geo_result = validate_step_geometry(step_path)
        assert geo_result.is_valid is True
        assert geo_result.volume > 0
        assert geo_result.bbox is not None
        assert abs(geo_result.bbox[2] - 30.0) < 0.1  # Z = 30

    def test_nonexistent_file(self):
        from cad3dify.v2.validators import validate_step_geometry
        geo_result = validate_step_geometry("/nonexistent.step")
        assert geo_result.is_valid is False
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && python -m pytest tests/test_validators.py::TestValidateStepGeometry -v`
Expected: FAIL — `ImportError: cannot import name 'validate_step_geometry'`

**Step 3: Implement validate_step_geometry**

```python
# cad3dify/v2/validators.py — 追加

@dataclass
class GeometryResult:
    is_valid: bool = False
    volume: float = 0.0
    bbox: tuple[float, float, float] | None = None  # (xlen, ylen, zlen)
    error: str = ""


def validate_step_geometry(step_filepath: str) -> GeometryResult:
    """验证 STEP 文件的几何有效性"""
    try:
        import cadquery as cq
        shape = cq.importers.importStep(step_filepath)
        solid = shape.val()
        bb = solid.BoundingBox()
        return GeometryResult(
            is_valid=solid.isValid(),
            volume=solid.Volume(),
            bbox=(bb.xlen, bb.ylen, bb.zlen),
        )
    except FileNotFoundError:
        return GeometryResult(is_valid=False, error=f"File not found: {step_filepath}")
    except Exception as e:
        return GeometryResult(is_valid=False, error=str(e))
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && python -m pytest tests/test_validators.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
git add cad3dify/v2/validators.py cad3dify/agents.py tests/test_validators.py
git commit -m "feat: add STEP geometry validation (isValid, Volume, BoundingBox)"
```

---

### Task 6: 知识库扩充 — 特征标签 + 新示例 `[backend]`

**Files:**
- Create: `cad3dify/knowledge/examples/gear.py`
- Create: `cad3dify/knowledge/examples/general.py`
- Modify: `cad3dify/knowledge/examples/__init__.py`
- Modify: `cad3dify/knowledge/examples/rotational.py` (追加更多示例)
- Modify: `cad3dify/knowledge/examples/plate.py` (追加更多示例)

**Step 1: Expand examples**

为每种零件类型添加 2-3 个新的高质量示例，重点覆盖：
- 旋转体：带键槽的法兰、带沉头孔的法兰、薄壁旋转件
- 板件：带长圆孔的板、多孔阵列板
- 齿轮：简化的直齿轮（involute 近似）
- 通用：带凸台的底座

每个示例格式为 `(说明文本, CadQuery代码)`，代码必须可执行且导出 STEP。

**Step 2: Add feature tags to examples**

```python
# cad3dify/knowledge/examples/__init__.py — 改造

from dataclasses import dataclass


@dataclass
class TaggedExample:
    description: str
    code: str
    features: set[str]  # {"bolt_holes", "fillet", "revolve", "bore", "chamfer", ...}

# 重构所有示例为 TaggedExample 格式
TAGGED_EXAMPLES: list[TaggedExample] = [...]
```

**Step 3: Verify examples compile**

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && python -c "from cad3dify.knowledge.examples import TAGGED_EXAMPLES; print(f'{len(TAGGED_EXAMPLES)} examples loaded')"`
Expected: `~15-20 examples loaded`

**Step 4: Commit**

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
git add cad3dify/knowledge/examples/
git commit -m "feat: expand knowledge base to 20+ tagged examples"
```

---

### Task 7: 特征匹配示例选择器 `[backend]`

**Files:**
- Modify: `cad3dify/v2/modeling_strategist.py`
- Create: `tests/test_modeling_strategist.py`

**Step 1: Write the failing test**

```python
# tests/test_modeling_strategist.py
import pytest
from cad3dify.knowledge.part_types import (
    BaseBodySpec, BoreSpec, DimensionLayer, DrawingSpec, PartType,
)
from cad3dify.v2.modeling_strategist import ModelingStrategist


def _make_flange_spec() -> DrawingSpec:
    return DrawingSpec(
        part_type=PartType.ROTATIONAL_STEPPED,
        description="法兰盘",
        views=["front_section", "top"],
        overall_dimensions={"max_diameter": 100, "total_height": 30},
        base_body=BaseBodySpec(
            method="revolve",
            profile=[DimensionLayer(diameter=100, height=10, label="base")],
            bore=BoreSpec(diameter=10, through=True),
        ),
        features=[
            {"type": "hole_pattern", "count": 6, "diameter": 10, "pcd": 70},
            {"type": "fillet", "radius": 3},
        ],
    )


class TestFeatureBasedSelection:
    def test_selects_examples_with_matching_features(self):
        spec = _make_flange_spec()
        strategist = ModelingStrategist()
        context = strategist.select(spec)

        # Should prioritize examples with bolt_holes + fillet + revolve
        assert len(context.examples) > 0
        # First example should be highly relevant (rotational with bolt holes)
        first_desc = context.examples[0][0].lower()
        assert "法兰" in first_desc or "bolt" in first_desc or "螺栓" in first_desc

    def test_max_examples_limit(self):
        spec = _make_flange_spec()
        strategist = ModelingStrategist()
        context = strategist.select(spec, max_examples=2)
        assert len(context.examples) <= 2
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && python -m pytest tests/test_modeling_strategist.py -v`
Expected: FAIL — `TypeError: select() got an unexpected keyword argument 'max_examples'`

**Step 3: Implement feature-based selection**

在 `ModelingStrategist.select()` 中：
1. 从 `DrawingSpec` 提取特征集合：`{"revolve", "bore", "bolt_holes", "fillet", ...}`
2. 对所有 `TaggedExample` 计算 Jaccard 相似度
3. 按相似度排序，取 top-k
4. 保持向后兼容（无 tagged examples 时回退到 PartType 匹配）

```python
def _extract_features_from_spec(spec: DrawingSpec) -> set[str]:
    features = set()
    features.add(spec.base_body.method)  # revolve, extrude, etc.
    if spec.base_body.bore:
        features.add("bore")
    for feat in spec.features:
        feat_type = feat.get("type", "")
        features.add(feat_type)  # hole_pattern, fillet, chamfer, etc.
    return features

def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify && python -m pytest tests/ -v`
Expected: All PASS

**Step 5: Commit**

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
git add cad3dify/v2/modeling_strategist.py tests/test_modeling_strategist.py
git commit -m "feat: feature-based example selection using Jaccard similarity"
```

---

### Task 8: 管道集成 + UI 更新 `[backend]`

**Files:**
- Modify: `cad3dify/pipeline.py`
- Modify: `scripts/app.py`

**Step 1: Update generate_step_v2 with validation loop**

在 `pipeline.py` 的 `generate_step_v2()` 中：

1. 阶段 3 执行后，立即运行几何验证：
```python
geo = validate_step_geometry(output_filepath)
if not geo.is_valid:
    logger.error(f"[V2] Generated geometry invalid: {geo.error}")
```

2. 阶段 4 循环前，先做静态参数校验：
```python
param_result = validate_code_params(code, spec)
if not param_result.passed:
    # 基于静态校验的修复指令，不走 VL
    fix_instructions = "参数校验发现以下问题：\n" + "\n".join(param_result.mismatches)
    ...
```

3. 包围盒校验作为 VL 比较的前置条件：
```python
bbox_result = validate_bounding_box(geo.bbox, spec.overall_dimensions)
if bbox_result.passed:
    logger.info("[V2] Bounding box OK, proceeding to VL comparison")
else:
    logger.warning(f"[V2] Bounding box mismatch: {bbox_result.detail}")
    # 生成基于 bbox 的修复指令
```

**Step 2: Update Streamlit UI**

在 `scripts/app.py` 中增加验证结果展示区域：
- 显示 CoT reasoning（如果有）
- 显示静态参数校验结果
- 显示包围盒校验结果
- 显示每轮改进的校验状态

**Step 3: Run integration test**

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
# 确认所有单元测试通过
python -m pytest tests/ -v
# 确认 import 无报错
python -c "from cad3dify import generate_step_v2; print('OK')"
```

**Step 4: Commit**

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
git add cad3dify/pipeline.py scripts/app.py
git commit -m "feat: integrate validators into v2 pipeline and Streamlit UI"
```

---

### Task 9: P2 设计方案文档（仅设计不实施） `[architecture]`

**Files:**
- Create: `docs/plans/2026-02-26-v2-p2-design.md`

编写 P2 两个方向的设计方案：

**P2.1 — 自动化评测基准**
- 数据集结构：`benchmarks/` 目录，每个 case 含 `drawing.png` + `expected_spec.json` + `expected_bbox.json`
- 评测指标：编译通过率、参数提取准确率（Spec vs Expected）、几何匹配率（BBox 误差）
- 运行方式：`python -m cad3dify.benchmark run --dataset benchmarks/v1/`
- 报告格式：Markdown 表格 + JSON 详细结果
- 数据集来源建议：从 GrabCAD 下载公开图纸，手工标注 expected_spec

**P2.2 — 成本优化**
- 静态校验通过 + BBox 通过 → 跳过 VL refinement（节省 60%+ 调用）
- 简单修复（只改数值参数）→ 用 qwen-coder-plus 替代 qwen-vl-max 做修复
- Token 用量监控：每轮记录输入/输出 token 数，输出到 `pipeline_stats.json`
- 模型降级策略：first round 用 full model，subsequent rounds 用 turbo/lite

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
git add docs/plans/2026-02-26-v2-p2-design.md
git commit -m "docs: P2 design — automated benchmark and cost optimization"
```
