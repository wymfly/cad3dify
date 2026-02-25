"""Tests for DrawingAnalyzer CoT parsing."""

import pytest

from cad3dify.v2.drawing_analyzer import _parse_drawing_spec


class TestParseDrawingSpecCoT:
    def test_parse_with_reasoning_and_json(self):
        """CoT format: reasoning block then JSON block."""
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
        assert result["result"].overall_dimensions["max_diameter"] == 100
        assert result["reasoning"] is not None
        assert "φ100" in result["reasoning"]

    def test_parse_without_reasoning(self):
        """Backward compat: no reasoning block, just JSON."""
        text = '''```json
{"part_type": "plate", "description": "test plate", "views": [],
 "overall_dimensions": {}, "base_body": {"method": "extrude"},
 "features": [], "notes": []}
```'''
        result = _parse_drawing_spec({"text": text})
        assert result["result"] is not None
        assert result["result"].part_type.value == "plate"
        assert result["reasoning"] is None

    def test_parse_bare_json(self):
        """No code blocks at all, just raw JSON."""
        text = '{"part_type": "general", "description": "x", "views": [], "overall_dimensions": {}, "base_body": {"method": "extrude"}, "features": [], "notes": []}'
        result = _parse_drawing_spec({"text": text})
        assert result["result"] is not None
        assert result["result"].part_type.value == "general"

    def test_invalid_json_returns_none(self):
        """Invalid JSON returns result=None but still extracts reasoning."""
        text = '''
```reasoning
Some analysis here
```

```json
{invalid json!!!}
```
'''
        result = _parse_drawing_spec({"text": text})
        assert result["result"] is None
        assert result["reasoning"] is not None
        assert "Some analysis" in result["reasoning"]

    def test_invalid_part_type_defaults_to_general(self):
        """Unknown part_type is replaced with 'general'."""
        text = '{"part_type": "unknown_type", "description": "x", "views": [], "overall_dimensions": {}, "base_body": {"method": "extrude"}, "features": [], "notes": []}'
        result = _parse_drawing_spec({"text": text})
        assert result["result"] is not None
        assert result["result"].part_type.value == "general"
