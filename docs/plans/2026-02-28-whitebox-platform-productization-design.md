# 白盒化工业级 AI 3D 设计中台 — 产品化设计方案

## 1. 产品定位

**CAD3Dify — 白盒化工业级 AI 3D 设计中台**

面向 B2B 工业客户（3D 打印车间、定制零件制造商），以"新手友好、过程透明"为交互哲学的 AI 辅助 3D 模型生成工具。

### 核心体验承诺

1. **所见即所得** — 参数调整 500ms 内 3D 预览热更新
2. **过程全透明** — 管道每个阶段实时可视，AI 决策可理解可追溯
3. **步骤可干预** — 关键节点强制暂停，用户核对 AI 识别结果后再继续
4. **结果可信赖** — DfAM 可制造性报告自动生成，材料/成本/工时一目了然

### 目标用户

B2B 工业客户为主（3D 打印车间、定制零件制造商），但交互友好性按新手标准设计。越专业的软件越复杂，越需要有友好的交互让用户的专注力集中上来。

### 双引擎并行

| | 精密建模引擎 | 创意雕塑引擎 |
|---|---|---|
| **输入** | 2D 工程图纸 / 参数化表单 | 自然语言 / 参考图片 |
| **内核** | CadQuery 确定性代码生成 | Tripo3D/Hunyuan3D Mesh 生成 |
| **输出** | STEP (B-Rep, 工业级) | GLB/STL/3MF (Mesh) |
| **精度** | 尺寸 100% 精确 | 造型自由，工程特征硬切削 |
| **HITL** | 图纸确认 → 参数调整 → 代码审查 | 描述确认 → 约束设置 → 后处理审查 |

### 用户旅程

**精密建模**：
```
上传图纸 → AI 读图 → 【HITL: 结构化表单确认】
  → 策略选择 → 代码生成 → 几何校验 → 智能优化
  → 【展示: DfAM 报告 + 3D 预览】 → 下载/导出
```

**创意雕塑**：
```
输入描述/上传参考图 → 【约束设置: 尺寸/孔位/平底】
  → AI 3D 生成 → 网格后处理 → 布尔切削
  → 【展示: DfAM 报告 + 3D 预览】 → 下载/导出
```

---

## 2. 三栏工作台架构

### 全局布局

```
┌──────────────────────────────────────────────────────────────┐
│  [Logo] CAD3Dify    精密建模 │ 创意雕塑 │ 零件库    [☀/☾] [⚙]  │
├────────────┬─────────────────────────────────┬───────────────┤
│            │                                 │               │
│  左面板     │        中央 3D 预览区            │   右面板       │
│  (240px)   │        (flex: 1)                │   (300px)     │
│  可折叠     │                                 │   可折叠       │
│            │                                 │               │
├────────────┤                                 ├───────────────┤
│  内容随管道  │  [正视] [俯视] [侧视] [等轴]    │  内容随状态    │
│  阶段切换   │  [线框] [实体]                   │  自动切换      │
└────────────┴─────────────────────────────────┴───────────────┘
```

### 顶部导航栏

- **左**：Logo + 产品名
- **中**：Tab 切换（精密建模 / 创意雕塑 / 零件库）— 取代当前侧边栏 Menu
- **右**：主题切换按钮（☀/☾）+ 设置入口

顶部 Tab 替代侧边栏可以最大化水平空间给三栏布局。零件库作为独立 Tab 而非子页面，强调其重要性。

### 左面板（智能切换）

左面板内容根据当前管道阶段**自动切换**，用户无需手动导航：

| 管道阶段 | 左面板内容 |
|---------|-----------|
| 初始 / 空闲 | 输入区（文本框 + 图纸上传 + 模板选择） |
| 图纸分析中 | 管道进度条（动画加载） |
| 图纸确认 (HITL) | DrawingSpec 结构化表单（可编辑） |
| 参数确认 (HITL) | ParamForm 参数表单（可编辑 + 实时预览） |
| 生成中 | 管道进度条（各阶段状态 + 耗时） |
| 优化中 | 优化进度（轮次 + 改进详情） |
| 完成 | 下载按钮组 + 格式选择 |

