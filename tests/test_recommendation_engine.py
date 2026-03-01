"""Tests for PostProcessRecommendationEngine."""

import pytest

from backend.core.recommendation_engine import (
    PostProcessRecommendation,
    generate_recommendations,
)


class TestGenerateRecommendations:
    def test_thin_wall_produces_thicken_action(self):
        printability = {
            "printable": True,
            "issues": [
                {"type": "thin_wall", "severity": "warning", "message": "Wall < 0.8mm at region X"}
            ],
        }
        recs = generate_recommendations(printability)
        assert len(recs) >= 1
        assert any(r.action == "thicken_wall" for r in recs)

    def test_overhang_produces_support_action(self):
        printability = {
            "printable": True,
            "issues": [
                {"type": "overhang", "severity": "warning", "message": "Overhang > 45deg"}
            ],
        }
        recs = generate_recommendations(printability)
        assert any(r.action == "add_support" for r in recs)

    def test_no_issues_produces_empty(self):
        printability = {"printable": True, "issues": []}
        recs = generate_recommendations(printability)
        assert recs == []

    def test_none_printability_returns_empty(self):
        recs = generate_recommendations(None)
        assert recs == []

    def test_recommendation_fields(self):
        printability = {
            "printable": True,
            "issues": [
                {"type": "thin_wall", "severity": "warning", "message": "test"}
            ],
        }
        recs = generate_recommendations(printability)
        r = recs[0]
        assert r.action
        assert r.tool
        assert r.description
        assert r.severity

    def test_multiple_issues_deduplicated(self):
        printability = {
            "printable": True,
            "issues": [
                {"type": "thin_wall", "severity": "warning", "message": "area 1"},
                {"type": "thin_wall", "severity": "warning", "message": "area 2"},
            ],
        }
        recs = generate_recommendations(printability)
        assert len([r for r in recs if r.action == "thicken_wall"]) == 1

    def test_unknown_issue_type_skipped(self):
        printability = {
            "printable": True,
            "issues": [
                {"type": "unknown_issue_xyz", "severity": "info", "message": "test"}
            ],
        }
        recs = generate_recommendations(printability)
        assert recs == []
