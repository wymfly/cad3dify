# 白盒化工业级 AI 3D 设计中台 — 产品化实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 CAD3Dify 从"技术 Demo"演进为 B2B 工业级产品 — 后端 API 标准化、6 个已完成模块串入管道、前端三栏工作台全面重设计。

**Architecture:** 4 层迁移（Layer 1: API+持久化 → Layer 2: 管道集成 → Layer 3: 前端框架 → Layer 4: 前端功能）。后端 FastAPI + SQLAlchemy async + SSE 独立订阅。前端 React + Ant Design 6 + Three.js 三栏工作台。

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2.0 (async/aiosqlite), Pydantic v2, sse-starlette | React 18, TypeScript 5.6, Ant Design 6, @react-three/fiber, React Router

---

## 任务域分布与并行策略

| 域标签 | 任务数 | Groups |
|--------|--------|--------|
| `[backend]` | 21 | 1, 2, 3 |
| `[frontend]` | 22 | 4, 5, 6, 7, 8 |
| `[test]` | 3 | 1.8, 2.8, 3.8 |
| `[test:e2e]` | 6 | 9 |

### 依赖图

```
Layer 1: [Group 1: API 标准化] + [Group 2: 数据持久化]  ← 可并行
            ↓                           ↓
Layer 2: [Group 3: 管道集成]  ← 依赖 Group 1+2
            ↓
Layer 3: [Group 4: 前端框架]  ← 依赖 Group 1（API 端点）
            ↓
Layer 4: [Group 5] + [Group 6] + [Group 7] + [Group 8]  ← 可并行
            ↓
         [Group 9: E2E 验证]  ← 依赖全部
```

### 推荐执行模式

- **Layer 1**: backend-dev 串行执行 Group 1 → Group 2（共享 DB 层，不宜并行）
- **Layer 2**: backend-dev 执行 Group 3
- **Layer 3**: frontend-dev 执行 Group 4
- **Layer 4**: frontend-dev 并行执行 Group 5 + 6 + 7 + 8（独立页面）
- **Layer 5**: test-engineer 执行 Group 9

---

## 参考文档

- **设计方案**: `docs/plans/2026-02-28-whitebox-platform-productization-design.md`
- **OpenSpec 规范**: `openspec/changes/whitebox-platform-productization/specs/`
- **OpenSpec 任务**: `openspec/changes/whitebox-platform-productization/tasks.md`

---

### Task 1: 后端 API 标准化 `[backend]`

**Files:**
- Create: `backend/api/v1/__init__.py`
- Create: `backend/api/v1/router.py`
- Create: `backend/api/v1/errors.py`
- Create: `backend/api/v1/jobs.py`
- Create: `backend/api/v1/events.py`
- Modify: `backend/main.py:1-69` — 注册 v1 路由
- Modify: `backend/api/generate.py:1-773` — 提取逻辑到 v1，最终移除
- Modify: `backend/api/organic.py:1-498` — 提取逻辑到 v1，最终移除
- Modify: `backend/pipeline/sse_bridge.py:1-137` — 适配独立 SSE
- Reference: `backend/models/job.py:1-165` — Job 模型定义
- Reference: `backend/models/organic_job.py:1-168` — OrganicJob 模型
- Test: `tests/test_api_v1.py` (新建)

**Step 1: 创建 v1 路由蓝图和错误处理 (Task 1.1 + 1.2)**

```bash
mkdir -p backend/api/v1
touch backend/api/v1/__init__.py
```

编写 `backend/api/v1/errors.py`:
```python
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | list | None = None

class ErrorResponse(BaseModel):
    error: ErrorDetail

# 自定义异常
class JobNotFoundError(Exception):
    def __init__(self, job_id: str):
        self.job_id = job_id

class InvalidJobStateError(Exception):
    def __init__(self, job_id: str, current: str, expected: str):
        self.job_id = job_id
        self.current = current
        self.expected = expected

# 异常处理器注册
def register_error_handlers(app):
    @app.exception_handler(JobNotFoundError)
    async def job_not_found(request: Request, exc: JobNotFoundError):
        return JSONResponse(status_code=404, content=ErrorResponse(
            error=ErrorDetail(code="JOB_NOT_FOUND", message=f"Job {exc.job_id} not found")
        ).model_dump())

    @app.exception_handler(InvalidJobStateError)
    async def invalid_state(request: Request, exc: InvalidJobStateError):
        return JSONResponse(status_code=409, content=ErrorResponse(
            error=ErrorDetail(
                code="INVALID_JOB_STATE",
                message=f"Job {exc.job_id} is in '{exc.current}' state, expected '{exc.expected}'"
            )
        ).model_dump())
```

