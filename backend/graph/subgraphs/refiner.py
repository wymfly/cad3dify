"""Refiner subgraph — Compare -> Fix -> Re-execute -> Re-render cycle.

Models the SmartRefiner loop as a LangGraph subgraph with 5 nodes:
1. static_diagnose  — parameter + bbox + topology checks (no LLM)
2. render_for_compare — STEP -> PNG rendering
3. vl_compare — VL model visual comparison
4. coder_fix — LLM code fix
5. re_execute — sandbox execution + scoring + rollback
"""

import logging
import tempfile
from typing import Any, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from backend.core.candidate_scorer import score_candidate
from backend.core.rollback import RollbackTracker
from backend.core.validators import (
    compare_topology,
    count_topology,
    validate_bounding_box,
    validate_code_params,
    validate_step_geometry,
)
from backend.graph.chains import build_compare_chain, build_fix_chain
from backend.infra.image import ImageData
from backend.infra.render import render_and_export_image, render_multi_view
from backend.infra.sandbox import SafeExecutor
from backend.knowledge.part_types import DrawingSpec
from backend.models.pipeline_config import PipelineConfig
from backend.pipeline.pipeline import _score_geometry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class RefinerState(TypedDict, total=False):
    code: str
    step_path: str
    drawing_spec: dict  # DrawingSpec.model_dump() at entry
    image_path: str  # original drawing image path
    round: int
    max_rounds: int
    verdict: str  # "pending" | "pass" | "fail" | "max_rounds_reached"
    static_notes: list[str]
    comparison_result: str | None
    rendered_image_path: str | None
    prev_score: float | None
    prev_code: str | None
    prev_step_path: str | None


# ---------------------------------------------------------------------------
# State mapping helpers
# ---------------------------------------------------------------------------


def map_job_to_refiner(state: dict, config: dict) -> RefinerState:
    """Map parent job state to RefinerState for subgraph entry."""
    pipeline_config: PipelineConfig = config.get("configurable", {}).get(
        "pipeline_config", PipelineConfig()
    )

    # DrawingSpec -> dict if needed
    spec = state.get("drawing_spec")
    if isinstance(spec, DrawingSpec):
        spec = spec.model_dump()

    return RefinerState(
        code=state.get("generated_code", state.get("code", "")),
        step_path=state.get("step_path", ""),
        drawing_spec=spec or {},
        image_path=state.get("image_path", ""),
        round=0,
        max_rounds=pipeline_config.max_refinements,
        verdict="pending",
        static_notes=[],
        comparison_result=None,
        rendered_image_path=None,
        prev_score=None,
        prev_code=None,
        prev_step_path=None,
    )


def map_refiner_to_job(refiner_state: RefinerState) -> dict:
    """Extract final code + step_path from RefinerState back to job state."""
    return {
        "generated_code": refiner_state.get("code", ""),
        "step_path": refiner_state.get("step_path", ""),
    }


# ---------------------------------------------------------------------------
# Node 1: static_diagnose
# ---------------------------------------------------------------------------


def static_diagnose(state: RefinerState, config: RunnableConfig) -> dict:
    """Run static checks: param validation + bbox + optional topology."""
    pipeline_config: PipelineConfig = config.get("configurable", {}).get(
        "pipeline_config", PipelineConfig()
    )

    spec = DrawingSpec(**state["drawing_spec"])
    notes: list[str] = []

    # Parameter validation
    try:
        param_result = validate_code_params(state["code"], spec)
        if not param_result.passed:
            notes.extend(
                f"Param mismatch: {m}" for m in param_result.mismatches
            )
        notes.extend(f"Param warning: {w}" for w in param_result.warnings)
    except Exception as exc:
        logger.warning("validate_code_params failed: %s", exc)

    # Bounding box validation
    step_path = state.get("step_path", "")
    if step_path:
        try:
            geo = validate_step_geometry(step_path)
            if geo.is_valid and geo.bbox:
                bbox_result = validate_bounding_box(
                    geo.bbox, spec.overall_dimensions
                )
                if not bbox_result.passed:
                    notes.append(f"BBox mismatch: {bbox_result.detail}")
        except Exception as exc:
            logger.warning("validate_bounding_box failed: %s", exc)

    # Topology check (optional)
    if pipeline_config.topology_check and step_path:
        try:
            topo = count_topology(step_path)
            if not topo.error:
                expected_holes = 0
                for feat in spec.features:
                    if feat.type == "hole_pattern":
                        feat_data = (
                            feat.spec
                            if isinstance(feat.spec, dict)
                            else feat.spec.model_dump()
                        )
                        expected_holes += int(feat_data.get("count", 0))
                if spec.base_body.bore is not None:
                    expected_holes += 1
                topo_cmp = compare_topology(
                    topo, expected_holes=expected_holes
                )
                if not topo_cmp.passed:
                    notes.extend(
                        f"Topology: {m}" for m in topo_cmp.mismatches
                    )
        except Exception as exc:
            logger.warning("compare_topology failed: %s", exc)

    return {"static_notes": notes}


