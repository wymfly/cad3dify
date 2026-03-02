"""PipelineState — the new state schema for plugin-based pipeline nodes.

Key design: assets and data use custom dict-merge reducers so that
each node only returns its incremental additions, and LangGraph merges
them instead of overwriting.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def _merge_dicts(existing: dict, update: dict) -> dict:
    """Custom reducer: shallow-merge dicts instead of overwrite."""
    return {**existing, **update}


class PipelineState(TypedDict, total=False):
    job_id: str
    input_type: str  # "text" | "drawing" | "organic"

    # Asset registry — each value is an AssetEntry-like dict
    assets: Annotated[dict[str, dict[str, Any]], _merge_dicts]
    # Arbitrary data passed between nodes
    data: Annotated[dict[str, Any], _merge_dicts]

    # Per-node configuration: {node_name: {enabled, strategy, ...}}
    pipeline_config: dict[str, dict[str, Any]]

    # Status tracking
    status: str
    error: str | None
    failure_reason: str | None

    # Append-only execution trace
    node_trace: Annotated[list[dict[str, Any]], operator.add]