编写 `backend/api/v1/router.py`:
```python
from fastapi import APIRouter

v1_router = APIRouter(prefix="/api/v1")

# 子路由将在后续步骤中注册
```

修改 `backend/main.py` 注册 v1 路由:
```python
from backend.api.v1.router import v1_router
from backend.api.v1.errors import register_error_handlers

app.include_router(v1_router)
register_error_handlers(app)
```

**Step 2: 编写 Job CRUD + 创建端点测试 (Task 1.3 + 1.4)**

先写测试 `tests/test_api_v1.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_create_text_job(client):
    resp = await client.post("/api/v1/jobs", json={"input_type": "text", "text": "法兰盘"})
    assert resp.status_code == 201
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "created"

@pytest.mark.asyncio
async def test_create_job_invalid_type(client):
    resp = await client.post("/api/v1/jobs", json={"input_type": "invalid"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"

@pytest.mark.asyncio
async def test_get_job_not_found(client):
    resp = await client.get("/api/v1/jobs/nonexistent-id")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "JOB_NOT_FOUND"

@pytest.mark.asyncio
async def test_list_jobs_paginated(client):
    resp = await client.get("/api/v1/jobs?page=1&page_size=20")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data

@pytest.mark.asyncio
async def test_old_endpoint_returns_404(client):
    resp = await client.post("/api/generate", json={"text": "test"})
    assert resp.status_code == 404
```

运行验证失败: `uv run pytest tests/test_api_v1.py -v`

**Step 3: 实现 Job CRUD 端点**

编写 `backend/api/v1/jobs.py`:
```python
from fastapi import APIRouter, Body
from pydantic import BaseModel, Field
from typing import Literal
from backend.api.v1.errors import JobNotFoundError, InvalidJobStateError

router = APIRouter(prefix="/jobs", tags=["jobs"])

class CreateJobRequest(BaseModel):
    input_type: Literal["text", "drawing", "organic"]
    text: str | None = None
    prompt: str | None = None
    template_params: dict | None = None

class JobResponse(BaseModel):
    job_id: str
    status: str

@router.post("", status_code=201)
async def create_job(req: CreateJobRequest) -> JobResponse:
    # 分发到对应管道
    ...

@router.get("")
async def list_jobs(page: int = 1, page_size: int = 20):
    ...

@router.get("/{job_id}")
async def get_job(job_id: str):
    ...

@router.delete("/{job_id}")
async def delete_job(job_id: str):
    ...

@router.post("/{job_id}/regenerate", status_code=201)
async def regenerate_job(job_id: str) -> JobResponse:
    ...

@router.post("/{job_id}/confirm")
async def confirm_job(job_id: str, body: dict = Body(...)):
    ...
```

在 `router.py` 注册: `v1_router.include_router(jobs.router)`

**Step 4: 运行测试验证通过**

```bash
uv run pytest tests/test_api_v1.py -v
```

**Step 5: 实现 SSE 独立订阅端点 (Task 1.6)**

编写 `backend/api/v1/events.py`:
```python
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter(tags=["events"])

@router.get("/jobs/{job_id}/events")
async def subscribe_job_events(job_id: str):
    async def event_generator():
        # 从 job 的事件队列中读取
        ...
    return EventSourceResponse(event_generator())
```

**Step 6: 移除旧端点 (Task 1.7)**

从 `backend/main.py` 移除旧路由注册:
```python
# 移除这些行:
# app.include_router(generate_router)
# app.include_router(organic_router)
```

**Step 7: 运行全部测试**

```bash
uv run pytest tests/ -v
```

