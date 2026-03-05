# Schema-Driven Scope 实施计划（Agent Team 并行模式）

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现纯 schema-driven 的参数分层架构——后端标注 x-scope，前端按 scope 自动过滤渲染，新增节点/参数时零前端改动。

**Architecture:** 后端 Pydantic config model 添加 `x-scope` JSON Schema 扩展 + enhance_config_schema 自动推断安全网 + SystemConfigStore JSON 持久化 + 3 个 REST API；前端 SchemaForm 增强（anyOf 解析 + scope 过滤）+ Settings 系统配置面板。

**Tech Stack:** Python 3.10+ / Pydantic v2 / FastAPI / React / Ant Design / TypeScript

**OpenSpec Change:** `openspec/changes/schema-driven-scope/`

---

## 并行执行结构

```
Phase 0（串行，team lead）：API 契约定义
    ↓
Phase 1（并行）：
    ├─ Backend Agent：Task 1 → 2 → 3 → 4 → 5
    └─ Frontend Agent：Task 6 → 7
    ↓
Phase 2（串行）：Task 8 集成验证
```

## 文件交叉矩阵

| 文件 | Backend Agent | Frontend Agent |
|------|:---:|:---:|
| `backend/graph/configs/*.py` (4 files) | ✓ | |
| `backend/graph/registry.py` | ✓ | |
| `backend/graph/system_config.py` (new) | ✓ | |
| `backend/graph/context.py` | ✓ | |
| `backend/api/v1/pipeline_config.py` | ✓ | |
| `tests/test_schema_sensitive.py` | ✓ | |
| `tests/test_system_config.py` (new) | ✓ | |
| `tests/test_system_config_api.py` (new) | ✓ | |
| `frontend/src/components/SchemaForm/index.tsx` | | ✓ |
| `frontend/src/components/PipelineConfigBar/CustomPanel.tsx` | | ✓ |
| `frontend/src/services/api.ts` | | ✓ |
| `frontend/src/pages/Settings/SystemConfigPanel.tsx` (new) | | ✓ |
| `frontend/src/pages/Settings/index.tsx` | | ✓ |

**文件交叉：零。** 后端和前端完全隔离，可安全并行。

---

## Phase 0: API 契约定义（串行，team lead）

### Task 0: 定义 3 个新 API 端点的请求/响应契约

**文件：** 无代码修改，仅输出契约文档供两个 agent 参考。

**API 契约：**

```
GET /api/v1/pipeline/system-config-schema
Response: {
  [node_name: string]: {
    properties: {
      [field_name: string]: {
        type?: string;
        anyOf?: Array<{type: string}>;
        default?: unknown;
        "x-sensitive"?: boolean;
        "x-scope": "system";
        ...其余 JSON Schema 字段
      }
    }
  }
}
注：只返回 x-scope="system" 的字段，同步清理 required 列表。

GET /api/v1/pipeline/system-config
Response: {
  [node_name: string]: {
    [field_name: string]: unknown  // x-sensitive 字段做掩码："sk-****1234"
  }
}

PUT /api/v1/pipeline/system-config
Request: {
  [node_name: string]: {
    [field_name: string]: unknown  // 只接受 system scope 字段
  }
}
Response: { "ok": true }
Error 400: { "error": "field 'timeout' is not a system-scope field" }
Error 422: { "error": "validation error: ..." }
```

---

## Phase 1A: Backend Agent

### Task 1: Config Model x-scope 标记

**Files:**
- Modify: `backend/graph/configs/generate_raw_mesh.py`
- Modify: `backend/graph/configs/neural.py`
- Modify: `backend/graph/configs/mesh_healer.py`
- Modify: `backend/graph/configs/slice_to_gcode.py`
- Test: `tests/test_schema_sensitive.py`

**Step 1: Write failing tests**

在 `tests/test_schema_sensitive.py` 新增 class：

