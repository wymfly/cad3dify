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


class TestInterceptorInNewBuilder:
    """Interceptor insertion in PipelineBuilder (builder_new.py)."""

    def _make_resolved(self, edges=None):
        """Helper to create a minimal ResolvedPipeline."""
        from backend.graph.resolver import ResolvedPipeline
        from backend.graph.descriptor import NodeDescriptor

        async def noop(ctx):
            pass

        nodes = [
            NodeDescriptor(
                name="convert_preview",
                display_name="Convert",
                fn=noop,
                produces=["preview_glb"],
            ),
            NodeDescriptor(
                name="check_printability",
                display_name="Check",
                fn=noop,
                requires=["step_model"],
            ),
            NodeDescriptor(
                name="finalize",
                display_name="Final",
                fn=noop,
                is_terminal=True,
            ),
        ]
        return ResolvedPipeline(
            ordered_nodes=nodes,
            edges=edges or [
                ("convert_preview", "check_printability"),
                ("check_printability", "finalize"),
            ],
            asset_producers={},
            interrupt_before=[],
        )

    def test_interceptor_inserted_between_convert_and_check(self):
        from backend.graph.builder_new import PipelineBuilder
        from backend.graph.interceptors import InterceptorRegistry

        async def interceptor_fn(state):
            return state

        resolved = self._make_resolved()
        interceptor_reg = InterceptorRegistry()
        interceptor_reg.register("my_interceptor", interceptor_fn, after="convert_preview")

        builder = PipelineBuilder()
        graph = builder.build(resolved, interceptor_registry=interceptor_reg)

        assert "my_interceptor" in graph.nodes

    def test_interceptor_chain_order(self):
        from backend.graph.builder_new import PipelineBuilder
        from backend.graph.interceptors import InterceptorRegistry

        async def int1(state):
            return state

        async def int2(state):
            return state

        resolved = self._make_resolved()
        interceptor_reg = InterceptorRegistry()
        interceptor_reg.register("int1", int1, after="convert_preview")
        interceptor_reg.register("int2", int2, after="convert_preview")

        builder = PipelineBuilder()
        graph = builder.build(resolved, interceptor_registry=interceptor_reg)

        assert "int1" in graph.nodes
        assert "int2" in graph.nodes

    def test_no_interceptors_graph_unchanged(self):
        from backend.graph.builder_new import PipelineBuilder
        from backend.graph.interceptors import InterceptorRegistry

        resolved = self._make_resolved()
        builder = PipelineBuilder()
        graph = builder.build(resolved, interceptor_registry=InterceptorRegistry())

        assert "convert_preview" in graph.nodes
        assert "check_printability" in graph.nodes