**Step 8: Commit**

```bash
git add backend/api/v1/ tests/test_api_v1.py backend/main.py
git commit -m "feat: unified /api/v1/ route blueprint with error handling and Job CRUD"
```

---

### Task 2: 数据持久化 `[backend]`

**Files:**
- Modify: `backend/db/models.py:1-76` — 补全字段
- Modify: `backend/db/repository.py:1-168` — 改为 Protocol + 实现
- Create: `backend/db/protocols.py` — Protocol 接口定义
- Create: `backend/db/file_storage.py` — FileStorage Protocol + LocalFileStorage
- Modify: `backend/models/job.py:91-165` — 移除内存 CRUD 函数
- Modify: `alembic/versions/` — 更新迁移脚本
- Reference: `backend/db/database.py:1-49` — 已有 async engine
- Reference: `alembic/env.py` — 已有 Alembic 配置
- Test: `tests/test_repository.py` (已有，增强)
- Test: `tests/test_database.py` (已有，增强)

**Step 1: 编写 Protocol 接口测试**

在 `tests/test_repository.py` 中添加:
```python
@pytest.mark.asyncio
async def test_job_repository_protocol_compliance():
    """SQLiteJobRepository 必须实现所有 Protocol 方法"""
    from backend.db.protocols import JobRepository
    from backend.db.repository import SQLiteJobRepository
    assert isinstance(SQLiteJobRepository(), JobRepository)
```

运行验证失败: `uv run pytest tests/test_repository.py::test_job_repository_protocol_compliance -v`

**Step 2: 创建 Protocol 接口**

`backend/db/protocols.py`:
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class JobRepository(Protocol):
    async def create(self, job_id: str, **kwargs) -> dict: ...
    async def get(self, job_id: str) -> dict | None: ...
    async def list(self, page: int, page_size: int, **filters) -> tuple[list[dict], int]: ...
    async def update(self, job_id: str, **kwargs) -> dict: ...
    async def delete(self, job_id: str) -> None: ...
    async def get_corrections(self, job_id: str) -> list[dict]: ...

@runtime_checkable
class FileStorage(Protocol):
    async def save(self, job_id: str, filename: str, data: bytes) -> str: ...
    async def get_url(self, job_id: str, filename: str) -> str: ...
    async def delete(self, job_id: str) -> None: ...
```

**Step 3: 实现 SQLiteJobRepository**

重构 `backend/db/repository.py`，使其实现 `JobRepository` Protocol。
已有的 CRUD 函数（`create_job`, `get_job` 等）封装为类方法。

**Step 4: 实现 LocalFileStorage**

`backend/db/file_storage.py`:
```python
import aiofiles
from pathlib import Path

class LocalFileStorage:
    def __init__(self, base_dir: str = "outputs"):
        self.base_dir = Path(base_dir)

    async def save(self, job_id: str, filename: str, data: bytes) -> str:
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        path = job_dir / filename
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return str(path)

    async def get_url(self, job_id: str, filename: str) -> str:
        return f"/outputs/{job_id}/{filename}"

    async def delete(self, job_id: str) -> None:
        import shutil
        job_dir = self.base_dir / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir)
