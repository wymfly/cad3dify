"""Tests for the compiled CadJob StateGraph."""

from __future__ import annotations

import warnings

import pytest


class TestBuildGraph:
    def test_compile_succeeds(self) -> None:
        from backend.graph.builder import build_graph
        graph = build_graph()
        assert graph is not None

    def test_graph_has_expected_nodes(self) -> None:
        from backend.graph.builder import build_graph
        graph = build_graph()
        node_names = set(graph.nodes.keys())
        expected = {
            "create_job",
            "analyze_intent", "analyze_vision", "analyze_organic",
            "confirm_with_user",
            "generate_step_text", "generate_step_drawing",
            "generate_organic_mesh", "postprocess_organic",
            "convert_preview", "check_printability",
            "finalize",
        }
        assert expected.issubset(node_names), f"Missing: {expected - node_names}"


class TestGetCompiledGraph:
    @pytest.mark.asyncio
    async def test_compiles_with_memory_saver(self) -> None:
        from backend.graph.builder import get_compiled_graph
        graph = await get_compiled_graph()
        assert graph is not None

    @pytest.mark.asyncio
    async def test_compiled_graph_has_checkpointer(self) -> None:
        from backend.graph.builder import get_compiled_graph
        graph = await get_compiled_graph()
        assert graph.checkpointer is not None


class TestGraphExports:
    def test_imports_from_package(self) -> None:
        from backend.graph import build_graph, get_compiled_graph
        assert callable(build_graph)
        assert callable(get_compiled_graph)


class TestBuilderSwitch:
    """Verify USE_NEW_BUILDER env var correctly routes to the right builder."""

    # Core nodes present in both builders (legacy hand-coded + new @register_node).
    CORE_NODES = {
        "create_job",
        "analyze_intent", "analyze_vision", "analyze_organic",
        "confirm_with_user",
        "generate_step_text", "generate_step_drawing",
        "generate_organic_mesh",
        "convert_preview", "check_printability",
        "finalize",
    }

    @pytest.mark.parametrize("use_new", ["0", "1"])
    def test_graph_compiles(self, monkeypatch, use_new) -> None:
        """Both builder modes produce a compilable graph."""
        monkeypatch.setenv("USE_NEW_BUILDER", use_new)
        import backend.graph
        build_fn = backend.graph.__getattr__("build_graph")
        graph = build_fn()
        assert graph is not None

    @pytest.mark.parametrize("use_new", ["0", "1"])
    def test_core_nodes_present(self, monkeypatch, use_new) -> None:
        """Both builder modes include all core pipeline nodes."""
        monkeypatch.setenv("USE_NEW_BUILDER", use_new)
        import backend.graph
        build_fn = backend.graph.__getattr__("build_graph")
        graph = build_fn()
        node_names = set(graph.nodes.keys())
        missing = self.CORE_NODES - node_names
        assert not missing, f"USE_NEW_BUILDER={use_new} missing nodes: {missing}"

    def test_new_builder_has_stub_nodes(self, monkeypatch) -> None:
        """New builder includes @register_node stub nodes that legacy lacks."""
        monkeypatch.setenv("USE_NEW_BUILDER", "1")
        import backend.graph
        build_fn = backend.graph.__getattr__("build_graph")
        graph = build_fn()
        node_names = set(graph.nodes.keys())
        # Nodes registered via @register_node in new builder only
        # Note: boolean_cuts -> boolean_assemble (Phase 2 Task 3)
        # Note: export_formats removed (will be re-added in later phase)
        for stub in ("mesh_healer", "mesh_scale", "boolean_assemble"):
            assert stub in node_names, f"New builder should include node: {stub}"

    def test_legacy_builder_has_postprocess_organic(self, monkeypatch) -> None:
        """Legacy builder has postprocess_organic (uses @timed_node, not @register_node)."""
        monkeypatch.setenv("USE_NEW_BUILDER", "0")
        import backend.graph
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            build_fn = backend.graph.__getattr__("build_graph")
        graph = build_fn()
        assert "postprocess_organic" in set(graph.nodes.keys())

    def test_default_is_new_builder(self, monkeypatch) -> None:
        """Without env var, default is new builder (USE_NEW_BUILDER=1)."""
        monkeypatch.delenv("USE_NEW_BUILDER", raising=False)
        import backend.graph
        build_fn = backend.graph.__getattr__("build_graph")
        graph = build_fn()
        node_names = set(graph.nodes.keys())
        # New builder includes stub nodes, legacy doesn't
        assert "mesh_healer" in node_names, "Default should use new builder"


class TestTraceMerge:
    """_wrap_node merges ctx._fallback_trace into trace entry."""

    @pytest.mark.asyncio
    async def test_fallback_trace_merged_into_node_trace(self):
        from backend.graph.builder_new import PipelineBuilder
        from backend.graph.descriptor import NodeDescriptor

        async def node_with_fallback(ctx):
            # Simulate execute_with_fallback writing trace
            ctx._fallback_trace = {
                "fallback_triggered": True,
                "strategy_used": "neural",
                "strategies_attempted": [
                    {"name": "algorithm", "error": "failed"},
                    {"name": "neural", "result": "success"},
                ],
            }

        desc = NodeDescriptor(
            name="test_trace", display_name="Trace Test", fn=node_with_fallback,
        )
        builder = PipelineBuilder()
        wrapped = builder._wrap_node(desc)

        state = {
            "job_id": "j1", "input_type": "text",
            "assets": {}, "data": {},
            "pipeline_config": {}, "node_trace": [],
        }
        result = await wrapped(state)

        traces = result["node_trace"]
        assert len(traces) == 1
        entry = traces[0]
        assert entry["node"] == "test_trace"
        assert "fallback" in entry
        fb = entry["fallback"]
        assert fb["fallback_triggered"] is True
        assert fb["strategy_used"] == "neural"
        assert len(fb["strategies_attempted"]) == 2
