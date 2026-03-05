# Dual-Channel Phase 0 Skeleton — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Extend the LangGraph pipeline strategy mechanism to support `auto` mode with fallback chains, add `NeuralStrategy` base class with HTTP health check, `AssetStore` persistence layer, interceptor support in the new builder, and switch `USE_NEW_BUILDER=1` as default.

**Architecture:** Two-layer fallback design — `get_strategy()` for selection, `execute_with_fallback()` for execution+retry. `NeuralStrategy` base integrates HTTP health check into `check_available()` with class-level TTL cache. `AssetStore` Protocol abstracts file persistence, `LocalAssetStore` implements `file:///` storage. New builder (`builder_new.py`) gets explicit-declaration interceptor insertion, then becomes the default.

**Tech Stack:** Python 3.10+, LangGraph StateGraph, Pydantic v2, pytest, httpx (sync), pathlib

---

## Execution Order

串行执行，按 Task 编号顺序。每个 Task 完成后 commit。

```
Task 1 (descriptor: fallback_chain)
  → Task 2 (NodeStrategy.__init__, get_strategy config injection)
  → Task 3 (get_strategy auto mode)
  → Task 4 (execute_with_fallback + trace merge)
  → Task 5 (NeuralStrategyConfig)
  → Task 6 (NeuralStrategy base class + health check cache)
  → Task 7 (AssetStore Protocol + LocalAssetStore)
  → Task 8 (NodeContext.save_asset integration)
  → Task 9 (interceptor insertion in new builder)
  → Task 10 (builder legacy rename + re-export wrapper)
  → Task 11 (USE_NEW_BUILDER default=1)
  → Task 12 (dual-channel demo node + E2E tests)
  → Task 13 (full test suite + frontend type check)
```

---

### Task 1: NodeDescriptor 新增 fallback_chain + @register_node 参数

**标签:** `[backend]`

**Files:**
- Modify: `backend/graph/descriptor.py:14-40` (NodeDescriptor dataclass)
- Modify: `backend/graph/registry.py:82-131` (register_node decorator)
- Test: `tests/test_descriptor.py` (add new tests)
- Test: `tests/test_registry.py` (add new tests)

**Step 1: Write failing tests for fallback_chain on NodeDescriptor**

在 `tests/test_descriptor.py` 末尾添加：

```python
class TestFallbackChain:
    def test_descriptor_default_empty_fallback_chain(self):
        """NodeDescriptor.fallback_chain defaults to empty list."""
        async def noop(ctx): pass
        desc = NodeDescriptor(name="t", display_name="T", fn=noop)
        assert desc.fallback_chain == []

    def test_descriptor_with_fallback_chain(self):
        async def noop(ctx): pass

        class StratA(NodeStrategy):
            async def execute(self, ctx): pass
        class StratB(NodeStrategy):
            async def execute(self, ctx): pass

        desc = NodeDescriptor(
            name="t", display_name="T", fn=noop,
            strategies={"a": StratA, "b": StratB},
            fallback_chain=["a", "b"],
        )
        assert desc.fallback_chain == ["a", "b"]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_descriptor.py::TestFallbackChain -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'fallback_chain'`

**Step 3: Add fallback_chain field to NodeDescriptor**

In `backend/graph/descriptor.py`, add after line 29 (`default_strategy`):

```python
    fallback_chain: list[str] = field(default_factory=list)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_descriptor.py::TestFallbackChain -v`
Expected: PASS

**Step 5: Write failing tests for register_node fallback_chain validation**

在 `tests/test_registry.py` 末尾添加：

```python
class TestRegisterNodeFallbackChain:
    def test_register_with_valid_fallback_chain(self):
        """fallback_chain names must all exist in strategies."""
        from backend.graph.registry import NodeRegistry

        class StratA(NodeStrategy):
            async def execute(self, ctx): pass
        class StratB(NodeStrategy):
            async def execute(self, ctx): pass

        reg = NodeRegistry()

        @register_node(
            name="_test_fb_valid",
            display_name="Test FB",
            strategies={"a": StratA, "b": StratB},
            fallback_chain=["a", "b"],
        )
        async def node_fn(ctx): pass

        desc = node_fn._node_descriptor
        assert desc.fallback_chain == ["a", "b"]
        # cleanup
        from backend.graph.registry import registry
        registry._remove("_test_fb_valid")

    def test_register_with_invalid_fallback_chain_raises(self):
        """fallback_chain with nonexistent strategy name raises ValueError."""
        class StratA(NodeStrategy):
            async def execute(self, ctx): pass

        with pytest.raises(ValueError, match="nonexistent"):
            @register_node(
                name="_test_fb_invalid",
                display_name="Test FB",
                strategies={"a": StratA},
                fallback_chain=["a", "nonexistent"],
            )
            async def node_fn(ctx): pass

    def test_register_without_fallback_chain(self):
        """No fallback_chain → empty list."""
        @register_node(name="_test_fb_none", display_name="Test")
        async def node_fn(ctx): pass

        desc = node_fn._node_descriptor
        assert desc.fallback_chain == []
        from backend.graph.registry import registry
        registry._remove("_test_fb_none")
```

**Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_registry.py::TestRegisterNodeFallbackChain -v`
Expected: FAIL — `register_node() got an unexpected keyword argument 'fallback_chain'` (for first test), second test should also fail since validation isn't there.

**Step 7: Add fallback_chain to register_node decorator**

In `backend/graph/registry.py`, add parameter `fallback_chain: list[str] | None = None` to `register_node()` signature (after `default_strategy`).

In the `decorator` inner function, before `registry.register(desc)`, add validation:

```python
        chain = fallback_chain or []
        strats = strategies or {}
        if chain:
            invalid = [n for n in chain if n not in strats]
            if invalid:
                raise ValueError(
                    f"fallback_chain contains unknown strategy names: {invalid}. "
                    f"Available strategies: {list(strats.keys())}"
                )

        desc = NodeDescriptor(
            ...
            fallback_chain=chain,
            ...
        )
```

**Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_registry.py::TestRegisterNodeFallbackChain tests/test_descriptor.py::TestFallbackChain -v`
Expected: PASS

**Step 9: Run existing test suite to verify no regressions**

Run: `uv run pytest tests/test_descriptor.py tests/test_registry.py tests/test_context.py -v`
Expected: All PASS

**Step 10: Commit**

```bash
git add backend/graph/descriptor.py backend/graph/registry.py tests/test_descriptor.py tests/test_registry.py
git commit -m "feat(graph): add fallback_chain to NodeDescriptor and @register_node

NodeDescriptor gets a new fallback_chain: list[str] field (default empty).
@register_node validates all chain names exist in strategies dict."
```

---

### Task 2: NodeStrategy.__init__ 默认实现 + get_strategy 构造函数注入

**标签:** `[backend]`

**Files:**
- Modify: `backend/graph/descriptor.py:51-61` (NodeStrategy class)
- Modify: `backend/graph/context.py:185-202` (get_strategy method)
- Test: `tests/test_context.py` (add/update tests)

**Step 1: Write failing test for config injection into strategy**

在 `tests/test_context.py` 的 `TestNodeContextStrategy` 类末尾添加：

```python
    def test_strategy_receives_config(self):
        """get_strategy() passes config to strategy constructor."""

        class ConfigAwareStrategy(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
                self.received_config = config

            async def execute(self, ctx):
                return "ok"

        desc = _make_descriptor(
            strategies={"aware": ConfigAwareStrategy},
        )
        state = {"pipeline_config": {"test_node": {"strategy": "aware"}}}
        ctx = NodeContext.from_state(state, desc)
        strategy = ctx.get_strategy()

        assert isinstance(strategy, ConfigAwareStrategy)
        assert strategy.received_config is ctx.config

    def test_no_arg_strategy_still_works(self):
        """Existing strategies without config param still work."""

        class LegacyStrategy(NodeStrategy):
            async def execute(self, ctx):
                return "legacy"

        desc = _make_descriptor(strategies={"legacy": LegacyStrategy})
        state = {"pipeline_config": {"test_node": {"strategy": "legacy"}}}
        ctx = NodeContext.from_state(state, desc)
        strategy = ctx.get_strategy()
        assert isinstance(strategy, LegacyStrategy)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_context.py::TestNodeContextStrategy::test_strategy_receives_config tests/test_context.py::TestNodeContextStrategy::test_no_arg_strategy_still_works -v`