```python
class TestXScopeAnnotation:
    """Fields annotated with x-scope appear in config_schema."""

    def test_generate_raw_mesh_api_key_has_system_scope(self):
        from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig
        schema = GenerateRawMeshConfig.model_json_schema()
        api_key_prop = schema["properties"]["hunyuan3d_api_key"]
        assert api_key_prop.get("x-scope") == "system"
        assert api_key_prop.get("x-sensitive") is True

    def test_generate_raw_mesh_timeout_no_scope(self):
        from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig
        schema = GenerateRawMeshConfig.model_json_schema()
        assert "x-scope" not in schema["properties"]["timeout"]

    def test_neural_config_system_fields(self):
        from backend.graph.configs.neural import NeuralStrategyConfig
        schema = NeuralStrategyConfig.model_json_schema()
        for field in ("neural_enabled", "neural_endpoint", "health_check_path"):
            assert schema["properties"][field].get("x-scope") == "system", f"{field} missing x-scope"
        assert "x-scope" not in schema["properties"]["neural_timeout"]

    def test_mesh_healer_retopo_endpoint_system(self):
        from backend.graph.configs.mesh_healer import MeshHealerConfig
        schema = MeshHealerConfig.model_json_schema()
        assert schema["properties"]["retopo_endpoint"].get("x-scope") == "system"

    def test_slice_to_gcode_cli_paths_system(self):
        from backend.graph.configs.slice_to_gcode import SliceToGcodeConfig
        schema = SliceToGcodeConfig.model_json_schema()
        for field in ("prusaslicer_path", "orcaslicer_path"):
            assert schema["properties"][field].get("x-scope") == "system", f"{field} missing x-scope"
```

**Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_schema_sensitive.py::TestXScopeAnnotation -v`
Expected: FAIL — fields don't have x-scope yet

**Step 3: Implement x-scope annotations**

`generate_raw_mesh.py` — 修改 5 个字段：
```python
from pydantic import Field

hunyuan3d_api_key: str | None = Field(
    default=None, json_schema_extra={"x-sensitive": True, "x-scope": "system"},
)
hunyuan3d_endpoint: str | None = Field(
    default=None, json_schema_extra={"x-scope": "system"},
)
tripo3d_api_key: str | None = Field(
    default=None, json_schema_extra={"x-sensitive": True, "x-scope": "system"},
)
spar3d_endpoint: str | None = Field(
    default=None, json_schema_extra={"x-scope": "system"},
)
trellis_endpoint: str | None = Field(
    default=None, json_schema_extra={"x-scope": "system"},
)
```

`neural.py` — 修改 3 个字段：
```python
from pydantic import Field

neural_enabled: bool = Field(default=False, json_schema_extra={"x-scope": "system"})
neural_endpoint: str | None = Field(default=None, json_schema_extra={"x-scope": "system"})
health_check_path: str = Field(default="/health", json_schema_extra={"x-scope": "system"})
```

`mesh_healer.py` — 修改 1 个字段：
```python
retopo_endpoint: str | None = Field(default=None, json_schema_extra={"x-scope": "system"})
```

`slice_to_gcode.py` — 修改 2 个字段：
```python
prusaslicer_path: str | None = Field(default=None, json_schema_extra={"x-scope": "system"})
orcaslicer_path: str | None = Field(default=None, json_schema_extra={"x-scope": "system"})
```

**Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_schema_sensitive.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/graph/configs/generate_raw_mesh.py backend/graph/configs/neural.py backend/graph/configs/mesh_healer.py backend/graph/configs/slice_to_gcode.py tests/test_schema_sensitive.py
git commit -m "feat(configs): add x-scope=system annotations to system-level config fields"
```

---

### Task 2: enhance_config_schema 自动推断

**Files:**
- Modify: `backend/graph/registry.py:148-168`
- Test: `tests/test_schema_sensitive.py`

**Step 1: Write failing tests**

在 `tests/test_schema_sensitive.py` 新增 class：