# ---------------------------------------------------------------------------
# Node 2: render_for_compare
# ---------------------------------------------------------------------------


def render_for_compare(state: RefinerState, config: RunnableConfig) -> dict:
    """Render STEP file to PNG for VL comparison."""
    pipeline_config: PipelineConfig = config.get("configurable", {}).get(
        "pipeline_config", PipelineConfig()
    )

    step_path = state.get("step_path", "")
    rendered_path: Optional[str] = None

    if pipeline_config.multi_view_render:
        try:
            tmpdir = tempfile.mkdtemp(prefix="refiner_render_")
            view_paths = render_multi_view(step_path, tmpdir)
            # Use isometric view as primary rendered image
            rendered_path = view_paths.get(
                "isometric", next(iter(view_paths.values()), None)
            )
        except Exception as exc:
            logger.warning(
                "Multi-view rendering failed, falling back to single view: %s",
                exc,
            )

    # Fallback to single view
    if rendered_path is None:
        try:
            tmp = tempfile.NamedTemporaryFile(
                suffix=".png", delete=False, prefix="refiner_single_"
            )
            tmp.close()
            render_and_export_image(step_path, tmp.name)
            rendered_path = tmp.name
        except Exception as exc:
            logger.error("Single-view rendering also failed: %s", exc)

    return {"rendered_image_path": rendered_path}


# ---------------------------------------------------------------------------
# Node 3: vl_compare (async)
# ---------------------------------------------------------------------------


def vl_compare(state: RefinerState, config: RunnableConfig) -> dict:
    """Run VL comparison between original drawing and rendered image."""
    pipeline_config: PipelineConfig = config.get("configurable", {}).get(
        "pipeline_config", PipelineConfig()
    )

    image_path = state.get("image_path", "")
    rendered_path = state.get("rendered_image_path")

    if not rendered_path:
        return {"verdict": "fail", "comparison_result": "No rendered image available"}

    try:
        original_image = ImageData.load_from_file(image_path)
        rendered_image = ImageData.load_from_file(rendered_path)
    except Exception as exc:
        logger.error("Failed to load images for comparison: %s", exc)
        return {"verdict": "fail", "comparison_result": f"Image load error: {exc}"}

    spec = DrawingSpec(**state["drawing_spec"])

    chain = build_compare_chain(structured=pipeline_config.structured_feedback)
    comparison_result = chain.invoke(
        {
            "drawing_spec": spec.to_prompt_text(),
            "code": state["code"],
            "original_image_type": original_image.type,
            "original_image_data": original_image.data,
            "rendered_image_type": rendered_image.type,
            "rendered_image_data": rendered_image.data,
        }
    )

    if comparison_result is None:
        return {"verdict": "pass", "comparison_result": None}

    return {"verdict": "fail", "comparison_result": comparison_result}


# ---------------------------------------------------------------------------
# Node 4: coder_fix (async)
# ---------------------------------------------------------------------------


def coder_fix(state: RefinerState, config: RunnableConfig) -> dict:
    """Fix code using LLM based on comparison feedback."""
    # Snapshot BEFORE mutation
    prev_code = state["code"]
    prev_step_path = state.get("step_path", "")

    # Build fix instructions from comparison result + static notes
    instructions_parts: list[str] = []
    if state.get("comparison_result"):
        instructions_parts.append(
            f"VL Comparison Feedback:\n{state['comparison_result']}"
        )
    if state.get("static_notes"):
        instructions_parts.append(
            "Static Analysis Notes:\n"
            + "\n".join(f"- {n}" for n in state["static_notes"])
        )
    fix_instructions = "\n\n".join(instructions_parts) or "Improve the code."

    chain = build_fix_chain()
    fixed_code = chain.invoke(
        {
            "code": state["code"],
            "fix_instructions": fix_instructions,
        }
    )

    if fixed_code is None:
        # Fix chain failed to produce code — keep existing code
        return {
            "prev_code": prev_code,
            "prev_step_path": prev_step_path,
        }

    return {
        "code": fixed_code,
        "prev_code": prev_code,
        "prev_step_path": prev_step_path,
    }