### 右面板（属性与报告）

| 管道阶段 | 右面板内容 |
|---------|-----------|
| 初始 / 空闲 | 模板推荐卡片 / 最近生成历史 |
| 分析中 / 生成中 | 管道日志（SSE 事件实时滚动） |
| 图纸确认 | 原始图纸预览（与左侧表单对照） |
| 完成 | DfAM 报告卡片（可打印性 / 材料费用 / 工时估算） |

### 中央 3D 预览区

- **始终可见**，不随管道阶段隐藏
- 初始状态：显示占位图或上一次生成的模型
- 生成中：显示 Skeleton/加载动画
- 完成后：加载 GLB 模型，支持旋转/缩放/预设视角
- 参数调整时：Debounce 500ms 后自动热更新

### 面板折叠

- 左右面板均支持一键折叠（`<<` / `>>`），折叠后中央区域自动扩展
- 折叠状态通过 `localStorage` 记忆
- 移动端（<768px）：面板变为底部抽屉

### 亮暗主题

技术方案：Ant Design 6 `ConfigProvider` + `theme.algorithm`

| Token | 亮色模式 | 暗色模式 |
|-------|---------|---------|
| colorPrimary | `#1677ff` | `#4096ff` |
| colorBgContainer | `#ffffff` | `#1f1f1f` |
| colorBgLayout | `#f5f5f5` | `#141414` |
| 3D 预览背景 | `#f0f0f0` | `#0a0a0a` |
| colorText | `rgba(0,0,0,0.88)` | `rgba(255,255,255,0.85)` |

3D 渲染区特殊处理：
- 暗色模式下 3D 背景用纯黑 `#0a0a0a`，环境光调低，模型更突出
- 亮色模式下用浅灰 `#f0f0f0`，标准 studio 环境

切换机制：顶栏按钮 → React Context → ConfigProvider algorithm 切换 → Three.js scene background 同步

---

## 3. 后端 API 标准化设计

### 设计原则

1. **一致的错误格式** — 所有错误返回 `{ "error": { "code": string, "message": string, "details"?: any } }`
2. **SSE 事件规范** — 统一的事件结构 `{ "job_id", "status", "stage", "message", "progress", ...payload }`
3. **RESTful 资源设计** — Job 作为核心资源，所有操作围绕 Job 生命周期
4. **版本预留** — 路径前缀 `/api/v1/`

### API 端点

#### Job 生命周期（统一两条管道）

```
POST   /api/v1/jobs                    # 创建 Job（文本/图纸/有机）
GET    /api/v1/jobs                    # 列表（分页+筛选）
GET    /api/v1/jobs/{id}               # 详情
POST   /api/v1/jobs/{id}/confirm       # HITL 确认（DrawingSpec/Params）
DELETE /api/v1/jobs/{id}               # 软删除
POST   /api/v1/jobs/{id}/regenerate    # 基于已有参数重新生成
GET    /api/v1/jobs/{id}/events        # SSE 事件流（独立连接）
GET    /api/v1/jobs/{id}/corrections   # 用户修正记录
```

`POST /api/v1/jobs` 通过 `input_type` 字段区分管道类型。SSE 事件流从"嵌入响应"改为"独立订阅"。

#### 模板管理

```
GET    /api/v1/templates               # 列表
GET    /api/v1/templates/{name}        # 详情
POST   /api/v1/templates               # 创建
PUT    /api/v1/templates/{name}        # 更新
DELETE /api/v1/templates/{name}        # 删除
POST   /api/v1/templates/{name}/validate  # 参数校验
```

#### 预览

```
POST   /api/v1/preview/parametric      # 模板参数 → GLB（5s 超时）
```

#### 导出

```
POST   /api/v1/export                  # STEP → STL/3MF/glTF 转换
```

#### DfAM 配置