Expected: FAIL — `super().__init__()` will fail because `NodeStrategy.__init__` doesn't exist, and `strategies[name]()` doesn't pass config.

**Step 3: Add __init__ to NodeStrategy base class**

In `backend/graph/descriptor.py`, modify `NodeStrategy`:

```python
class NodeStrategy(ABC):
    """Base class for pluggable node execution strategies."""

    def __init__(self, config=None):
        self.config = config

    @abstractmethod
    async def execute(self, ctx: Any) -> Any:
        """Execute the strategy with the given node context."""
        ...

    def check_available(self) -> bool:
        """Check if this strategy's runtime dependencies are available."""
        return True
```

**Step 4: Update get_strategy to inject config**

In `backend/graph/context.py`, line 196, change:

```python
        instance = strategies[strategy_name]()
```

to:

```python
        instance = strategies[strategy_name](config=self.config)
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_context.py::TestNodeContextStrategy -v`
Expected: All PASS (including existing tests)

**Step 6: Run full context + descriptor tests**

Run: `uv run pytest tests/test_context.py tests/test_descriptor.py -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add backend/graph/descriptor.py backend/graph/context.py tests/test_context.py
git commit -m "feat(graph): add NodeStrategy.__init__(config) + inject config in get_strategy

NodeStrategy base class gets __init__(self, config=None) for safe
constructor injection. get_strategy() now passes config=self.config
when instantiating strategies."
```

---

### Task 3: get_strategy() 扩展 auto 模式（选择层）

**标签:** `[backend]`

**Files:**
- Modify: `backend/graph/context.py:185-202` (get_strategy method)
- Test: `tests/test_context.py` (add auto mode tests)

**Step 1: Write failing tests for auto mode selection**

在 `tests/test_context.py` 添加新测试类：

```python
class TestGetStrategyAutoMode:
    """Tests for get_strategy() auto mode — selection layer only."""

    def _make_strategies(self):
        class AlgoStrategy(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                return "algo"

        class NeuralStrategy(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                return "neural"
            def check_available(self):
                return False  # unavailable by default

        return {"algorithm": AlgoStrategy, "neural": NeuralStrategy}

    def test_auto_selects_first_available(self):
        strategies = self._make_strategies()
        desc = _make_descriptor(
            strategies=strategies,
            fallback_chain=["algorithm", "neural"],
        )
        state = {"pipeline_config": {"test_node": {"strategy": "auto"}}}
        ctx = NodeContext.from_state(state, desc)

        strategy = ctx.get_strategy()
        assert type(strategy).__name__ == "AlgoStrategy"

    def test_auto_skips_unavailable(self):
        strategies = self._make_strategies()

        # Make algorithm unavailable too
        class UnavailableAlgo(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                return "algo"
            def check_available(self):
                return False

        class AvailableNeural(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                return "neural"

        desc = _make_descriptor(
            strategies={"algorithm": UnavailableAlgo, "neural": AvailableNeural},
            fallback_chain=["algorithm", "neural"],
        )
        state = {"pipeline_config": {"test_node": {"strategy": "auto"}}}
        ctx = NodeContext.from_state(state, desc)

        strategy = ctx.get_strategy()
        assert type(strategy).__name__ == "AvailableNeural"

    def test_auto_all_unavailable_raises(self):
        class BadStrat(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                pass
            def check_available(self):
                return False

        desc = _make_descriptor(
            strategies={"a": BadStrat, "b": BadStrat},
            fallback_chain=["a", "b"],
        )
        state = {"pipeline_config": {"test_node": {"strategy": "auto"}}}
        ctx = NodeContext.from_state(state, desc)

        with pytest.raises(RuntimeError, match="unavailable"):
            ctx.get_strategy()

    def test_auto_no_fallback_chain_raises(self):
        class Strat(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                pass

        desc = _make_descriptor(
            strategies={"a": Strat},
            fallback_chain=[],  # empty
        )
        state = {"pipeline_config": {"test_node": {"strategy": "auto"}}}
        ctx = NodeContext.from_state(state, desc)

        with pytest.raises(ValueError, match="no fallback chain"):
            ctx.get_strategy()

    def test_explicit_strategy_unchanged(self):
        """Non-auto mode should work exactly as before."""
        strategies = self._make_strategies()
        desc = _make_descriptor(
            strategies=strategies,
            fallback_chain=["algorithm", "neural"],
        )
        state = {"pipeline_config": {"test_node": {"strategy": "algorithm"}}}
        ctx = NodeContext.from_state(state, desc)

        strategy = ctx.get_strategy()
        assert type(strategy).__name__ == "AlgoStrategy"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_context.py::TestGetStrategyAutoMode -v`
Expected: FAIL — `get_strategy()` doesn't handle `strategy="auto"`

**Step 3: Implement auto mode in get_strategy()**

Replace `get_strategy()` in `backend/graph/context.py`:

```python
    def get_strategy(self) -> NodeStrategy:
        """Instantiate the strategy selected by current config.

        For strategy="auto", iterates fallback_chain and returns the first
        strategy where check_available() returns True (selection only,
        does not call execute()).
        """
        strategy_name = self.config.strategy
        strategies = self.descriptor.strategies

        if not strategies:
            raise ValueError(f"Node '{self.node_name}' has no strategies defined")

        # Auto mode: iterate fallback_chain
        if strategy_name == "auto":
            chain = self.descriptor.fallback_chain
            if not chain:
                raise ValueError(
                    f"Node '{self.node_name}' has strategy='auto' but "
                    f"no fallback chain configured"
                )
            reasons = []
            for name in chain:
                if name not in strategies:
                    reasons.append(f"{name}: not in strategies")
                    continue
                instance = strategies[name](config=self.config)
                if instance.check_available():
                    return instance
                reasons.append(f"{name}: unavailable (check returned False)")

            reason_str = "; ".join(reasons)
            raise RuntimeError(
                f"No available strategy for '{self.node_name}' in auto mode. "
                f"Tried: {reason_str}"
            )

        # Explicit mode: direct lookup
        if strategy_name not in strategies:
            raise ValueError(
                f"Strategy '{strategy_name}' not found for '{self.node_name}'. "
                f"Available: {list(strategies.keys())}"
            )
        instance = strategies[strategy_name](config=self.config)
        if not instance.check_available():
            raise RuntimeError(
                f"Strategy '{strategy_name}' is not available "
                f"(runtime dependency missing)"
            )
        return instance
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_context.py::TestGetStrategyAutoMode tests/test_context.py::TestNodeContextStrategy -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/graph/context.py tests/test_context.py
git commit -m "feat(graph): extend get_strategy() with auto mode selection

Auto mode iterates fallback_chain, returns first strategy where
check_available()=True. No fallback_chain configured raises ValueError.
All unavailable raises RuntimeError with reason list."
```

---

### Task 4: execute_with_fallback() + trace 合并

**标签:** `[backend]`

**Files:**
- Modify: `backend/graph/context.py` (add execute_with_fallback, _fallback_trace)
- Modify: `backend/graph/builder_new.py:93-161` (_wrap_node trace merge)
- Test: `tests/test_context.py` (add fallback execution tests)
- Test: `tests/test_graph_builder.py` (add trace merge test)

**Step 1: Write failing tests for execute_with_fallback()**

在 `tests/test_context.py` 添加：

