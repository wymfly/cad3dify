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
    """Single DeepCAD command.

    Supported types: create_sketch, add_line, add_arc, close_sketch,
    extrude, revolve, fillet, chamfer.
    """
    type: str
    params: dict


@dataclass
class ConversionResult:
    """Result of converting a single DeepCAD record."""
    source_id: str
    cadquery_code: str
    success: bool
    error: Optional[str] = None


# Operations that start a new chain assignment vs. continue the current chain.
# "create_sketch" produces `result = ...`; all others produce `result = result...`.
_CHAIN_START_OPS = {"create_sketch"}

# Mapping from DeepCAD operation types to CadQuery code patterns.
# Chain-start ops produce full assignments; continuation ops are method calls
# that will be appended to `result = result` by commands_to_cadquery.
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
    """Convert DeepCAD commands to CadQuery Python code.

    Chain-start operations (``create_sketch``) produce a fresh assignment.
    Continuation operations produce ``result = result.<method>(...)`` so the
    generated code is syntactically valid Python.
    """
    lines = ["import cadquery as cq", ""]

    for cmd in commands:
        template = _OP_TEMPLATES.get(cmd.type)
        if template is None:
            logger.warning("Unknown DeepCAD op: %s", cmd.type)
            continue
        try:
            fragment = template.format(**cmd.params)
        except KeyError as e:
            logger.warning("Missing param %s for op %s", e, cmd.type)
            continue

        if cmd.type in _CHAIN_START_OPS:
            lines.append(fragment)
        else:
            # Continuation: wrap as `result = result.<call>`
            lines.append(f"result = result{fragment}")

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