```
GET    /api/v1/print-profiles          # 列表
GET    /api/v1/print-profiles/{name}   # 详情
POST   /api/v1/print-profiles          # 创建
PUT    /api/v1/print-profiles/{name}   # 更新
DELETE /api/v1/print-profiles/{name}   # 删除
```

#### 工程标准与 RAG

```
GET    /api/v1/standards               # 类别列表
GET    /api/v1/standards/{category}    # 条目
POST   /api/v1/standards/recommend     # 推荐
POST   /api/v1/standards/check         # 约束检查
GET    /api/v1/rag/search              # 搜索
```

#### Pipeline 配置

```
GET    /api/v1/pipeline/presets        # 预设列表
GET    /api/v1/pipeline/tooltips       # 字段提示
```

### SSE 事件规范

```typescript
interface SSEEvent {
  job_id: string;
  status: JobStatus;        // created | analyzing | awaiting_confirmation | generating | refining | post_processing | completed | failed
  stage?: string;           // 细分阶段标识
  message: string;          // 中文用户可读消息
  progress?: number;        // 0.0 - 1.0
  [key: string]: any;       // 阶段特定载荷
}
```

精密建模事件序列：
```
job_created → analyzing → drawing_spec_ready (暂停)
  → [用户确认] → generating → candidate(1/N) → ... → candidate(N/N)
  → geometry_valid → refining(1/M) → ... → refining(M/M)
  → printability_checked → completed
```

创意雕塑事件序列：
```
job_created → analyzing → generating(0.2-0.6)
  → post_processing:load → post_processing:repair → post_processing:scale
  → post_processing:boolean → post_processing:validate
  → printability_checked → completed
```

### 统一错误响应

```typescript
interface ErrorResponse {
  error: {
    code: string;           // "JOB_NOT_FOUND" | "VALIDATION_FAILED" | ...
    message: string;
    details?: any;
  }
}
```

### 数据持久化层

存储抽象接口：

```python
class JobRepository(Protocol):
    async def create(self, job: Job) -> Job: ...
    async def get(self, job_id: str) -> Job | None: ...
    async def update(self, job_id: str, **kwargs) -> Job: ...
    async def list(self, filters, page, page_size) -> Page[Job]: ...
    async def delete(self, job_id: str) -> None: ...

class FileStorage(Protocol):
    async def save(self, path: str, data: bytes) -> str: ...
    async def get_url(self, path: str) -> str: ...
    async def delete(self, path: str) -> None: ...
```

第一阶段：`SQLiteJobRepository` + `LocalFileStorage`
迁移预留：`PostgresJobRepository` + `S3FileStorage`

配置通过环境变量切换：
```
STORAGE_BACKEND=local    # local | s3
DATABASE_URL=sqlite+aiosqlite:///backend/data/cad3dify.db
```

---

## 4. 前端页面与组件设计

### 页面路由

```
/                          → 重定向到 /precision
/precision                 → 精密建模工作台
/organic                   → 创意雕塑工作台
/library                   → 零件库
/library/:jobId            → 零件详情
/templates                 → 模板管理
/settings                  → 设置
```

### 精密建模工作台 — 5 个阶段的面板布局

#### 阶段 1：输入（初始状态）

左面板：输入方式选择（图纸上传 / 模板选择）+ 管道配置
中央：欢迎占位 / 上次模型
右面板：推荐模板 + 最近生成历史

#### 阶段 2：图纸确认 (HITL)

左面板：DrawingSpec 结构化可编辑表单（零件类型、基体参数、特征列表）
中央：3D 预览（暂无模型，显示骨架）
右面板：原始图纸预览 + AI 推理摘要

#### 阶段 3：参数确认（模板路径 HITL）

左面板：ParamForm 参数表单（Slider/InputNumber/Switch，带推荐值）
中央：3D 预览（debounce 500ms 实时热更新）
右面板：约束校验结果 + 工程标准推荐

#### 阶段 4：生成中

左面板：管道进度条（阶段状态 + 耗时 + 候选进度）
中央：加载动画
右面板：SSE 事件实时日志

#### 阶段 5：完成