```python
class TestExecuteWithFallback:
    """Tests for execute_with_fallback() — execution layer."""

    @pytest.mark.asyncio
    async def test_auto_first_succeeds_no_fallback(self):
        class AlgoStrat(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                return {"result": "algo"}

        desc = _make_descriptor(
            strategies={"algorithm": AlgoStrat},
            fallback_chain=["algorithm"],
        )
        state = {"pipeline_config": {"test_node": {"strategy": "auto"}}}
        ctx = NodeContext.from_state(state, desc)

        result = await ctx.execute_with_fallback()
        assert result == {"result": "algo"}
        assert ctx._fallback_trace["fallback_triggered"] is False
        assert ctx._fallback_trace["strategy_used"] == "algorithm"

    @pytest.mark.asyncio
    async def test_auto_fallback_on_execute_failure(self):
        class FailAlgo(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                raise RuntimeError("algo failed")

        class OkNeural(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                return {"result": "neural"}

        desc = _make_descriptor(
            strategies={"algorithm": FailAlgo, "neural": OkNeural},
            fallback_chain=["algorithm", "neural"],
        )
        state = {"pipeline_config": {"test_node": {"strategy": "auto"}}}
        ctx = NodeContext.from_state(state, desc)

        result = await ctx.execute_with_fallback()
        assert result == {"result": "neural"}
        assert ctx._fallback_trace["fallback_triggered"] is True
        attempts = ctx._fallback_trace["strategies_attempted"]
        assert attempts[0]["name"] == "algorithm"
        assert "algo failed" in attempts[0]["error"]
        assert attempts[1]["name"] == "neural"
        assert attempts[1]["result"] == "success"

    @pytest.mark.asyncio
    async def test_auto_all_fail_raises(self):
        class FailStrat(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                raise RuntimeError(f"fail")
            def check_available(self):
                return True

        class UnavailStrat(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                pass
            def check_available(self):
                return False

        desc = _make_descriptor(
            strategies={"a": FailStrat, "b": UnavailStrat},
            fallback_chain=["a", "b"],
        )
        state = {"pipeline_config": {"test_node": {"strategy": "auto"}}}
        ctx = NodeContext.from_state(state, desc)

        with pytest.raises(RuntimeError, match="No strategy succeeded"):
            await ctx.execute_with_fallback()

        attempts = ctx._fallback_trace["strategies_attempted"]
        assert len(attempts) == 2
        assert "fail" in attempts[0]["error"]
        assert "unavailable" in attempts[1]["error"]

    @pytest.mark.asyncio
    async def test_non_auto_delegates_directly(self):
        class DirectStrat(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                return {"result": "direct"}

        desc = _make_descriptor(strategies={"direct": DirectStrat})
        state = {"pipeline_config": {"test_node": {"strategy": "direct"}}}
        ctx = NodeContext.from_state(state, desc)

        result = await ctx.execute_with_fallback()
        assert result == {"result": "direct"}

    @pytest.mark.asyncio
    async def test_auto_skips_unavailable_then_succeeds(self):
        class UnavailAlgo(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                return {"result": "algo"}
            def check_available(self):
                return False

        class OkNeural(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                return {"result": "neural"}

        desc = _make_descriptor(
            strategies={"algorithm": UnavailAlgo, "neural": OkNeural},
            fallback_chain=["algorithm", "neural"],
        )
        state = {"pipeline_config": {"test_node": {"strategy": "auto"}}}
        ctx = NodeContext.from_state(state, desc)

        result = await ctx.execute_with_fallback()
        assert result == {"result": "neural"}
        assert ctx._fallback_trace["fallback_triggered"] is True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_context.py::TestExecuteWithFallback -v`
Expected: FAIL — `NodeContext has no attribute '_fallback_trace'` / `execute_with_fallback`

**Step 3: Implement execute_with_fallback() on NodeContext**

In `backend/graph/context.py`, add `_fallback_trace` to `__init__`:

```python
        self._fallback_trace: dict[str, Any] | None = None
```

Add the method after `get_strategy()`:

```python
    async def execute_with_fallback(self) -> Any:
        """Execute strategy with fallback support.

        Auto mode: independently iterates fallback_chain, calling
        check_available() + execute() on each. First success returns.
        Non-auto: delegates to get_strategy().execute(self).
        """
        strategy_name = self.config.strategy

        if strategy_name != "auto":
            strategy = self.get_strategy()
            result = await strategy.execute(self)
            self._fallback_trace = {
                "fallback_triggered": False,
                "strategy_used": strategy_name,
            }
            return result

        # Auto mode: independent traversal
        chain = self.descriptor.fallback_chain
        strategies = self.descriptor.strategies

        if not chain:
            raise ValueError(
                f"Node '{self.node_name}' has strategy='auto' but "
                f"no fallback chain configured"
            )

        attempts: list[dict[str, Any]] = []
        for name in chain:
            if name not in strategies:
                attempts.append({"name": name, "error": "not in strategies"})
                continue

            instance = strategies[name](config=self.config)

            if not instance.check_available():
                attempts.append({
                    "name": name,
                    "error": "unavailable (check returned False)",
                })
                continue

            try:
                result = await instance.execute(self)
                attempts.append({"name": name, "result": "success"})
                self._fallback_trace = {
                    "fallback_triggered": len(attempts) > 1,
                    "strategy_used": name,
                    "strategies_attempted": attempts,
                }
                return result
            except Exception as exc:
                attempts.append({"name": name, "error": str(exc)})
                logger.warning(
                    "Strategy '%s' failed for node '%s': %s",
                    name, self.node_name, exc,
                )
                continue

        self._fallback_trace = {
            "fallback_triggered": True,
            "strategy_used": None,
            "strategies_attempted": attempts,
        }
        reasons = "; ".join(f"{a['name']}: {a.get('error', '?')}" for a in attempts)
        raise RuntimeError(
            f"No strategy succeeded for '{self.node_name}' in auto mode. "
            f"Attempted: {reasons}"
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_context.py::TestExecuteWithFallback -v`
Expected: All PASS

**Step 5: Write failing test for trace merge in _wrap_node**

In `tests/test_graph_builder.py`, add:

```python
class TestTraceMerge:
    """_wrap_node merges ctx._fallback_trace into trace entry."""

    @pytest.mark.asyncio
    async def test_fallback_trace_merged_into_node_trace(self):
        from backend.graph.builder_new import PipelineBuilder

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
            name="test_trace", display_name="Test Trace", fn=node_with_fallback,
        )
        builder = PipelineBuilder()
        wrapped = builder._wrap_node(desc)

        state = {"job_id": "j1", "input_type": "text", "assets": {}, "data": {}, "pipeline_config": {}, "node_trace": []}
        result = await wrapped(state)

        traces = result["node_trace"]
        assert len(traces) == 1
        entry = traces[0]
        assert entry["node"] == "test_trace"
        assert entry["fallback_triggered"] is True
        assert entry["strategy_used"] == "neural"
        assert len(entry["strategies_attempted"]) == 2
```

**Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_graph_builder.py::TestTraceMerge -v`
Expected: FAIL — `_wrap_node` doesn't merge `_fallback_trace`

**Step 7: Modify _wrap_node to merge fallback trace**

In `backend/graph/builder_new.py`, inside `_wrap_node`, after building `trace_entry` (around line 124), add:

```python
                # Merge fallback trace if present
                if hasattr(ctx, '_fallback_trace') and ctx._fallback_trace:
                    trace_entry.update(ctx._fallback_trace)
```

**Step 8: Run all trace and fallback tests**

Run: `uv run pytest tests/test_context.py::TestExecuteWithFallback tests/test_graph_builder.py::TestTraceMerge -v`
Expected: All PASS

**Step 9: Run existing test suite for regressions**

Run: `uv run pytest tests/test_context.py tests/test_graph_builder.py -v`
Expected: All PASS

**Step 10: Commit**

```bash
git add backend/graph/context.py backend/graph/builder_new.py tests/test_context.py tests/test_graph_builder.py
git commit -m "feat(graph): add execute_with_fallback() + trace merge in _wrap_node

