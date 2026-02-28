"""Conditional edge functions for the CadJob StateGraph."""

from __future__ import annotations

from backend.graph.state import CadJobState


def route_by_input_type(state: CadJobState) -> str:
    """Route after create_job_node -> analysis node by input type."""
    return state["input_type"]  # "text" | "drawing" | "organic"


def route_after_confirm(state: CadJobState) -> str:
    """Route after confirm_with_user_node -> generation or finalize."""
    if state.get("status") == "failed":
        return "finalize"
    input_type = state["input_type"]
    if input_type == "organic":
        return "finalize"
    return input_type  # "text" | "drawing"