左面板：下载面板（STEP/STL/3MF/glTF）+ [保存到库] + [重新生成]
中央：3D 模型（可旋转缩放 + 4 预设视角）
右面板：DfAM 报告卡片（可打印性 / 材料费用 / 工时 / 打印配置选择）

### 创意雕塑工作台

布局与精密建模相同，但阶段内容不同：

| 阶段 | 左面板 | 右面板 |
|------|--------|--------|
| 输入 | 文本描述 + 参考图上传 + 质量选择 | 风格灵感 / 最近生成 |
| 约束设置 | 尺寸限制 + 工程切削（孔/平底/槽） | 约束说明 + 提示 |
| 生成中 | 管道进度（生成→后处理 5 步骤） | SSE 日志 |
| 完成 | 下载（GLB/STL/3MF）+ 网格统计 | DfAM 报告 |

### 零件库

卡片网格布局：3D 缩略图 + 零件名 + 生成时间 + 可打印状态标签。
支持按类型/状态筛选、搜索、分页。
点击卡片进入零件详情（完整 3D 预览 + DfAM + 参数 + 重生成）。

### 核心组件清单

| 组件 | 职责 | 复用/新建 |
|------|------|----------|
| `WorkbenchLayout` | 三栏可折叠布局框架 | **新建** |
| `ThemeProvider` | 亮暗主题 Context + 切换 | **新建** |
| `PipelineProgress` | 管道阶段进度条 | **重构** 现有 |
| `DrawingSpecForm` | HITL 图纸确认表单 | **新建** |
| `ParamForm` | 参数输入表单 | **复用** 现有 |
| `Viewer3D` | Three.js 3D 预览 | **复用**，加暗色适配 |
| `PrintReport` | DfAM 报告卡片 | **重构**，对接真实数据 |
| `DownloadPanel` | 多格式下载面板 | **重构** 现有 |
| `JobCard` | 零件库列表项 | **新建** |
| `PipelineLog` | SSE 事件实时日志 | **新建** |
| `InputPanel` | 输入面板（文本+图纸+模板三合一）| **新建** |
| `ConstraintForm` | 有机管道约束设置表单 | **复用** 现有 |

---

## 5. 核心功能模块串联设计

### 模块 1：PrintabilityChecker 管道集成

**现状**：代码完整（`backend/core/printability.py`），3 预设配置，完整检查链。未被管道调用。

**串联**：在 STEP/Mesh 生成后、`completed` 事件前调用。新增 `printability_checked` SSE 事件。失败不阻断管道。

### 模块 2：HITL 图纸确认流

**现状**：文本路径有完整 HITL，图纸路径直接生成。

**串联**：
```
POST /api/v1/jobs (input_type=drawing)
  → DrawingAnalyzer → drawing_spec_ready (暂停)
POST /api/v1/jobs/{id}/confirm (body: confirmed_spec)
  → generate_from_drawing_spec → completed
```

前端 `DrawingSpecForm`：DrawingSpec JSON → 可编辑表单 + 原图对照。修改记录存入 `user_corrections` 表。

### 模块 3：IntentParser 替换 keyword 匹配

**现状**：IntentParser 完整但未用，主流程用 `_match_template()` keyword 匹配。

**串联**：IntentParser 优先 + keyword fallback。

### 模块 4：数据持久化实装

**现状**：ORM 完整（models + repository），API 用内存 dict。

**串联**：所有 `job_store[id]` 替换为 `await repository.create/update/get()`。配置 Alembic 迁移。

### 模块 5：实时参数预览

**现状**：`POST /api/preview/parametric` 已存在（5s 超时，内存缓存）。

**串联**：前端 `useParametricPreview` hook，debounce 500ms 调用预览 API，更新 Viewer3D。超时显示"预览不可用"。

### 模块 6：有机管道 3MF 导出

**现状**：前端有按钮，后端 `threemf_url` 始终 null。

**串联**：`processed_mesh.export("model.3mf", file_type="3mf")`。

---

## 6. 实施路线

### 实施分层（质量优先）