execute_with_fallback() independently traverses fallback_chain in auto mode,
calling check_available() + execute() on each strategy. Fallback trace is
stored in ctx._fallback_trace and merged by _wrap_node into a single
node_trace entry per node."
```

---

### Task 5: NeuralStrategyConfig Pydantic 模型

**标签:** `[backend]`

**Files:**
- Create: `backend/graph/configs/__init__.py` (if missing)
- Create: `backend/graph/configs/neural.py`
- Test: `tests/test_neural_config.py`

**Step 1: Write failing test for NeuralStrategyConfig**

Create `tests/test_neural_config.py`:

```python
"""Tests for NeuralStrategyConfig."""

import pytest

from backend.graph.configs.base import BaseNodeConfig


class TestNeuralStrategyConfig:
    def test_defaults(self):
        from backend.graph.configs.neural import NeuralStrategyConfig

        cfg = NeuralStrategyConfig()
        assert cfg.neural_enabled is False
        assert cfg.neural_endpoint is None
        assert cfg.neural_timeout == 60
        assert cfg.health_check_path == "/health"
        # Inherited from BaseNodeConfig
        assert cfg.enabled is True
        assert cfg.strategy == "default"

    def test_custom_values(self):
        from backend.graph.configs.neural import NeuralStrategyConfig

        cfg = NeuralStrategyConfig(
            neural_enabled=True,
            neural_endpoint="http://gpu:8090",
            neural_timeout=30,
            health_check_path="/healthz",
            strategy="auto",
        )
        assert cfg.neural_enabled is True
        assert cfg.neural_endpoint == "http://gpu:8090"
        assert cfg.neural_timeout == 30
        assert cfg.health_check_path == "/healthz"
        assert cfg.strategy == "auto"

    def test_is_subclass_of_base(self):
        from backend.graph.configs.neural import NeuralStrategyConfig

        assert issubclass(NeuralStrategyConfig, BaseNodeConfig)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_neural_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.graph.configs.neural'`

**Step 3: Create NeuralStrategyConfig**

Check if `backend/graph/configs/__init__.py` exists, create if not.

Create `backend/graph/configs/neural.py`:

```python
"""Neural strategy configuration model."""

from backend.graph.configs.base import BaseNodeConfig


class NeuralStrategyConfig(BaseNodeConfig):
    """Configuration for nodes that support Neural channel strategies.

    Extends BaseNodeConfig with neural-specific fields.
    """

    neural_enabled: bool = False
    neural_endpoint: str | None = None
    neural_timeout: int = 60
    health_check_path: str = "/health"
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_neural_config.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/graph/configs/neural.py tests/test_neural_config.py
git commit -m "feat(graph): add NeuralStrategyConfig extending BaseNodeConfig

NeuralStrategyConfig adds neural_enabled, neural_endpoint, neural_timeout,
and health_check_path fields for Neural channel configuration."
```

---

### Task 6: NeuralStrategy 基类 + 健康检查缓存

**标签:** `[backend]`

**Files:**
- Create: `backend/graph/strategies/__init__.py`
- Create: `backend/graph/strategies/neural.py`
- Test: `tests/test_neural_strategy.py`

**Step 1: Write failing tests for NeuralStrategy**

Create `tests/test_neural_strategy.py`:

```python
"""Tests for NeuralStrategy base class with HTTP health check + cache."""

import pytest
from unittest.mock import patch, MagicMock

from backend.graph.configs.neural import NeuralStrategyConfig
from backend.graph.descriptor import NodeStrategy


class TestNeuralStrategyThreeStates:
    """Three-state design: disabled / available / degraded."""

    def test_disabled_when_not_enabled(self):
        from backend.graph.strategies.neural import NeuralStrategy, _health_cache

        _health_cache.clear()

        class ConcreteNeural(NeuralStrategy):
            async def execute(self, ctx):
                return "neural"

        cfg = NeuralStrategyConfig(neural_enabled=False)
        s = ConcreteNeural(config=cfg)
        assert s.check_available() is False

    def test_disabled_when_no_endpoint(self):
        from backend.graph.strategies.neural import NeuralStrategy, _health_cache

        _health_cache.clear()

        class ConcreteNeural(NeuralStrategy):
            async def execute(self, ctx):
                return "neural"

        cfg = NeuralStrategyConfig(neural_enabled=True, neural_endpoint=None)
        s = ConcreteNeural(config=cfg)
        assert s.check_available() is False

    @patch("backend.graph.strategies.neural.httpx")
    def test_available_when_health_ok(self, mock_httpx):
        from backend.graph.strategies.neural import NeuralStrategy, _health_cache

        _health_cache.clear()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp

        class ConcreteNeural(NeuralStrategy):
            async def execute(self, ctx):
                return "neural"

        cfg = NeuralStrategyConfig(
            neural_enabled=True, neural_endpoint="http://gpu:8090",
        )
        s = ConcreteNeural(config=cfg)
        assert s.check_available() is True
        mock_httpx.get.assert_called_once_with(
            "http://gpu:8090/health", timeout=5,
        )

    @patch("backend.graph.strategies.neural.httpx")
    def test_degraded_when_health_fails(self, mock_httpx):
        from backend.graph.strategies.neural import NeuralStrategy, _health_cache

        _health_cache.clear()

        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_httpx.get.return_value = mock_resp

        class ConcreteNeural(NeuralStrategy):
            async def execute(self, ctx):
                return "neural"

        cfg = NeuralStrategyConfig(
            neural_enabled=True, neural_endpoint="http://gpu:8090",
        )
        s = ConcreteNeural(config=cfg)
        assert s.check_available() is False

    @patch("backend.graph.strategies.neural.httpx")
    def test_degraded_when_http_exception(self, mock_httpx):
        from backend.graph.strategies.neural import NeuralStrategy, _health_cache

        _health_cache.clear()

        import httpx as real_httpx
        mock_httpx.get.side_effect = Exception("connection refused")

        class ConcreteNeural(NeuralStrategy):
            async def execute(self, ctx):
                return "neural"

        cfg = NeuralStrategyConfig(
            neural_enabled=True, neural_endpoint="http://gpu:8090",
        )
        s = ConcreteNeural(config=cfg)
        assert s.check_available() is False


class TestHealthCheckCache:
    """Cache is class/module-level, keyed by (endpoint, health_check_path)."""

    @patch("backend.graph.strategies.neural.httpx")
    def test_cache_hit_within_ttl(self, mock_httpx):
        from backend.graph.strategies.neural import NeuralStrategy, _health_cache, _clock

        _health_cache.clear()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp

        class ConcreteNeural(NeuralStrategy):
            async def execute(self, ctx):
                return "neural"

        cfg = NeuralStrategyConfig(
            neural_enabled=True, neural_endpoint="http://gpu:8090",
        )

        s1 = ConcreteNeural(config=cfg)
        assert s1.check_available() is True

        # Second call on different instance — should use cache
        s2 = ConcreteNeural(config=cfg)
        assert s2.check_available() is True

        # Only one HTTP call
        assert mock_httpx.get.call_count == 1

    @patch("backend.graph.strategies.neural.httpx")
    def test_cache_expired_triggers_new_check(self, mock_httpx):
        from backend.graph.strategies.neural import (
            NeuralStrategy, _health_cache, _CACHE_TTL,
        )
        import backend.graph.strategies.neural as neural_mod

        _health_cache.clear()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp

        class ConcreteNeural(NeuralStrategy):
            async def execute(self, ctx):
                return "neural"

        cfg = NeuralStrategyConfig(
            neural_enabled=True, neural_endpoint="http://gpu:8090",
        )

        fake_time = [100.0]
        original_clock = neural_mod._clock
        neural_mod._clock = lambda: fake_time[0]

        try:
            s1 = ConcreteNeural(config=cfg)
            assert s1.check_available() is True
            assert mock_httpx.get.call_count == 1

            # Advance past TTL
            fake_time[0] = 100.0 + _CACHE_TTL + 1
            s2 = ConcreteNeural(config=cfg)
            assert s2.check_available() is True
            assert mock_httpx.get.call_count == 2
        finally:
            neural_mod._clock = original_clock

    @patch("backend.graph.strategies.neural.httpx")
    def test_different_endpoints_isolated(self, mock_httpx):
        from backend.graph.strategies.neural import NeuralStrategy, _health_cache

        _health_cache.clear()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp

        class ConcreteNeural(NeuralStrategy):
            async def execute(self, ctx):
                return "neural"

        cfg1 = NeuralStrategyConfig(
            neural_enabled=True, neural_endpoint="http://gpu1:8090",
        )
        cfg2 = NeuralStrategyConfig(
            neural_enabled=True, neural_endpoint="http://gpu2:8090",
        )

        ConcreteNeural(config=cfg1).check_available()
        ConcreteNeural(config=cfg2).check_available()

        # Two different HTTP calls
        assert mock_httpx.get.call_count == 2


class TestNeuralStrategyInheritance:
    def test_is_subclass_of_node_strategy(self):
        from backend.graph.strategies.neural import NeuralStrategy

        assert issubclass(NeuralStrategy, NodeStrategy)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_neural_strategy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.graph.strategies'`

