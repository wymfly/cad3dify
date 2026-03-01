"""Post-processing recommendation engine.

Generates actionable recommendations based on PrintabilityChecker results.
Maps issue types to specific tools (NX, Magics, Oqton) and actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PostProcessRecommendation:
    """A single post-processing recommendation."""

    action: str       # "thicken_wall", "add_support", "reorient", etc.
    tool: str         # "NX/Magics", "Oqton/Magics", etc.
    description: str
    severity: str     # "warning" | "error"


# Issue type -> recommendation mapping
_ISSUE_RECOMMENDATIONS: dict[str, dict[str, str]] = {
    "thin_wall": {
        "action": "thicken_wall",
        "tool": "NX/Magics",
        "description": "增厚壁面至最小厚度要求。在 NX 或 Magics 中使用偏移面/加厚功能修复薄壁区域。",
    },
    "overhang": {
        "action": "add_support",
        "tool": "Oqton/Magics",
        "description": "添加支撑结构。在 Oqton 或 Magics 中自动生成树状支撑，减少悬垂角度。",
    },
    "small_feature": {
        "action": "enlarge_feature",
        "tool": "NX",
        "description": "放大过小特征至可打印尺寸。在 NX 中调整特征参数，确保最小特征大于喷嘴直径。",
    },
    "sharp_edge": {
        "action": "add_fillet",
        "tool": "NX",
        "description": "添加圆角消除尖锐边缘。在 NX 中对锐边添加 R0.5mm+ 的圆角，改善打印质量。",
    },
    "bridging": {
        "action": "add_support",
        "tool": "Oqton/Magics",
        "description": "添加桥接支撑。在 Oqton 中为跨距过大的桥接区域生成支撑。",
    },
}


def generate_recommendations(
    printability: dict[str, Any] | None,
) -> list[PostProcessRecommendation]:
    """Generate recommendations from printability check results."""
    if not printability:
        return []

    issues = printability.get("issues", [])
    if not issues:
        return []

    recommendations: list[PostProcessRecommendation] = []
    seen_actions: set[str] = set()

    for issue in issues:
        issue_type = issue.get("type", "")
        severity = issue.get("severity", "warning")
        mapping = _ISSUE_RECOMMENDATIONS.get(issue_type)

        if mapping and mapping["action"] not in seen_actions:
            seen_actions.add(mapping["action"])
            recommendations.append(
                PostProcessRecommendation(
                    action=mapping["action"],
                    tool=mapping["tool"],
                    description=mapping["description"],
                    severity=severity,
                )
            )

    return recommendations