```

**Step 5: 补全 ORM 模型**

修改 `backend/db/models.py`，添加缺失字段:
- `JobModel`: 添加 `printability_result` (JSON), `deleted_at` (DateTime)
- `UserCorrectionModel`: 确认 `field_path`, `original_value`, `corrected_value` 字段

**Step 6: 替换内存存储 (Task 2.6)**

搜索所有内存 CRUD 调用位置:
```bash
uv run grep -rn "create_job\|get_job\|update_job\|delete_job\|list_jobs\|clear_jobs" backend/models/job.py backend/api/
```

将 `backend/models/job.py` 中的内存函数标记为 deprecated。
将 `backend/api/v1/jobs.py` 中的调用改为注入 `JobRepository`。

**Step 7: 运行测试**

```bash
uv run pytest tests/test_repository.py tests/test_database.py -v
```

**Step 8: Commit**

```bash
git add backend/db/ backend/models/job.py alembic/
git commit -m "feat: activate SQLite persistence with Protocol abstraction"
```

---

### Task 3: 后端管道集成 `[backend]`

**Files:**
- Modify: `backend/api/v1/jobs.py` — 在 create_job 中调用 IntentParser
- Modify: `backend/api/generate.py:135-161` — `_match_template` 改为 fallback
- Modify: `backend/api/generate.py:208-248` — `_run_printability_check` + `_parse_intent` 整合
- Modify: `backend/api/organic.py:134-336` — 添加 PrintabilityChecker + 3MF
- Modify: `backend/pipeline/sse_bridge.py:80-98` — 添加 `printability_checked` 事件
- Modify: `backend/core/mesh_post_processor.py:43-91` — 添加 3MF 导出
- Modify: `backend/api/preview.py:1-204` — 迁移到 v1 + 添加超时+缓存
- Reference: `backend/core/intent_parser.py:1-256` — IntentParser 实现
- Reference: `backend/core/printability.py:1-522` — PrintabilityChecker 实现
- Reference: `backend/core/geometry_extractor.py:1-91` — 几何提取
- Reference: `backend/core/drawing_analyzer.py:1-275` — DrawingAnalyzer
- Test: `tests/test_pipeline_integration.py` (新建)

**Step 1: IntentParser 替换测试**

```python
@pytest.mark.asyncio
async def test_intent_parser_routes_correctly(client, mock_intent_parser):
    """文本输入应通过 IntentParser 路由到正确模板"""
    mock_intent_parser.parse.return_value = IntentSpec(
        part_type="rotational", template_name="flange_basic", confidence=0.9
    )
    resp = await client.post("/api/v1/jobs", json={"input_type": "text", "text": "法兰盘，外径100"})
    assert resp.status_code == 201
    mock_intent_parser.parse.assert_called_once()

@pytest.mark.asyncio
async def test_intent_parser_fallback(client, mock_intent_parser):
    """IntentParser 异常时 fallback 到 keyword 匹配"""
    mock_intent_parser.parse.side_effect = Exception("LLM unavailable")
    resp = await client.post("/api/v1/jobs", json={"input_type": "text", "text": "法兰盘"})
    assert resp.status_code == 201  # 仍然成功（走 fallback）
```

**Step 2: 实现 IntentParser 串联**

在 `backend/api/v1/jobs.py` 的 `create_job` 中:
```python
if req.input_type == "text":
    try:
        intent = await intent_parser.parse(req.text)
        if intent.confidence < 0.5:
            raise ValueError("Low confidence")
    except Exception:
        logger.warning("IntentParser failed, falling back to keyword matching")
        template, recommendations = _match_template(req.text)
```

**Step 3: PrintabilityChecker 串联测试 + 实现**

在精密管道完成事件前插入:
```python
# 在 sse_bridge.py 的 complete() 之前
printability = await _run_printability_check(step_path)
yield _sse_event(job_id, "printability_checked", "可打印性检查完成", 0.95)
```

在有机管道的 `_sse_event` 流中，MeshPostProcessor 完成后:
```python
try:
    printability = await _run_printability_check(mesh_path)
except Exception as e:
    logger.warning(f"Printability check failed: {e}")
    printability = None
```

**Step 4: HITL 图纸确认流**

修改精密管道 drawing 路径:
1. `DrawingAnalyzer` 完成后 → yield `drawing_spec_ready` SSE 事件
2. Job 状态设为 `awaiting_confirmation`
3. SSE 流暂停（等待 confirm 端点调用）
4. Confirm 端点收到确认 → 恢复 `generate_from_drawing_spec(confirmed_spec)`

**Step 5: 用户修正数据收集**

在 confirm 端点中:
```python
if original_spec and confirmed_spec:
    corrections = diff_specs(original_spec, confirmed_spec)
    for correction in corrections:
        await repository.save_correction(job_id, correction)