**Step 3: Create strategies package and NeuralStrategy**

Create `backend/graph/strategies/__init__.py`:

```python
"""Strategy implementations for pipeline nodes."""
```

Create `backend/graph/strategies/neural.py`:

```python
"""NeuralStrategy base class with HTTP health check and TTL cache."""

from __future__ import annotations

import logging
import time
from abc import abstractmethod
from typing import Any

import httpx

from backend.graph.descriptor import NodeStrategy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level health check cache
# ---------------------------------------------------------------------------

_CACHE_TTL = 30  # seconds

# Injectable clock for testing
_clock = time.monotonic

# Cache: (endpoint, health_check_path) → (result: bool, timestamp: float)
_health_cache: dict[tuple[str, str], tuple[bool, float]] = {}


class NeuralStrategy(NodeStrategy):
    """Base class for Neural channel strategies.

    Integrates HTTP health check into check_available() with
    class-level TTL cache.
    """

    def __init__(self, config=None):
        super().__init__(config)

    def check_available(self) -> bool:
        """Three-state check: disabled → False, available → True, degraded → False."""
        if self.config is None:
            return False

        neural_enabled = getattr(self.config, "neural_enabled", False)
        neural_endpoint = getattr(self.config, "neural_endpoint", None)

        # Disabled state
        if not neural_enabled or not neural_endpoint:
            return False

        health_path = getattr(self.config, "health_check_path", "/health")
        cache_key = (neural_endpoint, health_path)

        # Check cache
        if cache_key in _health_cache:
            cached_result, cached_time = _health_cache[cache_key]
            if _clock() - cached_time < _CACHE_TTL:
                return cached_result

        # Perform health check
        url = f"{neural_endpoint.rstrip('/')}{health_path}"
        try:
            resp = httpx.get(url, timeout=5)
            result = resp.status_code == 200
        except Exception as exc:
            logger.warning("Health check failed for %s: %s", url, exc)
            result = False

        _health_cache[cache_key] = (result, _clock())
        return result

    @abstractmethod
    async def execute(self, ctx: Any) -> Any:
        """Subclasses implement the actual neural inference call."""
        ...
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_neural_strategy.py -v`
Expected: All PASS

**Step 5: Verify httpx is available**

Run: `uv run python -c "import httpx; print(httpx.__version__)"`

If not installed:

Run: `uv add httpx`

**Step 6: Commit**

```bash
git add backend/graph/strategies/__init__.py backend/graph/strategies/neural.py tests/test_neural_strategy.py
git commit -m "feat(graph): add NeuralStrategy base class with HTTP health check

NeuralStrategy extends NodeStrategy with check_available() that performs
HTTP health check (GET {endpoint}/health, 5s timeout). Module-level cache
keyed by (endpoint, health_check_path) with 30s TTL. Injectable _clock
for testing. Three-state design: disabled/available/degraded."
```

---

### Task 7: AssetStore Protocol + LocalAssetStore

**标签:** `[backend]`

**Files:**
- Create: `backend/graph/asset_store.py`
- Test: `tests/test_asset_store.py`

**Step 1: Write failing tests for AssetStore**

Create `tests/test_asset_store.py`:

```python
"""Tests for AssetStore Protocol and LocalAssetStore implementation."""

import os
import pytest
from pathlib import Path


class TestLocalAssetStoreSaveLoad:
    def test_save_and_load(self, tmp_path):
        from backend.graph.asset_store import LocalAssetStore

        store = LocalAssetStore(workspace=tmp_path)
        data = b"mesh data here"
        uri = store.save(job_id="j1", name="mesh", data=data, fmt="obj")

        assert "j1" in uri
        assert "mesh.obj" in uri

        loaded = store.load(uri)
        assert loaded == data

    def test_load_nonexistent_raises(self, tmp_path):
        from backend.graph.asset_store import LocalAssetStore

        store = LocalAssetStore(workspace=tmp_path)
        with pytest.raises(FileNotFoundError):
            store.load(f"file://{tmp_path}/jobs/nonexistent/mesh.obj")

    def test_directory_auto_created(self, tmp_path):
        from backend.graph.asset_store import LocalAssetStore

        store = LocalAssetStore(workspace=tmp_path)
        store.save(job_id="deep/job", name="out", data=b"x", fmt="stl")
        # Should not raise — directory created automatically

    def test_overwrite_existing(self, tmp_path):
        from backend.graph.asset_store import LocalAssetStore

        store = LocalAssetStore(workspace=tmp_path)
        uri1 = store.save(job_id="j1", name="mesh", data=b"old", fmt="obj")
        uri2 = store.save(job_id="j1", name="mesh", data=b"new", fmt="obj")

        assert uri1 == uri2
        assert store.load(uri1) == b"new"

    def test_workspace_from_env(self, tmp_path, monkeypatch):
        from backend.graph.asset_store import LocalAssetStore

        monkeypatch.setenv("CADPILOT_WORKSPACE", str(tmp_path))
        store = LocalAssetStore()
        uri = store.save(job_id="j1", name="test", data=b"data", fmt="bin")

        assert str(tmp_path) in uri

    def test_workspace_default_cwd(self, tmp_path, monkeypatch):
        from backend.graph.asset_store import LocalAssetStore

        monkeypatch.delenv("CADPILOT_WORKSPACE", raising=False)
        monkeypatch.chdir(tmp_path)
        store = LocalAssetStore()
        uri = store.save(job_id="j1", name="test", data=b"data", fmt="bin")

        assert str(tmp_path.resolve()) in uri

    def test_path_traversal_rejected(self, tmp_path):
        from backend.graph.asset_store import LocalAssetStore

        store = LocalAssetStore(workspace=tmp_path)
        with pytest.raises(ValueError, match="workspace boundary"):
            store.save(
                job_id="../../../etc", name="passwd",
                data=b"evil", fmt="txt",
            )

    def test_path_traversal_in_name_rejected(self, tmp_path):
        from backend.graph.asset_store import LocalAssetStore

        store = LocalAssetStore(workspace=tmp_path)
        with pytest.raises(ValueError, match="workspace boundary"):
            store.save(
                job_id="j1", name="../../etc/passwd",
                data=b"evil", fmt="txt",
            )


class TestAssetStoreProtocol:
    def test_local_implements_protocol(self):
        from backend.graph.asset_store import AssetStore, LocalAssetStore

        # runtime_checkable Protocol — isinstance should work
        store = LocalAssetStore()
        assert isinstance(store, AssetStore)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_asset_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.graph.asset_store'`