```python
class TestXScopeAutoInference:
    """enhance_config_schema auto-infers x-scope for system fields."""

    def test_sensitive_field_gets_system_scope(self):
        schema = {"properties": {
            "my_api_key": {"type": "string"},
        }}
        result = enhance_config_schema(schema)
        assert result["properties"]["my_api_key"].get("x-sensitive") is True
        assert result["properties"]["my_api_key"].get("x-scope") == "system"

    def test_endpoint_field_gets_system_scope(self):
        schema = {"properties": {
            "custom_endpoint": {"type": "string"},
        }}
        result = enhance_config_schema(schema)
        assert result["properties"]["custom_endpoint"].get("x-scope") == "system"

    def test_neural_enabled_gets_system_scope(self):
        schema = {"properties": {
            "neural_enabled": {"type": "boolean"},
        }}
        result = enhance_config_schema(schema)
        assert result["properties"]["neural_enabled"].get("x-scope") == "system"

    def test_cli_path_gets_system_scope(self):
        schema = {"properties": {
            "prusaslicer_path": {"type": "string"},
            "orcaslicer_path": {"type": "string"},
        }}
        result = enhance_config_schema(schema)
        assert result["properties"]["prusaslicer_path"].get("x-scope") == "system"
        assert result["properties"]["orcaslicer_path"].get("x-scope") == "system"

    def test_generic_path_not_auto_inferred(self):
        """model_path, export_path should NOT be auto-inferred as system."""
        schema = {"properties": {
            "model_path": {"type": "string"},
            "export_path": {"type": "string"},
        }}
        result = enhance_config_schema(schema)
        assert "x-scope" not in result["properties"]["model_path"]
        assert "x-scope" not in result["properties"]["export_path"]

    def test_explicit_scope_not_overridden(self):
        schema = {"properties": {
            "custom_endpoint": {"type": "string", "x-scope": "engineering"},
        }}
        result = enhance_config_schema(schema)
        assert result["properties"]["custom_endpoint"]["x-scope"] == "engineering"

    def test_engineering_field_no_scope(self):
        schema = {"properties": {
            "timeout": {"type": "integer"},
            "layer_height": {"type": "number"},
        }}
        result = enhance_config_schema(schema)
        assert "x-scope" not in result["properties"]["timeout"]
        assert "x-scope" not in result["properties"]["layer_height"]
```

**Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_schema_sensitive.py::TestXScopeAutoInference -v`
Expected: FAIL — enhance_config_schema doesn't handle x-scope yet

**Step 3: Implement auto-inference**

在 `backend/graph/registry.py:152` 后添加：

```python
_SYSTEM_PATTERN = re.compile(
    r"(_endpoint$|^prusaslicer_path$|^orcaslicer_path$|^neural_enabled$)",
    re.IGNORECASE,
)
```

修改 `enhance_config_schema()` 函数（L155-168），在 x-sensitive 检测之后添加 x-scope 推断：

```python
def enhance_config_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Post-process Pydantic v2 JSON schema: inject x-sensitive and x-scope."""
    schema = copy.deepcopy(schema)
    props = schema.get("properties", {})
    for field_name, field_schema in props.items():
        # Auto-detect x-sensitive
        if "x-sensitive" not in field_schema and _SENSITIVE_PATTERN.search(field_name):
            field_schema["x-sensitive"] = True
        # Auto-infer x-scope (only if not explicitly set)
        if "x-scope" not in field_schema:
            if field_schema.get("x-sensitive"):
                field_schema["x-scope"] = "system"
            elif _SYSTEM_PATTERN.search(field_name):
                field_schema["x-scope"] = "system"
    return schema
```

**Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_schema_sensitive.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/graph/registry.py tests/test_schema_sensitive.py
git commit -m "feat(registry): add x-scope auto-inference safety net in enhance_config_schema"
```

---

### Task 3: SystemConfigStore 持久化

**Files:**
- Create: `backend/graph/system_config.py`
- Create: `tests/test_system_config.py`

**Step 1: Write failing tests**

新建 `tests/test_system_config.py`：

```python
"""Tests for SystemConfigStore."""
import json
import os
import pytest

from backend.graph.system_config import SystemConfigStore


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "system_config.json"
    return SystemConfigStore(path=str(path))


class TestSystemConfigStore:
    def test_load_missing_file_returns_empty(self, store):
        assert store.load() == {}

    def test_save_and_load_roundtrip(self, store):
        data = {"generate_raw_mesh": {"hunyuan3d_api_key": "sk-test123"}}
        store.save(data)
        assert store.load() == data

    def test_get_node_existing(self, store):
        store.save({"generate_raw_mesh": {"key": "val"}})
        assert store.get_node("generate_raw_mesh") == {"key": "val"}

    def test_get_node_missing(self, store):
        store.save({"generate_raw_mesh": {"key": "val"}})
        assert store.get_node("mesh_healer") == {}

    def test_get_node_empty_store(self, store):
        assert store.get_node("anything") == {}

    def test_atomic_write_no_corruption(self, store, tmp_path):
        """Save creates valid JSON even if called repeatedly."""
        for i in range(5):
            store.save({"node": {"key": f"val-{i}"}})
        result = store.load()
        assert result == {"node": {"key": "val-4"}}
        # Verify no temp files left behind
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "system_config.json"
```

**Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_system_config.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement SystemConfigStore**

新建 `backend/graph/system_config.py`：

```python
"""SystemConfigStore — JSON-file persistence for system-level node configuration."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "system_config.json"