```

**Step 6: 有机管道 3MF 导出**

在 `backend/api/organic.py` 的完成逻辑中:
```python
# MeshPostProcessor 完成后
import trimesh
mesh = trimesh.load(processed_mesh_path)
threemf_path = output_dir / "model.3mf"
mesh.export(str(threemf_path), file_type="3mf")
threemf_url = f"/outputs/{job_id}/model.3mf"
```

**Step 7: 预览端点迁移**

将 `backend/api/preview.py` 的 `POST /api/preview/parametric` 迁移到 v1:
- 新路径: `POST /api/v1/preview/parametric`
- 添加 `asyncio.wait_for(render, timeout=5.0)` 硬超时
- 添加 `functools.lru_cache(maxsize=50)` 或自定义 LRU

**Step 8: 运行测试 + Commit**

```bash
uv run pytest tests/test_pipeline_integration.py tests/test_api_v1.py -v
git add backend/ tests/
git commit -m "feat: integrate IntentParser, PrintabilityChecker, HITL flow, 3MF export into pipeline"
```

---

### Task 4: 前端框架重建 `[frontend]`

**Files:**
- Create: `frontend/src/contexts/ThemeContext.tsx`
- Create: `frontend/src/layouts/WorkbenchLayout.tsx`
- Create: `frontend/src/layouts/TopNav.tsx`
- Modify: `frontend/src/App.tsx:1-46` — 路由重构
- Modify: `frontend/src/services/api.ts` — 对齐 /api/v1/
- Create: `frontend/src/hooks/useJobEvents.ts`
- Modify: `frontend/src/components/Viewer3D/index.tsx:1-153` — 暗色适配
- Modify: `frontend/src/layouts/MainLayout.tsx` — 替换为 WorkbenchLayout

**Step 1: ThemeProvider**

`frontend/src/contexts/ThemeContext.tsx`:
```tsx
import React, { createContext, useContext, useState, useEffect } from 'react';
import { ConfigProvider, theme as antdTheme } from 'antd';

type ThemeMode = 'light' | 'dark';

interface ThemeContextValue {
  mode: ThemeMode;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({ mode: 'light', toggle: () => {} });

export const useTheme = () => useContext(ThemeContext);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mode, setMode] = useState<ThemeMode>(
    () => (localStorage.getItem('theme') as ThemeMode) || 'light'
  );

  const toggle = () => setMode(prev => {
    const next = prev === 'light' ? 'dark' : 'light';
    localStorage.setItem('theme', next);
    return next;
  });

  return (
    <ThemeContext.Provider value={{ mode, toggle }}>
      <ConfigProvider theme={{
        algorithm: mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: mode === 'dark' ? '#4096ff' : '#1677ff',
        },
      }}>
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  );
};
```

**Step 2: WorkbenchLayout**

`frontend/src/layouts/WorkbenchLayout.tsx`:
```tsx
import React, { useState } from 'react';

interface WorkbenchLayoutProps {
  leftPanel?: React.ReactNode;
  centerPanel: React.ReactNode;
  rightPanel?: React.ReactNode;
}

export const WorkbenchLayout: React.FC<WorkbenchLayoutProps> = ({
  leftPanel, centerPanel, rightPanel
}) => {
  const [leftCollapsed, setLeftCollapsed] = useState(
    () => localStorage.getItem('leftPanelCollapsed') === 'true'
  );
  const [rightCollapsed, setRightCollapsed] = useState(
    () => localStorage.getItem('rightPanelCollapsed') === 'true'
  );

  // 折叠状态持久化到 localStorage
  // 布局: 左(240px) + 中(flex:1) + 右(300px)
  // <768px 时面板降级为底部 Drawer
  return (/* JSX */);
};
```

**Step 3: TopNav**

`frontend/src/layouts/TopNav.tsx`:
```tsx
// Logo + Tabs(精密建模/创意雕塑/零件库) + ThemeToggle(☀/☾) + Settings
```

**Step 4: 路由重构**

修改 `frontend/src/App.tsx`:
```tsx
<Routes>
  <Route path="/" element={<Navigate to="/precision" replace />} />
  <Route path="/precision" element={<PrecisionWorkbench />} />
  <Route path="/organic" element={<OrganicWorkbench />} />
  <Route path="/library" element={<LibraryPage />} />
  <Route path="/library/:jobId" element={<PartDetailPage />} />
  <Route path="/settings" element={<SettingsPage />} />
