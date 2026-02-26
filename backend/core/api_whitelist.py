"""CadQuery API whitelist for LLM code generation guidance.

Defines verified CadQuery APIs that the code generator should use,
and blocked APIs that must not appear in generated code.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Verified CadQuery APIs
# ---------------------------------------------------------------------------

CADQUERY_WHITELIST: frozenset[str] = frozenset({
    # Core
    "Workplane",
    "Assembly",
    # 2D sketching
    "circle",
    "ellipse",
    "rect",
    "polygon",
    "polyline",
    "slot2D",
    "moveTo",
    "lineTo",
    "hLineTo",
    "vLineTo",
    "line",
    "close",
    # Arcs & splines
    "sagittaArc",
    "radiusArc",
    "tangentArcPoint",
    "threePointArc",
    "spline",
    # 3D operations
    "extrude",
    "revolve",
    "loft",
    "sweep",
    "cut",
    "cutThruAll",
    "cutBlind",
    "hole",
    # Selectors
    "faces",
    "edges",
    "vertices",
    "wires",
    "solids",
    "shells",
    # Workplane management
    "workplane",
    "workplaneFromTagged",
    "tag",
    "add",
    "save",
    # Transforms
    "translate",
    "rotate",
    "mirror",
    "offset",
    # Fillets & chamfers
    "fillet",
    "chamfer",
    # Patterns
    "polarArray",
    "rarray",
    # Boolean
    "union",
    "intersect",
    # I/O
    "exporters.export",
    "importers.importStep",
})

# ---------------------------------------------------------------------------
# Blocked APIs (must NOT appear in generated code)
# ---------------------------------------------------------------------------

BLOCKED_APIS: frozenset[str] = frozenset({
    "show_object",
    "addAnnotation",
    "addText",
    "debug",
    "log",
    "cqgi",
})


# ---------------------------------------------------------------------------
# Prompt section generator
# ---------------------------------------------------------------------------

def get_whitelist_prompt_section() -> str:
    """Return a formatted prompt section listing allowed/blocked APIs.

    Intended to be injected into the code generation prompt to guide
    the LLM toward using only verified CadQuery APIs.
    """
    allowed_sorted = sorted(CADQUERY_WHITELIST)
    blocked_sorted = sorted(BLOCKED_APIS)

    lines = [
        "## CadQuery API 使用规范",
        "",
        "### 允许使用的 API",
        ", ".join(f"`{api}`" for api in allowed_sorted),
        "",
        "### 禁止使用的 API",
        ", ".join(f"`{api}`" for api in blocked_sorted),
        "",
        "请只使用上述允许列表中的 API。禁止列表中的 API 不得出现在生成的代码中。",
    ]
    return "\n".join(lines)