按**后端基础 → 后端功能 → 前端框架 → 前端功能**递进，确保每层高质量。

#### Layer 1：后端 API 标准化

- API 路由统一为 `/api/v1/` 前缀
- 统一错误响应格式（新建 `backend/api/errors.py`）
- Job 生命周期接口统一
- SSE 事件独立端点
- 数据持久化切换（内存 dict → SQLite ORM）
- Alembic 迁移配置

#### Layer 2：后端功能串联

- PrintabilityChecker 接入管道
- HITL 图纸确认流拆分
- IntentParser 启用（+ keyword fallback）
- 有机 3MF 导出
- 用户修正数据收集

#### Layer 3：前端框架重建

- ThemeProvider（亮暗切换 + localStorage 记忆）
- WorkbenchLayout（三栏可折叠框架）
- 顶部 Tab 导航（替代侧边栏）
- 路由重构
- API Service 层对齐 `/api/v1/`

#### Layer 4：前端功能页面

- PrecisionWorkbench（5 阶段面板切换）
- DrawingSpecForm（HITL 结构化表单）
- OrganicWorkbench（适配三栏布局）
- LibraryPage（卡片列表 + 详情）
- PrintReport 重构（对接真实数据）
- PipelineLog（SSE 日志滚动）
- Viewer3D 暗色适配

---

## 7. 技术选型

| 技术点 | 选型 | 理由 |
|--------|------|------|
| UI 框架 | Ant Design 6.3.1 | 已在用，企业级组件齐全 |
| 主题系统 | antd ConfigProvider + theme.algorithm | 原生亮暗切换，零外部依赖 |
| 状态管理 | React Context + useReducer | 管道状态复杂度适中 |
| 3D 渲染 | react-three-fiber + drei | 已在用，生态完善 |
| HTTP 客户端 | fetch API（原生） | SSE 需要 ReadableStream |
| 数据库 | SQLite + aiosqlite（→ PostgreSQL） | 已有 ORM，环境变量切换 |
| 文件存储 | 本地 outputs/（→ S3） | 接口抽象，后期切换 |
| SSE 框架 | sse-starlette 3.2.0 | 已在用，稳定 |
| CAD 内核 | CadQuery 2.4.0 | OCCT 内核，工业级 |
| 网格处理 | trimesh + PyMeshLab + manifold3d | 完整后处理链 |

---

## 8. 质量保证

| 维度 | 标准 |
|------|------|
| 后端测试 | pytest-asyncio，API + 核心逻辑完整覆盖 |
| 前端类型 | TypeScript strict，`npx tsc --noEmit` 零错误 |
| 前端 Lint | ESLint + React Hooks 规则 |
| API 文档 | FastAPI 自动生成 OpenAPI spec |
| SSE 测试 | curl + 脚本验证事件序列完整性 |
| E2E 验证 | 每个管道完整走通 |

---

## 9. 关键设计决策追踪

| 决策 | 结论 | 理由 |
|------|------|------|
| 目标用户 | B2B 工业客户，交互按新手标准 | 越专业越需要友好交互 |
| UI 风格 | 亮暗双模式 | Ant Design 6 原生支持，成本可控 |
| 布局 | 三栏工作台 | 3D 预览最大化，专业工具感 |
| 导航 | 顶部 Tab 取代侧边栏 | 最大化水平空间 |
| 新手引导 | 步骤式向导（面板自动切换） | 用户无需知道下一步做什么 |
| MVP 范围 | 全功能 P0-P2 | 不赶工期，追求质量 |
| 部署 | 混合（SQLite → PostgreSQL） | 先单机，架构预留迁移 |
| 用户系统 | 暂不需要 | 单机 = 单客户 |
| 实时预览 | Debounce 500ms | 平衡体验和资源 |
| HITL | 结构化表单 + 原图对照 | 新手可读，专家可改 |
| DfAM 展示 | 结构化报告卡片 | 复用 PrintReport，开发适中 |
| 实施路径 | 全面重构（后端 API + 前端重设计）| 质量优先，不赶工期 |