**Step 3: Implement AssetStore Protocol + LocalAssetStore**

Create `backend/graph/asset_store.py`:

```python
"""AssetStore — abstraction for persistent file storage.

AssetStore.save() returns an opaque URI string. URIs are only valid
for the same store implementation that produced them — do not pass
URIs between different store implementations.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class AssetStore(Protocol):
    """Protocol for asset persistence backends."""

    def save(
        self, *, job_id: str, name: str, data: bytes, fmt: str,
    ) -> str:
        """Persist data and return an opaque URI string."""
        ...

    def load(self, uri: str) -> bytes:
        """Load file content by URI. Raises FileNotFoundError if missing."""
        ...


class LocalAssetStore:
    """File-system-based AssetStore.

    Workspace priority: explicit parameter > CADPILOT_WORKSPACE env > cwd.
    Files stored at: {workspace}/jobs/{job_id}/{name}.{fmt}
    """

    def __init__(self, workspace: Path | str | None = None) -> None:
        if workspace is not None:
            self._workspace = Path(workspace).resolve()
        elif env := os.environ.get("CADPILOT_WORKSPACE"):
            self._workspace = Path(env).resolve()
        else:
            self._workspace = Path.cwd().resolve()

    def save(
        self, *, job_id: str, name: str, data: bytes, fmt: str,
    ) -> str:
        target = self._workspace / "jobs" / job_id / f"{name}.{fmt}"
        resolved = target.resolve()

        # Path traversal check
        if not str(resolved).startswith(str(self._workspace)):
            raise ValueError(
                f"Path escapes workspace boundary: {resolved} "
                f"is outside {self._workspace}"
            )

        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_bytes(data)
        return f"file://{resolved}"

    def load(self, uri: str) -> bytes:
        if uri.startswith("file://"):
            path = Path(uri[7:])
        else:
            path = Path(uri)

        if not path.exists():
            raise FileNotFoundError(f"Asset not found: {uri}")
        return path.read_bytes()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_asset_store.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/graph/asset_store.py tests/test_asset_store.py
git commit -m "feat(graph): add AssetStore Protocol + LocalAssetStore

AssetStore Protocol with save() → opaque URI and load() → bytes.
LocalAssetStore implements file:/// storage under configurable workspace.
Includes path traversal protection and auto directory creation."
```

---

### Task 8: NodeContext.save_asset 集成 AssetStore

**标签:** `[backend]`

**Files:**
- Modify: `backend/graph/context.py` (add asset_store, save_asset)
- Test: `tests/test_context.py` (add save_asset tests)

**Step 1: Write failing tests for save_asset**

在 `tests/test_context.py` 添加：

```python
class TestNodeContextSaveAsset:
    def test_save_asset_stores_and_registers(self, tmp_path):
        from backend.graph.asset_store import LocalAssetStore

        store = LocalAssetStore(workspace=tmp_path)
        desc = _make_descriptor()
        ctx = NodeContext.from_state({}, desc)
        ctx.asset_store = store

        uri = ctx.save_asset(
            name="mesh", data=b"mesh_data", fmt="obj",
            metadata={"vertices": 12000},
        )

        assert uri.startswith("file://")
        assert "mesh.obj" in uri
        # Asset registered in context
        assert ctx.has_asset("mesh")
        entry = ctx.get_asset("mesh")
        assert entry.format == "obj"
        assert entry.metadata == {"vertices": 12000}
        assert entry.path == uri

    def test_save_asset_appears_in_state_diff(self, tmp_path):
        from backend.graph.asset_store import LocalAssetStore

        store = LocalAssetStore(workspace=tmp_path)
        desc = _make_descriptor()
        ctx = NodeContext.from_state({"job_id": "j1"}, desc)
        ctx.asset_store = store

        ctx.save_asset(name="out", data=b"data", fmt="stl")

        diff = ctx.to_state_diff()
        assert "out" in diff["assets"]

    def test_save_asset_without_store_raises(self):
        desc = _make_descriptor()
        ctx = NodeContext.from_state({}, desc)
        # No asset_store set

        with pytest.raises(RuntimeError, match="AssetStore"):
            ctx.save_asset(name="x", data=b"y", fmt="z")

    def test_put_asset_still_works_without_store(self):
        """Backward compat: put_asset works as before without AssetStore."""
        desc = _make_descriptor()
        ctx = NodeContext.from_state({}, desc)

        ctx.put_asset("mesh", "/tmp/mesh.obj", "OBJ")
        assert ctx.has_asset("mesh")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_context.py::TestNodeContextSaveAsset -v`
Expected: FAIL — `NodeContext has no attribute 'asset_store'` / `save_asset`

**Step 3: Add asset_store and save_asset to NodeContext**

In `backend/graph/context.py`, add to `__init__`:

```python
        self.asset_store: Any = None  # Optional[AssetStore]
```

Add after `has_asset()`:

```python
    def save_asset(
        self,
        name: str,
        data: bytes,
        fmt: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist asset via AssetStore and register metadata.

        For nodes producing in-memory bytes. Use put_asset() instead
        when the file already exists on disk.
        """
        if self.asset_store is None:
            raise RuntimeError(
                "No AssetStore configured. Use put_asset() for "
                "direct path registration, or configure an AssetStore."
            )
        uri = self.asset_store.save(
            job_id=self.job_id, name=name, data=data, fmt=fmt,
        )
        self.put_asset(name, uri, fmt, metadata)
        return uri
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_context.py::TestNodeContextSaveAsset -v`
Expected: All PASS

**Step 5: Run full context test suite**

Run: `uv run pytest tests/test_context.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add backend/graph/context.py tests/test_context.py
git commit -m "feat(graph): add save_asset() to NodeContext with AssetStore integration

save_asset() persists in-memory bytes via AssetStore.save() and registers
metadata via put_asset(). Raises RuntimeError if no AssetStore configured.
put_asset() backward compat preserved."
```

---

### Task 9: 拦截器插入支持（新 builder）

**标签:** `[backend]`

**Files:**
- Modify: `backend/graph/builder_new.py:66-91` (build method)
- Test: `tests/test_interceptor_registry.py` (add new builder tests)

**Step 1: Write failing test for interceptor insertion in new builder**

在 `tests/test_interceptor_registry.py` 末尾添加：