</Routes>
```

**Step 5: API 服务层重构**

修改 `frontend/src/services/api.ts`:
- 所有 URL 改为 `/api/v1/` 前缀
- 统一错误解析: `resp.json().error.code`

**Step 6: SSE Hook**

`frontend/src/hooks/useJobEvents.ts`:
```tsx
export function useJobEvents(jobId: string | null) {
  // EventSource 连接 GET /api/v1/jobs/{jobId}/events
  // 解析 SSE 事件，更新状态
  // 返回 { status, progress, message, events }
}
```

**Step 7: Viewer3D 暗色适配**

修改 `frontend/src/components/Viewer3D/index.tsx`:
```tsx
const { mode } = useTheme();
const bgColor = mode === 'dark' ? '#0a0a0a' : '#f0f0f0';
const ambientIntensity = mode === 'dark' ? 0.3 : 0.5;
```

**Step 8: TypeScript 验证 + Commit**

```bash
cd frontend && npx tsc --noEmit && npm run lint
git add frontend/
git commit -m "feat: three-panel workbench layout with light/dark theme"
```

---

### Task 5: 精密建模工作台 `[frontend]`

**Files:**
- Create: `frontend/src/components/InputPanel/index.tsx`
- Create: `frontend/src/components/DrawingSpecForm/index.tsx`
- Create: `frontend/src/components/PipelineProgress/index.tsx`
- Create: `frontend/src/components/PipelineLog/index.tsx`
- Modify: `frontend/src/components/ParamForm/index.tsx:1-117`
- Modify: `frontend/src/components/PrintReport/index.tsx`
- Modify: `frontend/src/pages/Generate/GenerateWorkflow.tsx`
- Create: `frontend/src/pages/PrecisionWorkbench/index.tsx`
- Reference: `frontend/src/types/generate.ts` — Job/DrawingSpec 类型
- Reference: `frontend/src/hooks/useJobEvents.ts` — SSE Hook
- Reference: `openspec/changes/whitebox-platform-productization/specs/workbench-ui/spec.md`

**Step 1: InputPanel 组件**

三合一输入面板（文本框 + 图纸上传 + 模板选择）。

**Step 2: DrawingSpecForm 组件**

将 DrawingSpec JSON 渲染为结构化可编辑表单。嵌套字段分组:
- 零件类型 (Select)
- 基体参数 (InputNumber × N)
- 特征列表 (动态表单, 可增删)
- 底部 "确认并生成" Button

**Step 3: ParamForm 适配 + PipelineProgress + PipelineLog**

**Step 4: 面板自动切换逻辑**

```tsx
function getLeftPanel(jobStatus: JobStatus): React.ReactNode {
  switch (jobStatus) {
    case 'idle': return <InputPanel />;
    case 'awaiting_confirmation': return <DrawingSpecForm /> or <ParamForm />;
    case 'generating': case 'refining': return <PipelineProgress />;
    case 'completed': return <DownloadPanel />;
  }
}

function getRightPanel(jobStatus: JobStatus): React.ReactNode {
  switch (jobStatus) {
    case 'idle': return <Recommendations />;
    case 'awaiting_confirmation': return <OriginalDrawingPreview />;
    case 'generating': return <PipelineLog />;
    case 'completed': return <PrintReport />;
  }
}
```

**Step 5: PrintReport 重构**

对接真实 `printability` 数据（从 job 完成事件获取）。

**Step 6: 验证 + Commit**

```bash
cd frontend && npx tsc --noEmit && npm run lint
git add frontend/
git commit -m "feat: precision workbench with auto-switching panels"
```

---

### Task 6: 创意雕塑工作台 `[frontend]`

**Files:**
- Create: `frontend/src/pages/OrganicWorkbench/index.tsx`
- Modify: `frontend/src/pages/OrganicGenerate/ConstraintForm.tsx:1-281` — 适配新布局
- Reference: `frontend/src/types/organic.ts`
- Reference: 复用 Task 5 的 PipelineProgress、PipelineLog、PrintReport

**与 Task 5 并行**。复用 PipelineProgress/PipelineLog，适配有机管道阶段。

**Commit:**
```bash
git commit -m "feat: organic workbench with constraint form and pipeline display"
```

---

### Task 7: 零件库 `[frontend]`

**Files:**
- Create: `frontend/src/components/JobCard/index.tsx`
- Create: `frontend/src/pages/Library/index.tsx`
- Create: `frontend/src/pages/Library/PartDetail.tsx`
- Reference: `openspec/changes/whitebox-platform-productization/specs/parts-library/spec.md`
- Reference: `frontend/src/services/api.ts` — GET /api/v1/jobs (列表)

**与 Task 5/6 并行**。

**Step 1: JobCard 组件**

3D 缩略图 + 零件名 + 时间 + 可打印状态 Badge:
```tsx
<Card hoverable cover={<MiniViewer3D modelUrl={job.model_url} />}>
  <Card.Meta title={job.name} description={dayjs(job.created_at).fromNow()} />
  <Tag color={printabilityColor}>{printabilityLabel}</Tag>