# ---------------------------------------------------------------------------
# Node 5: re_execute
# ---------------------------------------------------------------------------


def re_execute(state: RefinerState, config: RunnableConfig) -> dict:
    """Execute fixed code, score geometry, rollback on degradation."""
    pipeline_config: PipelineConfig = config.get("configurable", {}).get(
        "pipeline_config", PipelineConfig()
    )

    code = state["code"]
    step_path = state.get("step_path", "")
    spec = DrawingSpec(**state["drawing_spec"])

    # Execute code in sandbox
    executor = SafeExecutor(timeout_s=60)
    try:
        result = executor.execute(code)
        if not result.success:
            logger.warning("Execution failed: %s", result.stderr[:200])
    except Exception as exc:
        logger.error("SafeExecutor error: %s", exc)

    # Score geometry
    compiled, volume_ok, bbox_ok, topology_ok = _score_geometry(
        step_path, spec, pipeline_config
    )
    new_score = float(
        score_candidate(
            compiled=compiled,
            volume_ok=volume_ok,
            bbox_ok=bbox_ok,
            topology_ok=topology_ok,
        )
    )

    # Rollback check
    updates: dict[str, Any] = {}
    prev_score = state.get("prev_score")

    if pipeline_config.rollback_on_degrade and prev_score is not None:
        tracker = RollbackTracker()
        tracker.save(state.get("prev_code", ""), prev_score)
        should_rollback, rollback_code = tracker.check_and_update(code, new_score)

        if should_rollback and rollback_code is not None:
            logger.warning(
                "Rollback triggered: score %.1f -> %.1f", prev_score, new_score
            )
            updates["code"] = rollback_code
            updates["step_path"] = state.get("prev_step_path", step_path)
            # Re-execute rollback code to restore STEP file
            try:
                executor.execute(rollback_code)
            except Exception as exc:
                logger.error("Rollback re-execution failed: %s", exc)
            # Keep prev_score unchanged after rollback
            updates["prev_score"] = prev_score
        else:
            updates["prev_score"] = new_score
    else:
        updates["prev_score"] = new_score

    # Increment round
    updates["round"] = state.get("round", 0) + 1

    return updates


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def _route_verdict(state: RefinerState) -> str:
    """Route based on verdict and round count."""
    if state.get("verdict") == "pass":
        return "end"
    if state.get("round", 0) >= state.get("max_rounds", 3):
        return "max_reached"
    return "fix"


def _set_max_reached(state: RefinerState) -> dict:
    """Transition node to set verdict when max rounds exceeded."""
    return {"verdict": "max_rounds_reached"}


# ---------------------------------------------------------------------------
# Subgraph builder
# ---------------------------------------------------------------------------


def build_refiner_subgraph():
    """Build and compile the Refiner subgraph.

    Topology:
        static_diagnose -> render_for_compare -> vl_compare -> route_verdict
          - verdict="pass" -> END
          - round >= max_rounds -> set_max_reached -> END
          - verdict="fail" -> coder_fix -> re_execute -> render_for_compare (loop)
    """
    graph = StateGraph(RefinerState)

    # Add nodes
    graph.add_node("static_diagnose", static_diagnose)
    graph.add_node("render_for_compare", render_for_compare)
    graph.add_node("vl_compare", vl_compare)
    graph.add_node("coder_fix", coder_fix)
    graph.add_node("re_execute", re_execute)
    graph.add_node("set_max_reached", _set_max_reached)

    # Set entry
    graph.set_entry_point("static_diagnose")

    # Edges
    graph.add_edge("static_diagnose", "render_for_compare")
    graph.add_edge("render_for_compare", "vl_compare")

    # Conditional routing after vl_compare
    graph.add_conditional_edges(
        "vl_compare",
        _route_verdict,
        {
            "end": END,
            "max_reached": "set_max_reached",
            "fix": "coder_fix",
        },
    )

    graph.add_edge("set_max_reached", END)
    graph.add_edge("coder_fix", "re_execute")
    # Loop: re_execute -> render_for_compare (includes re-render step)
    graph.add_edge("re_execute", "render_for_compare")

    return graph.compile()