```python
class TestInterceptorInNewBuilder:
    """Interceptor insertion in PipelineBuilder (builder_new.py)."""

    def test_interceptor_inserted_between_convert_and_check(self):
        """New builder inserts interceptor chain between convert_preview
        and check_printability using explicit declaration."""
        from backend.graph.builder_new import PipelineBuilder
        from backend.graph.resolver import DependencyResolver, ResolvedPipeline
        from backend.graph.descriptor import NodeDescriptor
        from backend.graph.interceptors import InterceptorRegistry

        async def noop(ctx): pass
        async def interceptor_fn(state):
            return state

        # Create minimal resolved pipeline
        nodes = [
            NodeDescriptor(name="convert_preview", display_name="Convert", fn=noop, produces=["preview_glb"]),
            NodeDescriptor(name="check_printability", display_name="Check", fn=noop, requires=["step_model"]),
            NodeDescriptor(name="finalize", display_name="Final", fn=noop, is_terminal=True),
        ]
        resolved = ResolvedPipeline(
            ordered_nodes=nodes,
            edges=[("convert_preview", "check_printability"), ("check_printability", "finalize")],
            interrupt_before=[],
        )

        interceptor_reg = InterceptorRegistry()
        interceptor_reg.register("my_interceptor", interceptor_fn, after="convert_preview")

        builder = PipelineBuilder()
        graph = builder.build(resolved, interceptor_registry=interceptor_reg)

        # Verify interceptor node exists in graph
        assert "my_interceptor" in graph.nodes

    def test_interceptor_chain_order(self):
        """Multiple interceptors chained in registration order."""
        from backend.graph.builder_new import PipelineBuilder
        from backend.graph.resolver import ResolvedPipeline
        from backend.graph.descriptor import NodeDescriptor
        from backend.graph.interceptors import InterceptorRegistry

        async def noop(ctx): pass
        call_order = []

        async def int1(state):
            call_order.append("int1")
            return state

        async def int2(state):
            call_order.append("int2")
            return state

        nodes = [
            NodeDescriptor(name="convert_preview", display_name="Convert", fn=noop, produces=["preview_glb"]),
            NodeDescriptor(name="check_printability", display_name="Check", fn=noop, requires=["step_model"]),
            NodeDescriptor(name="finalize", display_name="Final", fn=noop, is_terminal=True),
        ]
        resolved = ResolvedPipeline(
            ordered_nodes=nodes,
            edges=[("convert_preview", "check_printability"), ("check_printability", "finalize")],
            interrupt_before=[],
        )

        interceptor_reg = InterceptorRegistry()
        interceptor_reg.register("int1", int1, after="convert_preview")
        interceptor_reg.register("int2", int2, after="convert_preview")

        builder = PipelineBuilder()
        graph = builder.build(resolved, interceptor_registry=interceptor_reg)

        assert "int1" in graph.nodes
        assert "int2" in graph.nodes

    def test_no_interceptors_graph_unchanged(self):
        """Empty InterceptorRegistry should not alter the graph."""
        from backend.graph.builder_new import PipelineBuilder
        from backend.graph.resolver import ResolvedPipeline
        from backend.graph.descriptor import NodeDescriptor
        from backend.graph.interceptors import InterceptorRegistry

        async def noop(ctx): pass

        nodes = [
            NodeDescriptor(name="convert_preview", display_name="Convert", fn=noop),
            NodeDescriptor(name="check_printability", display_name="Check", fn=noop),
            NodeDescriptor(name="finalize", display_name="Final", fn=noop, is_terminal=True),
        ]
        resolved = ResolvedPipeline(
            ordered_nodes=nodes,
            edges=[("convert_preview", "check_printability"), ("check_printability", "finalize")],
            interrupt_before=[],
        )

        builder = PipelineBuilder()
        graph = builder.build(resolved, interceptor_registry=InterceptorRegistry())

        assert "convert_preview" in graph.nodes
        assert "check_printability" in graph.nodes
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_interceptor_registry.py::TestInterceptorInNewBuilder -v`
Expected: FAIL — `build() got an unexpected keyword argument 'interceptor_registry'`

**Step 3: Add interceptor support to PipelineBuilder.build()**

Modify `PipelineBuilder.build()` in `backend/graph/builder_new.py`:

```python
    def build(
        self,
        resolved: ResolvedPipeline,
        interceptor_registry: Any = None,
    ) -> StateGraph:
        workflow = StateGraph(PipelineState)

        # Register all nodes
        for desc in resolved.ordered_nodes:
            workflow.add_node(desc.name, self._wrap_node(desc))

        if not resolved.ordered_nodes:
            return workflow

        # Apply interceptors (register nodes only)
        if interceptor_registry is not None:
            interceptor_registry.apply(workflow)

        # Entry point
        entry = next((d for d in resolved.ordered_nodes if d.is_entry), None)
        if entry:
            workflow.add_edge(START, entry.name)
        else:
            workflow.add_edge(START, resolved.ordered_nodes[0].name)

        # Add conditional edges for input_type routing
        self._add_routing_edges(workflow, resolved)

        # Insert interceptor chains (explicit declaration)
        if interceptor_registry is not None:
            self._insert_interceptor_edges(workflow, resolved, interceptor_registry)

        # Terminal nodes → END
        for desc in resolved.ordered_nodes:
            if desc.is_terminal:
                workflow.add_edge(desc.name, END)

        return workflow

    def _insert_interceptor_edges(
        self,
        workflow: StateGraph,
        resolved: ResolvedPipeline,
        interceptor_registry: Any,
    ) -> None:
        """Insert interceptor chains by explicit declaration.

        For each insertion point (e.g. after="convert_preview"), build a chain:
        convert_preview → int1 → int2 → ... → next_node

        If _add_routing_edges already created a direct edge from the insertion
        point to the next node, we need to ensure the interceptor chain
        replaces that path. We do this by rebuilding edges for affected nodes.
        """
        from backend.graph.interceptors import InterceptorRegistry

        entries = interceptor_registry.list_interceptors()
        if not entries:
            return

        # Group interceptors by insertion point
        by_after: dict[str, list[str]] = {}
        for entry in entries:
            by_after.setdefault(entry["after"], []).append(entry["name"])

        # Build adjacency from resolved edges for reference
        resolved_successors: dict[str, list[str]] = {}
        for src, dst in resolved.edges:
            resolved_successors.setdefault(src, []).append(dst)

        for after_node, interceptor_names in by_after.items():
            successors = resolved_successors.get(after_node, [])
            if not successors:
                logger.warning(
                    "Interceptor insertion point '%s' has no successors "
                    "in resolved pipeline", after_node,
                )
                continue

            # For now, support single successor at insertion point
            # (convert_preview → check_printability is the only use case)
            next_node = successors[0]

            # Build chain: after_node → int1 → int2 → ... → next_node
            chain = [after_node] + interceptor_names + [next_node]
            for i in range(len(chain) - 1):
                workflow.add_edge(chain[i], chain[i + 1])

            logger.info(
                "Interceptor chain inserted: %s",
                " → ".join(chain),
            )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_interceptor_registry.py::TestInterceptorInNewBuilder -v`
Expected: All PASS

**Step 5: Update get_compiled_graph_new to pass interceptor registry**

In `backend/graph/builder_new.py`, update `get_compiled_graph_new()`:

```python
    from backend.graph.interceptors import default_registry
    graph = builder.build(resolved, interceptor_registry=default_registry)
```

**Step 6: Run existing interceptor and builder tests**

Run: `uv run pytest tests/test_interceptor_registry.py tests/test_graph_builder.py -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add backend/graph/builder_new.py tests/test_interceptor_registry.py
git commit -m "feat(graph): add interceptor support to PipelineBuilder

PipelineBuilder.build() accepts optional interceptor_registry parameter.
Interceptors are inserted as explicit edge chains at declared insertion
points (after='convert_preview'). get_compiled_graph_new() wires
default_registry automatically."
```

---

### Task 10: builder.py → builder_legacy.py + re-export wrapper

**标签:** `[backend]`

**Files:**
- Rename: `backend/graph/builder.py` → `backend/graph/builder_legacy.py`
- Create: `backend/graph/builder.py` (re-export wrapper)
- Test: `tests/test_import_compat.py` (verify imports work)

**Step 1: Write failing test for deprecation warning**

在 `tests/test_import_compat.py` 添加（或新建）：

```python
class TestBuilderDeprecationWrapper:
    def test_import_from_builder_still_works(self):
        """Importing from builder.py should work (backward compat)."""
        from backend.graph.builder import build_graph, get_compiled_graph
        assert callable(build_graph)
        assert callable(get_compiled_graph)

    def test_import_emits_deprecation_warning(self):
        """Importing from builder.py emits DeprecationWarning."""
        import importlib
        import warnings
        import backend.graph.builder as mod

        # Force reimport to trigger warning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            importlib.reload(mod)
            # Check that at least one DeprecationWarning was raised
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
```

**Step 2: Move builder.py to builder_legacy.py**

```bash
git mv backend/graph/builder.py backend/graph/builder_legacy.py
```

**Step 3: Create new builder.py as re-export wrapper**

