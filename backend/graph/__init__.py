"""LangGraph CAD Job orchestration."""

from __future__ import annotations

__all__ = ["build_graph", "get_compiled_graph"]


def __getattr__(name: str):
    """Lazy import to avoid eagerly loading langgraph at module import time."""
    if name in __all__:
        from backend.graph import builder

        if name == "get_compiled_graph":
            return builder.get_compiled_graph_new
        elif name == "build_graph":
            from backend.graph.discovery import discover_nodes
            from backend.graph.registry import registry
            from backend.graph.resolver import DependencyResolver

            def _build_graph():
                discover_nodes()
                from backend.graph.interceptors import default_registry
                resolved = DependencyResolver.resolve_all(registry, {})
                return builder.PipelineBuilder().build(
                    resolved, interceptor_registry=default_registry,
                ).compile()

            return _build_graph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
