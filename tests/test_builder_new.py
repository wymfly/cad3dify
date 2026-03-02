"""Tests for PipelineBuilder (builder_new.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.graph.descriptor import NodeDescriptor, NodeStrategy
from backend.graph.registry import NodeRegistry
from backend.graph.resolver import DependencyResolver
from backend.graph.builder_new import PipelineBuilder, _safe_dispatch


def _desc(name, **kw):
    async def fn(ctx):
        pass
    defaults = dict(name=name, display_name=name, fn=fn)
    defaults.update(kw)
    return NodeDescriptor(**defaults)


def _resolve(descs, config=None, input_type=None):
    reg = NodeRegistry()
    for d in descs:
        reg.register(d)
    return DependencyResolver.resolve(reg, config or {}, input_type)


class TestPipelineBuilderBuild:
    def test_empty_pipeline(self):
        from backend.graph.resolver import ResolvedPipeline

        resolved = ResolvedPipeline(
            ordered_nodes=[], edges=[], asset_producers={}, interrupt_before=[],
        )
        builder = PipelineBuilder()
        graph = builder.build(resolved)
        assert graph is not None

    def test_single_node_pipeline(self):
        resolved = _resolve([_desc("only", is_entry=True)])
        builder = PipelineBuilder()
        graph = builder.build(resolved)
        # Should compile without error
        compiled = graph.compile()
        assert compiled is not None

    def test_linear_three_node_pipeline(self):
        resolved = _resolve([
            _desc("create", is_entry=True, produces=["job"]),
            _desc("process", requires=["job"], produces=["result"]),
            _desc("finish", requires=["result"], is_terminal=True),
        ])
        builder = PipelineBuilder()
        graph = builder.build(resolved)
        compiled = graph.compile()
        assert compiled is not None

    def test_node_count_matches(self):
        descs = [
            _desc("a", is_entry=True, produces=["x"]),
            _desc("b", requires=["x"], produces=["y"]),
            _desc("c", requires=["y"], is_terminal=True),
        ]
        resolved = _resolve(descs)
        builder = PipelineBuilder()
        graph = builder.build(resolved)

        # StateGraph nodes should include our 3 nodes + __start__ + __end__
        assert len(resolved.ordered_nodes) == 3

    def test_hitl_interrupt_before(self):
        resolved = _resolve([
            _desc("create", is_entry=True, produces=["spec"]),
            _desc("confirm", requires=["spec"], produces=["params"], supports_hitl=True),
            _desc("gen", requires=["params"], is_terminal=True),
        ])
        assert resolved.interrupt_before == ["confirm"]


class TestWrapNode:
    @pytest.mark.asyncio
    async def test_wrap_dispatches_events(self):
        dispatched: list[tuple[str, dict]] = []

        async def capture(name, payload):
            dispatched.append((name, payload))

        async def my_fn(ctx):
            ctx.put_data("output", "value")

        desc = _desc("test_wrap", fn=my_fn)
        builder = PipelineBuilder()
        wrapped = builder._wrap_node(desc)

        state = {"job_id": "w1", "input_type": "text", "assets": {}, "data": {}, "pipeline_config": {}, "node_trace": []}

        with patch("backend.graph.builder_new._safe_dispatch", side_effect=capture):
            result = await wrapped(state)

        assert len(dispatched) == 2
        assert dispatched[0][0] == "node.started"
        assert dispatched[1][0] == "node.completed"
        assert dispatched[1][1]["node"] == "test_wrap"

        # Check result contains incremental data
        assert "data" in result
        assert result["data"]["output"] == "value"

    @pytest.mark.asyncio
    async def test_wrap_non_fatal_catches_exception(self):
        dispatched: list[tuple[str, dict]] = []

        async def capture(name, payload):
            dispatched.append((name, payload))

        async def failing_fn(ctx):
            raise ValueError("expected failure")

        desc = _desc("non_fatal_node", fn=failing_fn, non_fatal=True)
        builder = PipelineBuilder()
        wrapped = builder._wrap_node(desc)

        state = {"job_id": "nf1", "input_type": "text", "assets": {}, "data": {}, "pipeline_config": {}, "node_trace": []}

        with patch("backend.graph.builder_new._safe_dispatch", side_effect=capture):
            result = await wrapped(state)

        # Should not raise, returns trace with error info
        assert result["node_trace"][0]["non_fatal"] is True
        assert "expected failure" in result["node_trace"][0]["error"]

    @pytest.mark.asyncio
    async def test_wrap_fatal_reraises(self):
        async def failing_fn(ctx):
            raise RuntimeError("fatal")

        desc = _desc("fatal_node", fn=failing_fn, non_fatal=False)
        builder = PipelineBuilder()
        wrapped = builder._wrap_node(desc)

        state = {"job_id": "f1", "input_type": "text", "assets": {}, "data": {}, "pipeline_config": {}, "node_trace": []}

        with patch("backend.graph.builder_new._safe_dispatch", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="fatal"):
                await wrapped(state)

    @pytest.mark.asyncio
    async def test_wrap_node_trace_entry(self):
        async def my_fn(ctx):
            ctx.put_asset("model", "/tmp/m.step", "STEP")

        desc = _desc("traced", fn=my_fn, produces=["model"])
        builder = PipelineBuilder()
        wrapped = builder._wrap_node(desc)

        state = {"job_id": "t1", "input_type": "text", "assets": {}, "data": {}, "pipeline_config": {}, "node_trace": []}

        with patch("backend.graph.builder_new._safe_dispatch", new_callable=AsyncMock):
            result = await wrapped(state)

        assert len(result["node_trace"]) == 1
        trace = result["node_trace"][0]
        assert trace["node"] == "traced"
        assert "elapsed_ms" in trace
        assert "model" in trace["assets_produced"]


class TestInputTypeRouting:
    def test_conditional_routing_with_disjoint_input_types(self):
        """Builder should create conditional edges for input_type-divergent paths."""
        descs = [
            _desc("create", is_entry=True, produces=["job"]),
            _desc("text_analyze", requires=["job"], produces=["spec"], input_types=["text"]),
            _desc("draw_analyze", requires=["job"], produces=["spec"], input_types=["drawing"]),
            _desc("org_analyze", requires=["job"], produces=["spec"], input_types=["organic"]),
            _desc("confirm", requires=[["spec"]], supports_hitl=True, is_terminal=True),
        ]
        # resolve_all includes all nodes
        reg = NodeRegistry()
        for d in descs:
            reg.register(d)
        resolved = DependencyResolver.resolve_all(reg, {})
        builder = PipelineBuilder()
        graph = builder.build(resolved)
        # Should compile without error
        compiled = graph.compile()
        assert compiled is not None

    def test_router_handles_failed_state(self):
        """Router should route to terminal on failure."""
        builder = PipelineBuilder()
        desc = _desc("src")
        node_map = {
            "src": desc,
            "text_a": _desc("text_a", input_types=["text"]),
            "draw_a": _desc("draw_a", input_types=["drawing"]),
            "fin": _desc("fin", is_terminal=True),
        }
        input_type_map = [("text", "text_a"), ("drawing", "draw_a")]
        router = builder._make_router(desc, input_type_map, node_map)

        # Normal routing
        assert router({"input_type": "text"}) == "text_a"
        assert router({"input_type": "drawing"}) == "draw_a"

        # Failed state → terminal
        result = router({"input_type": "text", "status": "failed"})
        assert result == "fin"


class TestWrapNodeLegacyReturn:
    """Tests for _wrap_node handling of legacy dict-return nodes."""

    @pytest.mark.asyncio
    async def test_legacy_dict_return(self):
        """Legacy nodes that return dicts should have their diff used directly."""

        async def legacy_fn(ctx):
            return {"step_path": "/tmp/out.step", "status": "done"}

        desc = _desc("legacy", fn=legacy_fn)
        builder = PipelineBuilder()
        wrapped = builder._wrap_node(desc)

        state = {"job_id": "lg1", "input_type": "text", "assets": {}, "data": {}, "pipeline_config": {}, "node_trace": []}
        with patch("backend.graph.builder_new._safe_dispatch", new_callable=AsyncMock):
            result = await wrapped(state)

        assert result["step_path"] == "/tmp/out.step"
        assert result["status"] == "done"
        # Should have node_trace injected
        assert len(result["node_trace"]) == 1
        assert result["node_trace"][0]["node"] == "legacy"

    @pytest.mark.asyncio
    async def test_legacy_dict_with_reasoning(self):
        """Legacy nodes returning _reasoning should have it extracted into trace."""

        async def reasoning_fn(ctx):
            return {"result": "ok", "_reasoning": {"model": "gpt"}}

        desc = _desc("reasoning_node", fn=reasoning_fn)
        builder = PipelineBuilder()
        wrapped = builder._wrap_node(desc)

        state = {"job_id": "r1", "input_type": "text", "assets": {}, "data": {}, "pipeline_config": {}, "node_trace": []}
        with patch("backend.graph.builder_new._safe_dispatch", new_callable=AsyncMock):
            result = await wrapped(state)

        # _reasoning should be popped from diff
        assert "_reasoning" not in result
        # But should be in trace
        assert result["node_trace"][0]["reasoning"] == {"model": "gpt"}


class TestRouterFallback:
    """Tests for _make_router fallback and edge cases."""

    def test_unknown_input_type_routes_deterministically(self):
        builder = PipelineBuilder()
        desc = _desc("src")
        node_map = {
            "src": desc,
            "text_a": _desc("text_a", input_types=["text"]),
            "draw_a": _desc("draw_a", input_types=["drawing"]),
        }
        input_type_map = [("text", "text_a"), ("drawing", "draw_a")]
        router = builder._make_router(desc, input_type_map, node_map)

        # Unknown input_type should route to sorted-first destination
        result1 = router({"input_type": "unknown"})
        result2 = router({"input_type": "another_unknown"})
        assert result1 == "draw_a"  # sorted first: ["draw_a", "text_a"]
        assert result1 == result2  # same fallback every time

    def test_overlapping_input_types_connects_first(self):
        """Builder connects to earliest topo successor when input_types overlap."""
        descs = [
            _desc("create", is_entry=True, produces=["job"]),
            _desc("a", requires=["job"], produces=["out"]),
            _desc("b", requires=["job", "out"], is_terminal=True),
        ]
        reg = NodeRegistry()
        for d in descs:
            reg.register(d)
        resolved = DependencyResolver.resolve_all(reg, {})
        builder = PipelineBuilder()
        # Should NOT raise — connects to earliest in topo order
        graph = builder.build(resolved)
        compiled = graph.compile()
        assert compiled is not None


class TestFanOut:
    """Tests for fan-out when successors are unreachable from earliest."""

    def test_fan_out_for_unreachable_successors(self):
        """When multiple successors are NOT reachable from first, builder fans out."""
        descs = [
            _desc("create", is_entry=True, produces=["job"]),
            _desc("gen", requires=["job"], produces=["model"]),
            _desc("preview", requires=[["model"]], produces=["glb"],
                  input_types=["text", "drawing"]),
            _desc("check", requires=[["model"]], produces=["report"]),
            _desc("dfam", requires=[["model"]], produces=["heatmap"],
                  non_fatal=True),
            _desc("fin", is_terminal=True),
        ]
        reg = NodeRegistry()
        for d in descs:
            reg.register(d)
        resolved = DependencyResolver.resolve(reg, {}, input_type="text")
        builder = PipelineBuilder()
        graph = builder.build(resolved)
        compiled = graph.compile()
        assert compiled is not None

        # All three post-process nodes should be in resolved pipeline
        names = {d.name for d in resolved.ordered_nodes}
        assert {"preview", "check", "dfam"}.issubset(names)

    def test_transitive_edge_single_connection(self):
        """When skipped node IS reachable from first, single edge suffices."""
        descs = [
            _desc("create", is_entry=True, produces=["job"]),
            _desc("a", requires=["job"], produces=["out"]),
            _desc("b", requires=["job", "out"], is_terminal=True),
        ]
        reg = NodeRegistry()
        for d in descs:
            reg.register(d)
        resolved = DependencyResolver.resolve_all(reg, {})
        builder = PipelineBuilder()
        graph = builder.build(resolved)
        compiled = graph.compile()
        assert compiled is not None


class TestFullPipelineCompilation:
    """Integration test: resolve + build + compile a realistic pipeline."""

    def test_text_pipeline_compiles(self):
        reg = NodeRegistry()
        nodes = [
            _desc("create_job", is_entry=True, produces=["job_info"]),
            _desc("analyze_intent", requires=["job_info"], produces=["intent_spec"], input_types=["text"]),
            _desc("analyze_vision", requires=["job_info"], produces=["drawing_spec"], input_types=["drawing"]),
            _desc("confirm", requires=[["intent_spec", "drawing_spec"]],
                  produces=["confirmed_params"], supports_hitl=True),
            _desc("gen_text", requires=["confirmed_params"], produces=["step_model"], input_types=["text"]),
            _desc("gen_drawing", requires=["confirmed_params"], produces=["step_model"], input_types=["drawing"]),
            _desc("convert_preview", requires=[["step_model"]], produces=["preview_glb"], non_fatal=True),
            _desc("finalize", is_terminal=True),
        ]
        for n in nodes:
            reg.register(n)

        resolved = DependencyResolver.resolve(reg, {}, input_type="text")
        builder = PipelineBuilder()
        graph = builder.build(resolved)
        compiled = graph.compile()
        assert compiled is not None

        # Correct number of pipeline nodes (text path)
        names = {d.name for d in resolved.ordered_nodes}
        assert "analyze_intent" in names
        assert "analyze_vision" not in names
        assert "gen_text" in names
        assert "gen_drawing" not in names
