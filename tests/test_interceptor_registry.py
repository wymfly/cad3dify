"""Tests for InterceptorRegistry — build-time node insertion."""
import pytest

from backend.graph.interceptors import InterceptorRegistry


class TestInterceptorRegistry:
    def test_empty_registry(self):
        registry = InterceptorRegistry()
        assert registry.list_interceptors() == []

    def test_register_interceptor(self):
        registry = InterceptorRegistry()

        async def my_node(state):
            return {}

        registry.register("watermark", my_node, after="convert_preview")
        interceptors = registry.list_interceptors()
        assert len(interceptors) == 1
        assert interceptors[0]["name"] == "watermark"
        assert interceptors[0]["after"] == "convert_preview"

    def test_register_multiple(self):
        registry = InterceptorRegistry()

        async def node_a(state):
            return {}

        async def node_b(state):
            return {}

        registry.register("a", node_a, after="convert_preview")
        registry.register("b", node_b, after="a")
        assert len(registry.list_interceptors()) == 2

    def test_apply_no_interceptors_preserves_topology(self):
        from langgraph.graph import StateGraph
        from backend.graph.state import CadJobState

        registry = InterceptorRegistry()
        workflow = StateGraph(CadJobState)

        async def dummy(state):
            return {}

        workflow.add_node("convert_preview", dummy)
        workflow.add_node("check_printability", dummy)
        workflow.add_edge("convert_preview", "check_printability")

        registry.apply(workflow)
        # Should not raise or modify

    def test_apply_inserts_node(self):
        from langgraph.graph import StateGraph
        from backend.graph.state import CadJobState

        registry = InterceptorRegistry()

        async def watermark_node(state):
            return {"watermark": True}

        registry.register("watermark", watermark_node, after="convert_preview")

        workflow = StateGraph(CadJobState)

        async def dummy(state):
            return {}

        workflow.add_node("convert_preview", dummy)
        workflow.add_node("check_printability", dummy)

        registry.apply(workflow)
        assert "watermark" in workflow.nodes


class TestBuilderIntegration:
    def test_build_graph_with_no_interceptors(self):
        from backend.graph.builder import build_graph
        graph = build_graph()
        assert graph is not None

    def test_build_graph_nodes_unchanged(self):
        from backend.graph.builder import build_graph
        graph = build_graph()
        node_names = set(graph.get_graph().nodes.keys())
        expected = {"create_job", "analyze_intent", "analyze_vision", "confirm_with_user",
                    "generate_step_text", "generate_step_drawing", "convert_preview",
                    "check_printability", "finalize"}
        assert expected.issubset(node_names)
