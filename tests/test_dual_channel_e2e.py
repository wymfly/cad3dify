"""End-to-end tests for dual-channel auto fallback.

Creates a demo node with algorithm + mock_neural strategies.
NOT registered to production pipeline.
"""

import pytest

from backend.graph.configs.neural import NeuralStrategyConfig
from backend.graph.context import NodeContext
from backend.graph.descriptor import NodeDescriptor, NodeStrategy


# ---------------------------------------------------------------------------
# Demo strategies (test-only, not registered to production)
# ---------------------------------------------------------------------------

class DemoAlgorithmStrategy(NodeStrategy):
    """Deterministic algorithm strategy — always available."""

    def __init__(self, config=None):
        super().__init__(config)
        self._should_fail = False

    async def execute(self, ctx):
        if self._should_fail:
            raise RuntimeError("algorithm computation failed")
        return {"result": "algorithm_output", "strategy": "algorithm"}


class DemoNeuralStrategy(NodeStrategy):
    """Mock neural strategy — availability controlled by config."""

    def __init__(self, config=None):
        super().__init__(config)

    def check_available(self):
        if self.config is None:
            return False
        return getattr(self.config, "neural_enabled", False)

    async def execute(self, ctx):
        return {"result": "neural_output", "strategy": "neural"}


# ---------------------------------------------------------------------------
# Demo node descriptor factory
# ---------------------------------------------------------------------------

def _make_demo_descriptor():
    async def demo_fn(ctx):
        result = await ctx.execute_with_fallback()
        ctx.put_data("demo_result", result)

    desc = NodeDescriptor(
        name="_test_dual_channel",
        display_name="Test Dual Channel",
        fn=demo_fn,
        strategies={"algorithm": DemoAlgorithmStrategy, "neural": DemoNeuralStrategy},
        fallback_chain=["algorithm", "neural"],
        config_model=NeuralStrategyConfig,
    )
    return desc


# ---------------------------------------------------------------------------
# E2E Tests: Auto Fallback
# ---------------------------------------------------------------------------

class TestDualChannelAutoFallback:
    """Demo node with algorithm + mock_neural in auto mode."""

    @pytest.mark.asyncio
    async def test_algorithm_succeeds_no_fallback(self):
        """Auto mode: algorithm available + succeeds → no fallback."""
        desc = _make_demo_descriptor()
        state = {"pipeline_config": {
            "_test_dual_channel": {"strategy": "auto", "neural_enabled": False},
        }}
        ctx = NodeContext.from_state(state, desc)

        result = await ctx.execute_with_fallback()
        assert result["strategy"] == "algorithm"
        assert ctx._fallback_trace["fallback_triggered"] is False

    @pytest.mark.asyncio
    async def test_algorithm_fails_fallback_to_neural(self):
        """Auto mode: algorithm raises → fallback to neural."""
        desc = _make_demo_descriptor()
        state = {"pipeline_config": {
            "_test_dual_channel": {"strategy": "auto", "neural_enabled": True},
        }}
        ctx = NodeContext.from_state(state, desc)

        # Replace algorithm with failing version
        class FailingAlgo(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                raise RuntimeError("algo error")

        desc.strategies["algorithm"] = FailingAlgo

        result = await ctx.execute_with_fallback()
        assert result["strategy"] == "neural"
        assert ctx._fallback_trace["fallback_triggered"] is True
        attempts = ctx._fallback_trace["strategies_attempted"]
        assert attempts[0]["name"] == "algorithm"
        assert "algo error" in attempts[0]["error"]
        assert attempts[1]["name"] == "neural"
        assert attempts[1]["result"] == "success"

    @pytest.mark.asyncio
    async def test_neural_disabled_auto_only_uses_algorithm(self):
        """Auto mode + neural_enabled=False: only algorithm attempted."""
        desc = _make_demo_descriptor()
        state = {"pipeline_config": {
            "_test_dual_channel": {"strategy": "auto", "neural_enabled": False},
        }}
        ctx = NodeContext.from_state(state, desc)

        result = await ctx.execute_with_fallback()
        assert result["strategy"] == "algorithm"
        trace = ctx._fallback_trace
        assert trace["strategy_used"] == "algorithm"

    @pytest.mark.asyncio
    async def test_explicit_algorithm_selection(self):
        """Explicit strategy='algorithm' bypasses fallback."""
        desc = _make_demo_descriptor()
        state = {"pipeline_config": {
            "_test_dual_channel": {"strategy": "algorithm"},
        }}
        ctx = NodeContext.from_state(state, desc)

        result = await ctx.execute_with_fallback()
        assert result["strategy"] == "algorithm"
        assert ctx._fallback_trace["fallback_triggered"] is False


# ---------------------------------------------------------------------------
# E2E Tests: Trace Integration
# ---------------------------------------------------------------------------

class TestDualChannelTraceIntegration:
    """Trace merge with _wrap_node."""

    @pytest.mark.asyncio
    async def test_trace_contains_fallback_info(self):
        """_wrap_node trace includes fallback_triggered and strategy_used."""
        from backend.graph.builder_new import PipelineBuilder

        class FailAlgo(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                raise RuntimeError("algo error")

        class OkNeural(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                return {"result": "neural"}

        async def demo_fn(ctx):
            return await ctx.execute_with_fallback()

        desc = NodeDescriptor(
            name="_test_trace",
            display_name="Trace Test",
            fn=demo_fn,
            strategies={"algorithm": FailAlgo, "neural": OkNeural},
            fallback_chain=["algorithm", "neural"],
        )

        builder = PipelineBuilder()
        wrapped = builder._wrap_node(desc)

        state = {
            "job_id": "j1", "input_type": "text",
            "assets": {}, "data": {},
            "pipeline_config": {"_test_trace": {"strategy": "auto"}},
            "node_trace": [],
        }
        result = await wrapped(state)

        traces = result["node_trace"]
        assert len(traces) == 1
        entry = traces[0]
        assert "fallback" in entry
        fb = entry["fallback"]
        assert fb["fallback_triggered"] is True
        assert fb["strategy_used"] == "neural"
        assert len(fb["strategies_attempted"]) == 2