</Card>
```

**Step 2: LibraryPage**

卡片网格 + 筛选栏 + 分页:
```tsx
<Row gutter={[16, 16]}>
  {jobs.map(job => <Col span={6}><JobCard job={job} /></Col>)}
</Row>
<Pagination total={total} pageSize={20} />
```

**Step 3: PartDetail 页面**

`/library/:jobId` — 完整 3D 预览 + DfAM + 参数 + 下载/重生成。

**Commit:**
```bash
git commit -m "feat: parts library with card grid, search, filter, and detail view"
```

---

### Task 8: 实时参数预览 `[frontend]`

**Files:**
- Modify: `frontend/src/hooks/useParametricPreview.ts` (已有，增强)
- Modify: `frontend/src/components/Viewer3D/index.tsx:1-153` — 热更新逻辑
- Modify: `frontend/src/components/ParamForm/index.tsx` — 预览可用性指示

**Step 1: 增强 useParametricPreview Hook**

已有 `frontend/src/hooks/useParametricPreview.ts`，增强:
- 500ms debounce (lodash/debounce 或 useMemo)
- loading/error/data 状态管理
- 超时处理（408 → "预览不可用"）

**Step 2: Viewer3D 热更新**

接收新 GLB → 替换模型（保持相机位置）:
```tsx
useEffect(() => {
  if (previewGlbUrl) {
    // 保存当前相机
    const camera = cameraRef.current;
    // 加载新模型
    loadGLB(previewGlbUrl).then(model => {
      sceneRef.current.clear();
      sceneRef.current.add(model);
      // 恢复相机
    });
  }
}, [previewGlbUrl]);
```

**Step 3: 超时降级 + 可用性指示**

**Commit:**
```bash
git commit -m "feat: real-time parametric preview with 500ms debounce"
```

---

### Task 9: 端到端验证 `[test:e2e]`

**Files:**
- Create: `tests/e2e/test_precision_flow.py`
- Create: `tests/e2e/test_drawing_flow.py`
- Create: `tests/e2e/test_organic_flow.py`
- Create: `tests/e2e/test_theme.py`
- Create: `tests/e2e/test_persistence.py`
- Create: `tests/e2e/test_deprecated_api.py`

6 个 E2E 场景验证全链路。每个测试覆盖完整用户旅程。

**Commit:**
```bash
git commit -m "test: end-to-end validation for all pipelines and UI features"
```

---

## 验证命令速查

```bash
# 后端测试
uv run pytest tests/ -v

# 后端格式
uv run black . && uv run isort .

# 前端类型检查
cd frontend && npx tsc --noEmit

# 前端 lint
cd frontend && npm run lint

# 数据库迁移
uv run alembic upgrade head

# 启动服务验证
./scripts/start-v3.sh
```

## Layer 完成检查点

每个 Layer 完成时打 git tag:

```bash
git tag layer-1-api-persistence    # Group 1+2 完成
git tag layer-2-pipeline           # Group 3 完成
git tag layer-3-frontend-framework # Group 4 完成
git tag layer-4-frontend-features  # Group 5+6+7+8 完成
git tag layer-5-e2e-validation     # Group 9 完成
```