Create `backend/graph/builder.py`:

```python
"""Re-export wrapper for backward compatibility.

The actual builder code has moved to builder_legacy.py.
Import from backend.graph.builder_legacy directly for new code.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "backend.graph.builder is deprecated. "
    "Use backend.graph.builder_legacy for the legacy builder, "
    "or backend.graph.builder_new for the new builder.",
    DeprecationWarning,
    stacklevel=2,
)

from backend.graph.builder_legacy import (  # noqa: F401, E402
    build_graph,
    get_compiled_graph,
)
```

**Step 4: Run import tests**

Run: `uv run pytest tests/test_import_compat.py::TestBuilderDeprecationWrapper -v`
Expected: PASS

**Step 5: Update any tests that import builder directly**

Search for direct imports and verify they still work:

Run: `uv run pytest tests/test_graph_builder.py tests/test_characterization.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add backend/graph/builder.py backend/graph/builder_legacy.py tests/test_import_compat.py
git commit -m "refactor(graph): move builder.py to builder_legacy.py + re-export wrapper

Legacy builder code moved to builder_legacy.py. builder.py remains as
a re-export wrapper with DeprecationWarning for backward compatibility.
All existing import paths continue to work."
```

---

### Task 11: USE_NEW_BUILDER 默认值改为 1

**标签:** `[backend]`

**Files:**
- Modify: `backend/graph/__init__.py:23` (default value change)
- Test: `tests/test_graph_builder.py` (verify both modes)

**Step 1: Write failing test for default USE_NEW_BUILDER=1**

在 `tests/test_graph_builder.py` 添加：

```python
class TestUseNewBuilderDefault:
    def test_default_is_new_builder(self, monkeypatch):
        """Without USE_NEW_BUILDER env, default should be new builder."""
        monkeypatch.delenv("USE_NEW_BUILDER", raising=False)

        import importlib
        import backend.graph
        importlib.reload(backend.graph)

        # The __getattr__ should route to builder_new
        # We test indirectly: the env check should default to "1"
        result = os.environ.get("USE_NEW_BUILDER", "1") == "1"
        assert result is True

    def test_explicit_zero_uses_legacy(self, monkeypatch):
        """USE_NEW_BUILDER=0 should use legacy builder."""
        monkeypatch.setenv("USE_NEW_BUILDER", "0")
        result = os.environ.get("USE_NEW_BUILDER", "1") == "1"
        assert result is False
```

**Step 2: Modify __init__.py default value**

In `backend/graph/__init__.py`, change line 23 from:

```python
        if os.environ.get("USE_NEW_BUILDER") == "1":
```

to:

```python
        if os.environ.get("USE_NEW_BUILDER", "1") == "1":
```

**Step 3: Run tests with both modes**

Run: `USE_NEW_BUILDER=1 uv run pytest tests/ -v --timeout=30 -x`
Run: `USE_NEW_BUILDER=0 uv run pytest tests/ -v --timeout=30 -x`
Expected: Both PASS

**Step 4: Commit**

```bash
git add backend/graph/__init__.py
git commit -m "feat(graph): set USE_NEW_BUILDER default to 1

New builder is now the default. Legacy builder activated only with
explicit USE_NEW_BUILDER=0 environment variable."
```

---

### Task 12: Demo 节点 + 端到端测试

**标签:** `[test]`

**Files:**
- Create: `tests/test_dual_channel_e2e.py`

**Step 1: Write E2E test file with demo node and all scenarios**

Create `tests/test_dual_channel_e2e.py`:

```python
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
# Demo node descriptor
# ---------------------------------------------------------------------------

def _make_demo_descriptor(config_overrides=None):
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
# E2E Tests
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

        # Make algorithm fail by using a special strategy
        class FailingAlgo(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                raise RuntimeError("algo error")

        desc.strategies["algorithm"] = FailingAlgo

        result = await ctx.execute_with_fallback()
        assert result["strategy"] == "neural"
        assert ctx._fallback_trace["fallback_triggered"] is True

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

        # Neural should be skipped (check_available=False)
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


class TestDualChannelTraceIntegration:
    """Trace merge with _wrap_node."""

    @pytest.mark.asyncio
    async def test_trace_contains_fallback_info(self):
        """_wrap_node trace includes fallback_triggered and strategy_used."""
        from backend.graph.builder_new import PipelineBuilder

        call_log = []

        class FailAlgo(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                call_log.append("algo_fail")
                raise RuntimeError("algo error")

        class OkNeural(NodeStrategy):
            def __init__(self, config=None):
                super().__init__(config)
            async def execute(self, ctx):
                call_log.append("neural_ok")
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

        assert "algo_fail" in call_log
        assert "neural_ok" in call_log

        traces = result["node_trace"]
        assert len(traces) == 1
        entry = traces[0]
        assert entry["fallback_triggered"] is True
        assert entry["strategy_used"] == "neural"
```

**Step 2: Run E2E tests**

Run: `uv run pytest tests/test_dual_channel_e2e.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/test_dual_channel_e2e.py
git commit -m "test: add dual-channel E2E tests with demo node

Demo node with algorithm + mock_neural strategies validates auto fallback
end-to-end: first-success, fallback-on-failure, neural-disabled, explicit
selection, and trace merge integration."
```

---

### Task 13: 全量测试 + 前端类型检查

**标签:** `[test]`

**Step 1: Run full test suite with USE_NEW_BUILDER=1**

Run: `USE_NEW_BUILDER=1 uv run pytest tests/ -v --timeout=60`
Expected: All PASS (zero failures)

**Step 2: Run full test suite with USE_NEW_BUILDER=0**

Run: `USE_NEW_BUILDER=0 uv run pytest tests/ -v --timeout=60`
Expected: All PASS (zero failures)

**Step 3: Run frontend type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors (this change doesn't modify frontend)

**Step 4: Fix any failures found in Steps 1-3**

If any test fails:
1. Read the failing test
2. Read the code it tests
3. Identify if it's a pre-existing issue or a regression from our changes
4. Fix regressions only (don't fix pre-existing issues in this task)
5. Re-run the affected test to confirm fix
6. Re-run full suite to confirm no cascading failures

**Step 5: Final commit if fixes were needed**

```bash
git add -A
git commit -m "fix: resolve regressions from dual-channel Phase 0 skeleton"
```

**Step 6: Run full suite one final time to confirm**

Run: `USE_NEW_BUILDER=1 uv run pytest tests/ -v --timeout=60`
Expected: All PASS

---

## Summary

| Task | 主题 | 文件 | 预计 Commit |
|------|------|------|------------|
| 1 | NodeDescriptor.fallback_chain | descriptor.py, registry.py | `feat: add fallback_chain` |
| 2 | NodeStrategy.__init__ + config injection | descriptor.py, context.py | `feat: config injection` |
| 3 | get_strategy() auto mode | context.py | `feat: auto mode selection` |
| 4 | execute_with_fallback() + trace | context.py, builder_new.py | `feat: execute_with_fallback` |
| 5 | NeuralStrategyConfig | configs/neural.py | `feat: NeuralStrategyConfig` |
| 6 | NeuralStrategy + health cache | strategies/neural.py | `feat: NeuralStrategy` |
| 7 | AssetStore + LocalAssetStore | asset_store.py | `feat: AssetStore` |
| 8 | NodeContext.save_asset | context.py | `feat: save_asset` |
| 9 | 拦截器支持（新 builder） | builder_new.py | `feat: interceptor support` |
| 10 | builder_legacy + wrapper | builder.py, builder_legacy.py | `refactor: builder rename` |
| 11 | USE_NEW_BUILDER=1 默认 | __init__.py | `feat: default new builder` |
| 12 | Demo 节点 + E2E | test_dual_channel_e2e.py | `test: E2E tests` |
| 13 | 全量验证 | — | `fix: regressions (if any)` |