class SystemConfigStore:
    """Thread-safe JSON store for system-scope config values.

    Atomic writes via NamedTemporaryFile + os.replace.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else _DEFAULT_PATH
        self._lock = threading.Lock()

    def load(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            if not self._path.exists():
                return {}
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)

    def save(self, data: dict[str, dict[str, Any]]) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = tempfile.NamedTemporaryFile(
                mode="w",
                dir=str(self._path.parent),
                suffix=".tmp",
                delete=False,
                encoding="utf-8",
            )
            try:
                json.dump(data, fd, ensure_ascii=False, indent=2)
                fd.flush()
                os.fsync(fd.fileno())
                fd.close()
                os.replace(fd.name, str(self._path))
            except BaseException:
                fd.close()
                try:
                    os.unlink(fd.name)
                except OSError:
                    pass
                raise

    def get_node(self, node_name: str) -> dict[str, Any]:
        return self.load().get(node_name, {})


# Module-level singleton
system_config_store = SystemConfigStore()
```

**Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_system_config.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/graph/system_config.py tests/test_system_config.py
git commit -m "feat(graph): add SystemConfigStore for system-scope config persistence"
```

---

### Task 4: 系统配置 REST API

**Files:**
- Modify: `backend/api/v1/pipeline_config.py`
- Create: `tests/test_system_config_api.py`

**Step 1: Write failing tests**

新建 `tests/test_system_config_api.py`：

```python
"""Tests for system config API endpoints."""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)


class TestSystemConfigSchemaEndpoint:
    def test_returns_only_system_fields(self, client):
        resp = client.get("/api/v1/pipeline/system-config-schema")
        assert resp.status_code == 200
        data = resp.json()
        # generate_raw_mesh should have system fields
        if "generate_raw_mesh" in data:
            props = data["generate_raw_mesh"]["properties"]
            for field_name, field_schema in props.items():
                assert field_schema.get("x-scope") == "system"
            # engineering fields should NOT appear
            assert "timeout" not in props
            assert "output_format" not in props


class TestSystemConfigGetEndpoint:
    def test_returns_masked_sensitive_values(self, client, tmp_path):
        config_path = tmp_path / "test_config.json"
        config_path.write_text(json.dumps({
            "generate_raw_mesh": {"hunyuan3d_api_key": "sk-test1234567890"}
        }))
        with patch("backend.api.v1.pipeline_config.system_config_store") as mock_store:
            mock_store.load.return_value = {
                "generate_raw_mesh": {"hunyuan3d_api_key": "sk-test1234567890"}
            }
            resp = client.get("/api/v1/pipeline/system-config")
            assert resp.status_code == 200
            data = resp.json()
            api_key = data["generate_raw_mesh"]["hunyuan3d_api_key"]
            assert "sk-test1234567890" not in api_key  # masked
            assert api_key.endswith("7890")  # last 4 chars visible


class TestSystemConfigPutEndpoint:
    def test_saves_valid_system_config(self, client):
        with patch("backend.api.v1.pipeline_config.system_config_store") as mock_store:
            mock_store.save.return_value = None
            resp = client.put("/api/v1/pipeline/system-config", json={
                "generate_raw_mesh": {"hunyuan3d_endpoint": "https://example.com"}
            })
            assert resp.status_code == 200

    def test_rejects_engineering_field(self, client):
        resp = client.put("/api/v1/pipeline/system-config", json={
            "generate_raw_mesh": {"timeout": 999}
        })
        assert resp.status_code == 400
```

**Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_system_config_api.py -v`
Expected: FAIL — endpoints don't exist

**Step 3: Implement API endpoints**

在 `backend/api/v1/pipeline_config.py` 末尾添加 3 个端点：

```python
@router.get("/system-config-schema")
async def get_system_config_schema() -> dict[str, Any]:
    """返回每个节点的 system scope 字段 schema。"""
    from backend.graph.registry import registry, enhance_config_schema

    result: dict[str, Any] = {}
    for name, desc in registry.all().items():
        if not desc.config_model:
            continue
        schema = enhance_config_schema(desc.config_model.model_json_schema())
        props = schema.get("properties", {})
        system_props = {
            k: v for k, v in props.items()
            if v.get("x-scope") == "system"
        }
        if system_props:
            # Clean up required list
            required = [r for r in schema.get("required", []) if r in system_props]
            node_schema: dict[str, Any] = {"properties": system_props}
            if required:
                node_schema["required"] = required
            result[name] = node_schema
    return result


@router.get("/system-config")
async def get_system_config() -> dict[str, Any]:
    """返回当前系统配置值（x-sensitive 字段做掩码）。"""
    from backend.graph.registry import registry, enhance_config_schema
    from backend.graph.system_config import system_config_store

    raw = system_config_store.load()

    # Build sensitive field set for masking
    sensitive_fields: dict[str, set[str]] = {}
    for name, desc in registry.all().items():
        if not desc.config_model:
            continue
        schema = enhance_config_schema(desc.config_model.model_json_schema())
        s_fields = set()
        for fname, fschema in schema.get("properties", {}).items():
            if fschema.get("x-sensitive"):
                s_fields.add(fname)
        if s_fields:
            sensitive_fields[name] = s_fields

    # Mask sensitive values
    masked = {}
    for node_name, node_config in raw.items():
        masked_node = {}
        s_set = sensitive_fields.get(node_name, set())
        for k, v in node_config.items():
            if k in s_set and isinstance(v, str) and len(v) > 4:
                masked_node[k] = v[:3] + "****" + v[-4:]
            else:
                masked_node[k] = v
        masked[node_name] = masked_node
    return masked


@router.put("/system-config")
async def update_system_config(request: Request) -> dict[str, Any]:
    """保存系统配置（仅接受 system scope 字段，做类型验证）。"""
    from backend.graph.registry import registry, enhance_config_schema
    from backend.graph.system_config import system_config_store

    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400, content='{"error":"Invalid JSON"}',
                        media_type="application/json")

    # Validate: only system-scope fields allowed
    for node_name, node_config in body.items():
        desc = registry.get(node_name)
        if not desc or not desc.config_model:
            return Response(
                status_code=400,
                content=json.dumps({"error": f"Unknown node: {node_name}"}),
                media_type="application/json",
            )
        schema = enhance_config_schema(desc.config_model.model_json_schema())
        props = schema.get("properties", {})
        for field_name in node_config:
            field_schema = props.get(field_name, {})
            if field_schema.get("x-scope") != "system":
                return Response(
                    status_code=400,
                    content=json.dumps({"error": f"field '{field_name}' is not a system-scope field"}),
                    media_type="application/json",
                )

    # Merge with existing (replace semantics per node)
    existing = system_config_store.load()
    existing.update(body)
    system_config_store.save(existing)
    return {"ok": True}
```

需要在文件顶部导入 `json` 和 `Response`。

**Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_system_config_api.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/api/v1/pipeline_config.py tests/test_system_config_api.py
git commit -m "feat(api): add system config REST endpoints (schema, get with masking, put with validation)"
```

---

### Task 5: NodeContext 运行时合并

**Files:**
- Modify: `backend/graph/context.py:137-156`

**Step 1: Write failing test**

在 `tests/test_system_config.py` 追加：

```python
class TestNodeContextMerge:
    """NodeContext.from_state merges system config as defaults."""

    def test_system_config_provides_defaults(self, tmp_path):
        from backend.graph.context import NodeContext
        from backend.graph.descriptor import NodeDescriptor
        from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig

        config_path = tmp_path / "sys.json"
        config_path.write_text(json.dumps({
            "generate_raw_mesh": {"hunyuan3d_endpoint": "https://sys.example.com"}
        }))

        with patch("backend.graph.context.system_config_store") as mock_store:
            mock_store.get_node.return_value = {"hunyuan3d_endpoint": "https://sys.example.com"}

            desc = NodeDescriptor(
                name="generate_raw_mesh",
                display_name="Generate Raw Mesh",
                config_model=GenerateRawMeshConfig,
            )
            state = {"pipeline_config": {}, "assets": {}, "data": {}}
            ctx = NodeContext.from_state(state, desc)
            assert ctx.config.hunyuan3d_endpoint == "https://sys.example.com"

    def test_per_request_overrides_system_config(self):
        from backend.graph.context import NodeContext
        from backend.graph.descriptor import NodeDescriptor
        from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig

        with patch("backend.graph.context.system_config_store") as mock_store:
            mock_store.get_node.return_value = {"hunyuan3d_endpoint": "https://sys.example.com"}

            desc = NodeDescriptor(
                name="generate_raw_mesh",
                display_name="Generate Raw Mesh",
                config_model=GenerateRawMeshConfig,
            )
            state = {
                "pipeline_config": {
                    "generate_raw_mesh": {"hunyuan3d_endpoint": "https://override.com"}
                },
                "assets": {}, "data": {},
            }
            ctx = NodeContext.from_state(state, desc)
            assert ctx.config.hunyuan3d_endpoint == "https://override.com"

    def test_no_system_config_unchanged_behavior(self):
        from backend.graph.context import NodeContext
        from backend.graph.descriptor import NodeDescriptor
        from backend.graph.configs.generate_raw_mesh import GenerateRawMeshConfig

        with patch("backend.graph.context.system_config_store") as mock_store:
            mock_store.get_node.return_value = {}

            desc = NodeDescriptor(
                name="generate_raw_mesh",
                display_name="Generate Raw Mesh",
                config_model=GenerateRawMeshConfig,
            )
            state = {"pipeline_config": {}, "assets": {}, "data": {}}
            ctx = NodeContext.from_state(state, desc)
            assert ctx.config.hunyuan3d_endpoint is None  # Pydantic default
```

**Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_system_config.py::TestNodeContextMerge -v`
Expected: FAIL

**Step 3: Implement merge in NodeContext.from_state()**

修改 `backend/graph/context.py:142-145`，将：

```python
node_configs = state.get("pipeline_config", {})
raw_config = node_configs.get(desc.name, {})
config_cls = desc.config_model or BaseNodeConfig
config = config_cls(**raw_config) if raw_config else config_cls()
```

改为：

```python
from backend.graph.system_config import system_config_store

node_configs = state.get("pipeline_config", {})
raw_config = node_configs.get(desc.name, {})
config_cls = desc.config_model or BaseNodeConfig

# Merge: Pydantic default < system_config < per-request
system_defaults = system_config_store.get_node(desc.name)
if system_defaults:
    merged = {**system_defaults, **raw_config}
else:
    merged = raw_config
config = config_cls(**merged) if merged else config_cls()
```

**Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_system_config.py -v`
Expected: ALL PASS

然后运行全量测试确认无回归：

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/graph/context.py tests/test_system_config.py
git commit -m "feat(context): merge system config as defaults in NodeContext.from_state"
```

---

## Phase 1B: Frontend Agent

### Task 6: SchemaForm 增强（anyOf 解析 + scope 过滤）

**Files:**
- Modify: `frontend/src/components/SchemaForm/index.tsx`
- Modify: `frontend/src/components/PipelineConfigBar/CustomPanel.tsx:240-244`

**Step 1: 在 SchemaForm/index.tsx 中添加 anyOf 类型解析**

在 `JsonSchemaProperty` 接口中新增：

```typescript
interface JsonSchemaProperty {
  type?: string;
  anyOf?: Array<{ type?: string }>;  // 新增
  description?: string;
  minimum?: number;
  maximum?: number;
  enum?: string[];
  default?: unknown;
  'x-sensitive'?: boolean;
  'x-group'?: string;
  'x-scope'?: string;  // 新增
}
```

在 `SchemaFormProps` 中新增 scope prop：

```typescript
interface SchemaFormProps {
  schema: {
    properties?: Record<string, JsonSchemaProperty>;
    [key: string]: unknown;
  };
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  scope?: 'engineering' | 'system' | 'all';  // 新增
}
```

新增 `resolveType` 工具函数（在 `humanize` 函数之后）：

```typescript
/** Resolve Pydantic v2 anyOf types (e.g. str | None → "string") */
function resolveType(prop: JsonSchemaProperty): string | undefined {
  if (prop.type) return prop.type;
  if (prop.anyOf) {
    const types = prop.anyOf.map((s) => s.type).filter((t) => t && t !== 'null');
    return types[0];
  }
  return undefined;
}
```

**Step 2: 修改 renderField 使用 resolveType**

将 `renderField` 中所有 `prop.type` 判断改为 `resolveType(prop)`：

```typescript
function renderField(...) {
  // Sensitive → Password (优先，不需要改)
  if (prop['x-sensitive']) { ... }

  const type = resolveType(prop);

  // Boolean → Switch
  if (type === 'boolean') { ... }

  // Integer/Number with min+max → Slider
  if ((type === 'integer' || type === 'number') && ...) { ... }

  // Integer/Number without range → InputNumber
  if (type === 'integer' || type === 'number') { ... }

  // String with enum → Select
  if (type === 'string' && prop.enum) { ... }

  // String without enum → Input
  if (type === 'string') { ... }

  // Unsupported fallback
  ...
}
```

**Step 3: 添加 scope 过滤逻辑**

在 `SchemaForm` 组件中，修改 fields 过滤：

```typescript
export default function SchemaForm({ schema, value, onChange, scope = 'engineering' }: SchemaFormProps) {
  const properties = schema.properties ?? {};
  const requiredFields = new Set((schema.required as string[] | undefined) ?? []);

  const fields = Object.entries(properties).filter(([name, prop]) => {
    if (SKIP_FIELDS.has(name)) return false;
    if (scope === 'all') return true;
    const fieldScope = prop['x-scope'] ?? 'engineering';
    return fieldScope === scope;
  });

  // ... rest unchanged
}
```

**Step 4: CustomPanel.tsx 传入 scope="engineering"**

修改 `CustomPanel.tsx:240-244`：

```typescript
<SchemaForm
  schema={desc.config_schema as Record<string, unknown> & { properties?: Record<string, unknown> }}
  value={nodeConf}
  onChange={(params) => handleParams(desc.name, params)}
  scope="engineering"
/>
```

**Step 5: 验证编译**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: 零错误

**Step 6: Commit**

```bash
git add frontend/src/components/SchemaForm/index.tsx frontend/src/components/PipelineConfigBar/CustomPanel.tsx
git commit -m "feat(SchemaForm): add anyOf type resolution and x-scope filtering"
```

---

### Task 7: Settings 页系统配置面板

**Files:**
- Modify: `frontend/src/services/api.ts`
- Create: `frontend/src/pages/Settings/SystemConfigPanel.tsx`
- Modify: `frontend/src/pages/Settings/index.tsx`

**Step 1: 添加 API 函数到 api.ts**

在 `frontend/src/services/api.ts` 的 `getStrategyAvailability` 之后添加：

```typescript
// System Config API
export async function getSystemConfigSchema(): Promise<Record<string, { properties: Record<string, unknown> }>> {
  const { data } = await api.get<Record<string, { properties: Record<string, unknown> }>>('/v1/pipeline/system-config-schema');
  return data;
}

export async function getSystemConfig(): Promise<Record<string, Record<string, unknown>>> {
  const { data } = await api.get<Record<string, Record<string, unknown>>>('/v1/pipeline/system-config');
  return data;
}

export async function updateSystemConfig(
  config: Record<string, Record<string, unknown>>,
): Promise<{ ok: boolean }> {
  const { data } = await api.put<{ ok: boolean }>('/v1/pipeline/system-config', config);
  return data;
}
```

**Step 2: 创建 SystemConfigPanel.tsx**

新建 `frontend/src/pages/Settings/SystemConfigPanel.tsx`：

```typescript
import { useState, useEffect, useCallback } from 'react';
import { Collapse, Button, Space, message, Spin, Empty } from 'antd';
import { SaveOutlined, UndoOutlined } from '@ant-design/icons';
import SchemaForm from '../../components/SchemaForm/index.tsx';
import { getSystemConfigSchema, getSystemConfig, updateSystemConfig } from '../../services/api.ts';

/** Convert snake_case to human-readable */
function humanize(name: string): string {
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function SystemConfigPanel() {
  const [schemas, setSchemas] = useState<Record<string, { properties: Record<string, unknown> }>>({});
  const [values, setValues] = useState<Record<string, Record<string, unknown>>>({});
  const [savedValues, setSavedValues] = useState<Record<string, Record<string, unknown>>>({});
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [schemaData, configData] = await Promise.all([
        getSystemConfigSchema(),
        getSystemConfig(),
      ]);
      setSchemas(schemaData);
      setValues(configData);
      setSavedValues(configData);
    } catch {
      message.error('加载系统配置失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSave = async () => {
    try {
      await updateSystemConfig(values);
      setSavedValues({ ...values });
      message.success('系统配置已保存');
    } catch {
      message.error('保存失败');
    }
  };

  const handleReset = () => {
    setValues({ ...savedValues });
  };

  const handleNodeChange = (nodeName: string, nodeValues: Record<string, unknown>) => {
    setValues((prev) => ({ ...prev, [nodeName]: nodeValues }));
  };

  if (loading) return <Spin />;

  const nodeNames = Object.keys(schemas);
  if (nodeNames.length === 0) return <Empty description="无系统配置" />;

  const hasChanges = JSON.stringify(values) !== JSON.stringify(savedValues);

  return (
    <div>
      <Collapse
        items={nodeNames.map((nodeName) => ({
          key: nodeName,
          label: humanize(nodeName),
          children: (
            <SchemaForm
              schema={schemas[nodeName] as Record<string, unknown> & { properties?: Record<string, unknown> }}
              value={values[nodeName] ?? {}}
              onChange={(v) => handleNodeChange(nodeName, v)}
              scope="system"
            />
          ),
        }))}
      />
      <Space style={{ marginTop: 16 }}>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          onClick={handleSave}
          disabled={!hasChanges}
        >
          保存
        </Button>
        <Button
          icon={<UndoOutlined />}
          onClick={handleReset}
          disabled={!hasChanges}
        >
          重置
        </Button>
      </Space>
    </div>
  );
}
```

**Step 3: Settings/index.tsx 新增 tab**

修改 `frontend/src/pages/Settings/index.tsx`，添加 import 和 tab：

```typescript
import { Typography, Tabs } from 'antd';
import { SettingOutlined, PrinterOutlined, ApiOutlined } from '@ant-design/icons';
import ModelConfigPanel from './ModelConfigPanel.tsx';
import PrintConfigPanel from './PrintConfigPanel.tsx';
import SystemConfigPanel from './SystemConfigPanel.tsx';

const { Title } = Typography;

export default function Settings() {
  return (
    <div>
      <Title level={3}>设置</Title>
      <Tabs
        defaultActiveKey="models"
        items={[
          {
            key: 'models',
            label: <span><SettingOutlined /> 模型配置</span>,
            children: <ModelConfigPanel />,
          },
          {
            key: 'print',
            label: <span><PrinterOutlined /> 打印配置</span>,
            children: <PrintConfigPanel />,
          },
          {
            key: 'system',
            label: <span><ApiOutlined /> 系统配置</span>,
            children: <SystemConfigPanel />,
          },
        ]}
      />
    </div>
  );
}
```

**Step 4: 验证编译**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: 零错误

**Step 5: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/pages/Settings/SystemConfigPanel.tsx frontend/src/pages/Settings/index.tsx
git commit -m "feat(Settings): add system config panel with schema-driven form rendering"
```

---

## Phase 2: 集成验证（串行）

### Task 8: 全栈集成验证

**Step 1: 后端全量测试**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

**Step 2: 前端编译检查**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: 零错误

**Step 3: E2E 验证**

1. 启动服务：`./scripts/start.sh`
2. 打开 http://localhost:3001/organic → 展开管道配置面板
   - 验证：节点展开后**不显示** API key、endpoint、CLI path 字段
   - 验证：显示 timeout、layer_height 等工程参数
3. 打开 http://localhost:3001/settings → 切换到"系统配置"tab
   - 验证：显示有 system 字段的节点（Generate Raw Mesh、Mesh Healer、Slice To Gcode 等）
   - 验证：API key 字段使用密码输入框
   - 验证：endpoint 字段使用普通文本输入框（不是"未设置"）
4. 在系统配置中填入值 → 保存 → 刷新页面 → 验证值持久

**Step 4: Commit integration verification**

```bash
git commit --allow-empty -m "test: verify schema-driven-scope full-stack integration"
```
