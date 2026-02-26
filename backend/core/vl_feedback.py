"""Structured VL feedback parser.

Parses JSON feedback from VL model with graceful fallback for free-text.

Expected JSON format::

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
import re
from dataclasses import dataclass, field

from loguru import logger

# Maximum length of raw text to be considered a "short PASS response".
_SHORT_PASS_THRESHOLD = 20


@dataclass
class VLFeedback:
    """Parsed VL comparison feedback."""

    passed: bool = False
    issues: list[dict] = field(default_factory=list)
    raw_text: str = ""

    def to_fix_instructions(self) -> str:
        """Convert issues to fix instructions for Coder model.

        - If passed -> return ""
        - If issues present: format each as numbered entry with severity,
          description, expected value, and location.
        - If no issues but raw_text exists: return raw_text as-is
          (free-text fallback).
        """
        if self.passed:
            return ""

        if self.issues:
            lines: list[str] = []
            for idx, issue in enumerate(self.issues, start=1):
                severity = issue.get("severity", "unknown")
                description = issue.get("description", "")
                header = f"问题{idx} [{severity}]: {description}"
                lines.append(header)

                expected = issue.get("expected")
                if expected:
                    lines.append(f"  预期: {expected}")

                actual = issue.get("actual")
                if actual:
                    lines.append(f"  实际: {actual}")

                location = issue.get("location")
                if location:
                    lines.append(f"  位置: {location}")

            return "\n".join(lines)

        # Free-text fallback: return raw text as-is.
        return self.raw_text


def _extract_json_from_markdown(raw: str) -> str | None:
    """Extract JSON content from markdown ```json ... ``` code blocks.

    Returns the inner JSON string if found, otherwise None.
    """
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _try_parse_json(text: str) -> dict | None:
    """Attempt to parse text as JSON. Returns dict on success, None on failure."""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def parse_vl_feedback(raw: str) -> VLFeedback:
    """Parse VL model output into structured feedback.

    Strategy:
    1. Short PASS response: text is "PASS" or very short containing PASS
       -> passed=True
    2. Try JSON parse (also handle markdown ```json ... ``` wrapper)
    3. Fallback: treat as free text -> passed=False, raw_text=raw
    """
    stripped = raw.strip()

    # --- Strategy 1: Short PASS response ---
    if len(stripped) <= _SHORT_PASS_THRESHOLD and "PASS" in stripped.upper():
        logger.debug(f"VL feedback: short PASS response detected: {stripped!r}")
        return VLFeedback(passed=True, raw_text=stripped)

    # --- Strategy 2: Try JSON parse ---
    # First try direct JSON parse.
    data = _try_parse_json(stripped)

    # If that fails, try extracting from markdown code block.
    if data is None:
        extracted = _extract_json_from_markdown(stripped)
        if extracted is not None:
            data = _try_parse_json(extracted)

    if data is not None:
        verdict = data.get("verdict", "").upper()
        issues = data.get("issues", [])
        passed = verdict == "PASS" and not issues
        logger.debug(
            f"VL feedback: parsed JSON — verdict={verdict}, "
            f"issues_count={len(issues)}"
        )
        return VLFeedback(passed=passed, issues=issues, raw_text=raw)

    # --- Strategy 3: Free-text fallback ---
    logger.debug(
        f"VL feedback: free-text fallback (len={len(raw)})"
    )
    return VLFeedback(passed=False, raw_text=raw)
