"""Tests for structured VL feedback parsing."""
from __future__ import annotations

import json

import pytest


class TestParseVLFeedback:
    def test_valid_json_issues(self) -> None:
        from backend.core.vl_feedback import parse_vl_feedback

        raw = json.dumps(
            {
                "verdict": "FAIL",
                "issues": [
                    {
                        "type": "dimension",
                        "severity": "high",
                        "description": "大端直径偏小",
                        "expected": "100mm",
                        "actual": "80mm",
                        "location": "底部法兰",
                    }
                ],
            }
        )
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
        from backend.core.vl_feedback import parse_vl_feedback

        raw = "问题1: 直径偏小\n预期: 100mm\n修改: 增大 d1"
        result = parse_vl_feedback(raw)
        assert result.passed is False
        assert result.raw_text == raw

    def test_pass_keyword_in_short_text(self) -> None:
        from backend.core.vl_feedback import parse_vl_feedback

        result = parse_vl_feedback("PASS")
        assert result.passed is True

    def test_to_fix_instructions_with_issues(self) -> None:
        from backend.core.vl_feedback import parse_vl_feedback

        raw = json.dumps(
            {
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
            }
        )
        result = parse_vl_feedback(raw)
        instructions = result.to_fix_instructions()
        assert "大端直径偏小" in instructions
        assert "缺少通孔" in instructions

    def test_to_fix_instructions_pass_returns_empty(self) -> None:
        from backend.core.vl_feedback import parse_vl_feedback

        result = parse_vl_feedback("PASS")
        assert result.to_fix_instructions() == ""

    def test_json_in_markdown_code_block(self) -> None:
        from backend.core.vl_feedback import parse_vl_feedback

        raw = '```json\n{"verdict": "FAIL", "issues": [{"type": "dimension", "severity": "high", "description": "test"}]}\n```'
        result = parse_vl_feedback(raw)
        assert result.passed is False
        assert len(result.issues) == 1

    def test_to_fix_instructions_free_text_fallback(self) -> None:
        """Free-text fallback: to_fix_instructions returns raw_text as-is."""
        from backend.core.vl_feedback import parse_vl_feedback

        raw = "问题1: 高度不对\n预期: 30mm"
        result = parse_vl_feedback(raw)
        assert result.to_fix_instructions() == raw

    def test_pass_keyword_case_insensitive(self) -> None:
        """Short text 'pass' (lowercase) should also be treated as PASS."""
        from backend.core.vl_feedback import parse_vl_feedback

        result = parse_vl_feedback("pass")
        assert result.passed is True

    def test_pass_with_trailing_whitespace(self) -> None:
        from backend.core.vl_feedback import parse_vl_feedback

        result = parse_vl_feedback("  PASS  \n")
        assert result.passed is True

    def test_to_fix_instructions_includes_severity_and_location(self) -> None:
        """Fix instructions should include severity and location info."""
        from backend.core.vl_feedback import parse_vl_feedback

        raw = json.dumps(
            {
                "verdict": "FAIL",
                "issues": [
                    {
                        "type": "dimension",
                        "severity": "high",
                        "description": "直径偏小",
                        "expected": "100mm",
                        "actual": "80mm",
                        "location": "底部法兰",
                    }
                ],
            }
        )
        result = parse_vl_feedback(raw)
        instructions = result.to_fix_instructions()
        assert "high" in instructions
        assert "100mm" in instructions
        assert "底部法兰" in instructions

    def test_multiple_issues_numbered(self) -> None:
        """Multiple issues should be numbered in fix instructions."""
        from backend.core.vl_feedback import parse_vl_feedback

        raw = json.dumps(
            {
                "verdict": "FAIL",
                "issues": [
                    {"type": "dimension", "severity": "high", "description": "A"},
                    {"type": "structural", "severity": "medium", "description": "B"},
                    {"type": "feature", "severity": "low", "description": "C"},
                ],
            }
        )
        result = parse_vl_feedback(raw)
        instructions = result.to_fix_instructions()
        assert "问题1" in instructions
        assert "问题2" in instructions
        assert "问题3" in instructions

    def test_json_with_extra_whitespace(self) -> None:
        """JSON with leading/trailing whitespace should still parse."""
        from backend.core.vl_feedback import parse_vl_feedback

        raw = '  \n  {"verdict": "PASS", "issues": []}  \n  '
        result = parse_vl_feedback(raw)
        assert result.passed is True

    def test_issue_missing_optional_fields(self) -> None:
        """Issues with missing optional fields (expected, actual, location) should not crash."""
        from backend.core.vl_feedback import parse_vl_feedback

        raw = json.dumps(
            {
                "verdict": "FAIL",
                "issues": [
                    {"type": "orientation", "severity": "medium", "description": "方向反了"}
                ],
            }
        )
        result = parse_vl_feedback(raw)
        assert result.passed is False
        assert len(result.issues) == 1
        instructions = result.to_fix_instructions()
        assert "方向反了" in instructions
