# 产品商业化全栈推进设计

## 背景

基于 [产品商业化差距分析](ai-3d-printing-strategy/2026-02-28-product-commercialization-gap-analysis.md) 的发现，cad3dify 存在大量"最后一公里"问题——PrintabilityChecker、OCR、IntentParser、Benchmark 等模块代码已写好却未串入主管道。本设计采用**方案 A（管道串联优先）**，按 P0→P1→P2 顺序实施，优先串联断裂管道产出可演示价值，再建数据基础设施。

## 关键决策

| 维度 | 决策 | 理由 |
|------|------|------|
| 实施顺序 | 管道串联优先（方案 A） | ROI 最高的改动最先落地 |
| 数据库 | SQLite + SQLAlchemy 2.0 + aiosqlite | 零部署、后期可迁移 PG |
| OCR 引擎 | PaddleOCR | 中文工程图纸最强、本地部署零成本 |
| 目标用户 | 工业客户 + SaaS 级体验 | 专业性 + 易用性并重 |
| 实时预览 | 后端快速预览 API | 模板引擎→CadQuery→GLB，目标 <1s |

---

## P0：管道串联（1-2 周）

### P0.1 PrintabilityChecker 管道接入

**问题**：`PrintabilityChecker` 代码完整（壁厚/悬垂/孔径/肋板/构建体积/材料/时间估算），但零 API 暴露，前端 `PrintReport` 组件无数据源。

**方案**：

```
生成完成（STEP/GLB 已存在）
  ↓ 自动触发
geometry_extractor.extract(step_path) → geometry_info
  ↓
PrintabilityChecker.check(geometry_info, profile) → PrintabilityResult
  ↓
存入 Job.printability_result
  ↓
SSE completed 事件附带 printability 数据
  ↓
前端 PrintReport 渲染
```

**设计决策**：

| 决策 | 选择 | 理由 |
|------|------|------|
| 触发时机 | 生成完成后自动运行 | 工业客户期望每次生成都带检查报告 |
| geometry_info 来源 | 从 STEP 文件提取 | 比 mesh 更精确 |
| 打印配置来源 | 默认 FDM Standard，可切换 | 已有 `/print-profiles` API |
| 结果展示 | 嵌入生成结果卡片 | 生成流程的自然延伸 |

**文件变更**：

| 文件 | 操作 |
|------|------|
| `backend/core/geometry_extractor.py` | 新建：从 STEP 提取 geometry_info |
| `backend/api/generate.py` | 修改：生成完成后调用 checker |
| `backend/api/organic.py` | 修改：有机路径完成后调用 checker |
| `frontend/src/components/PrintReport/` | 修改：对接真实数据 |

### P0.2 图纸路径 HITL 确认流

**问题**：文本路径有完整 HITL（awaiting_confirmation → ParamForm 确认），但图纸路径是"火箭发射"模式——上传即生成，用户无法修正 VLM 误识别的尺寸。

**方案**：

```
POST /generate/drawing
  ↓
Stage 1: DrawingAnalyzer → DrawingSpec
  ↓
SSE event: drawing_spec_ready（附带 DrawingSpec JSON）
  ↓ ← 暂停！等待用户确认
前端渲染 DrawingSpec：
  - 识别的零件类型 + 置信度
  - 尺寸参数列表（可编辑）
  - 识别的特征列表
  - 免责声明 checkbox
  ↓
POST /generate/drawing/{job_id}/confirm
  body: { confirmed_spec, disclaimer_accepted }
  ↓
Stage 2-4: 继续 V2 管道生成
```

**免责声明**（工业客户必需）：
```
⚠️ AI 识别结果仅供参考
- AI 从图纸中提取的尺寸和特征可能存在偏差
- 生成的 3D 模型需人工核验后方可用于生产
- 本系统不对因 AI 误识别导致的加工损失承担责任

☐ 我已阅读并理解上述免责声明
```

**数据飞轮入口**：用户每次修正 DrawingSpec 的操作，自动记录为 `[图片, 原始spec, 修正spec]` 三元组——这是方向 C 微调训练的高质量标注数据源。

**文件变更**：

| 文件 | 操作 |
|------|------|
| `backend/api/generate.py` | 修改：拆分图纸管道，加暂停点 + confirm 端点 |
| `backend/models/job.py` | 修改：添加 drawing_spec / drawing_spec_confirmed 字段 |
| `frontend/src/pages/Generate/DrawingSpecReview.tsx` | 新建：DrawingSpec 可视化 + 编辑 + 免责确认 |

### P0.3 有机路径 3MF 导出

**问题**：前端有 3MF 按钮但 `threemf_url` 始终 null。

**修复**：在 `organic.py` 的导出阶段添加 `mesh.export("model.3mf")`。Quick win，一行代码。

---

## P1：智能层升级（1 周）

### P1.1 PaddleOCR 引擎接入

**问题**：`ocr_assist.py` 依赖注入设计完善但无实际 OCR 引擎。

**技术选型**：

| 方案 | 精度（工程图） | 延迟 | 成本 | 中文 |
|------|-------------|------|------|------|
| **PaddleOCR** ✅ | ★★★★★ | ~200ms | 零 | 最强 |
| Tesseract | ★★☆ | ~500ms | 零 | 弱 |
| Qwen-VL OCR | ★★★ | ~2s | API 付费 | 强 |
| Cloud Vision | ★★★★ | ~300ms | API 付费 | 好 |

**集成设计**：

```
图纸上传
  ↓
PaddleOCR 提取文本区域 + 坐标 + 置信度
  ↓
OCRAssistant.extract_dimensions() → 过滤非尺寸文本
  ↓
merge_ocr_with_vl(ocr_dims, vl_dims)
  数值字段 → OCR 优先（φ50±0.1 等精确数字）
  语义字段 → VLM 优先（零件类型、特征描述）
  ↓
融合后 DrawingSpec（更高精度）
```

**文件变更**：

| 文件 | 操作 |
|------|------|
| `backend/core/ocr_engine.py` | 新建：PaddleOCR 包装函数 |
| `backend/core/drawing_analyzer.py` | 修改：Stage 1 后调用 merge_ocr_with_vl |
| `pyproject.toml` | 修改：添加 paddleocr 依赖 |

### P1.2 IntentParser 替换 keyword 匹配

**问题**：`generate.py` 的 `_match_template()` 使用纯 keyword 匹配，IntentParser 已实现但未使用。

**设计**：

```
用户输入文本
  ↓
IntentParser.parse(text) → IntentSpec
  ├─ part_type: PartType（LLM 推断）
  ├─ known_params: dict
  ├─ missing_params: list
  └─ confidence: float
  ↓
if confidence > 0.7 and matching_template:
  → 轨道 A：参数化模板
else:
  → 轨道 B：LLM 代码生成
```

**替换策略**：
- `_match_template()` 保留为 fallback（IntentParser 不可用时降级）
- 主路径改为 IntentParser
- LLM 调用使用 `qwen-coder-plus`（低成本、结构化输出好）

**文件变更**：

| 文件 | 操作 |
|------|------|
| `backend/api/generate.py` | 修改：主路径替换为 IntentParser |
| `backend/core/intent_parser.py` | 可能微调：适配当前 PipelineConfig |

---

## P2：数据基础设施（1-2 周）

### P2.1 SQLite 持久化

**问题**：`_jobs: dict[str, Job] = {}`，进程重启全部丢失。

**数据模型**：

```sql
-- 主表：Job 记录
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    input_type TEXT NOT NULL,        -- text / drawing / organic
    input_text TEXT,
    input_image_path TEXT,
    intent_spec JSON,                -- IntentParser 输出
    precise_spec JSON,               -- 确认后的精确参数
    drawing_spec JSON,               -- VLM 识别结果（原始）
    drawing_spec_confirmed JSON,     -- 用户修正版本
    printability_result JSON,        -- PrintabilityChecker 输出
    result JSON,                     -- 生成结果
    output_files JSON,               -- {step, glb, stl, 3mf} 路径
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT                      -- 预留，当前无认证
);

-- 数据飞轮核心：用户修正记录
CREATE TABLE user_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    field_path TEXT NOT NULL,         -- "overall_dimensions.diameter"
    original_value TEXT NOT NULL,
    corrected_value TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**技术选择**：

| 决策 | 选择 | 理由 |
|------|------|------|
| ORM | SQLAlchemy 2.0 + aiosqlite | async-first，与主项目一致 |
| 迁移 | Alembic | 标准选择，后期迁移 PG 无缝 |
| JSON 字段 | SQLite JSON1 | 结构复杂的 Spec 用 JSON 存储 |
| user_corrections | 独立表 | 数据飞轮核心资产 |

**文件变更**：

| 文件 | 操作 |
|------|------|
| `backend/db/` | 新建：database.py + models.py + repository.py |
| `backend/db/migrations/` | 新建：Alembic 迁移脚本 |
| `backend/models/job.py` | 修改：从内存 dict 改为 DB 操作 |

### P2.2 我的零件库 / 历史

**API**：
```
GET  /jobs?page=1&page_size=20&status=completed  # 分页查询
GET  /jobs/{job_id}                               # 详情
POST /jobs/{job_id}/regenerate                    # 改参数重生成
DELETE /jobs/{job_id}                             # 删除
```

**前端**：
- 新增 `/history` 页面 — 卡片列表（缩略图 + 零件名 + 时间 + 状态）
- 详情页 — 3D 预览 + 参数 + 打印报告 + 下载
- "改参数重生成"按钮 — ParamForm 预填历史参数

---

## P2：体验升级（1 周）

### P2.3 参数实时预览 API

**问题**：调参后需"确认参数"→后端完整生成→刷新预览，无实时联动。

**设计**：

```
前端 ParamForm 参数变更
  ↓ debounce 300ms
POST /preview/parametric
  body: { template_name, params }
  ↓
TemplateEngine.render() → CadQuery code → execute → STEP → GLB (draft quality)
  ↓
返回 GLB URL
  ↓
前端 Three.js 热替换 GLB
```

**性能优化**：

| 步骤 | 目标延迟 |
|------|---------|
| Jinja2 渲染 | <10ms |
| CadQuery 执行 | <500ms |
| STEP→GLB 转换 | <200ms |
| 网络传输 | <100ms |
| **总计** | **<800ms** |

**优化手段**：
1. 预览用 `mesh_quality=draft`（减少面数 70%）
2. 相同参数组合缓存命中直接返回
3. Jinja2 预编译模板缓存
4. CadQuery 在 worker 进程执行，不阻塞 API

**文件变更**：

| 文件 | 操作 |
|------|------|
| `backend/api/preview.py` | 新建：预览 API |
| `backend/core/template_engine.py` | 修改：添加 draft 模式 |
| `frontend/src/pages/Generate/` | 修改：参数变更触发预览请求 |

---

## 全局优先级矩阵

| 阶段 | 行动项 | 工作量 | 依赖 |
|------|--------|--------|------|
| **P0.1** | PrintabilityChecker 管道接入 | 1-2 天 | 无 |
| **P0.2** | 图纸路径 HITL 确认流 | 3-5 天 | 无 |
| **P0.3** | 有机路径 3MF 导出 | 0.5 天 | 无 |
| **P1.1** | PaddleOCR 引擎接入 | 2-3 天 | P0.2（HITL 流程中展示 OCR 辅助结果） |
| **P1.2** | IntentParser 替换 keyword | 2 天 | 无 |
| **P2.1** | SQLite 持久化 | 5-7 天 | 无（但尽早做，所有数据开始沉淀） |
| **P2.2** | 我的零件库 / 历史 | 3-5 天 | P2.1 |
| **P2.3** | 参数实时预览 API | 3-5 天 | 无 |

**并行化机会**：
- P0.1 / P0.2 / P0.3 可并行
- P1.1 / P1.2 可并行
- P2.1 与 P0/P1 可并行（越早引入越好）
- P2.3 与 P2.2 可并行

---

## 架构影响评估

本设计**不改变**现有模块边界和接口契约：
- PrintabilityChecker 是现有模块的管道接入
- HITL 是在现有 SSE 流中增加暂停点
- PaddleOCR 通过已有的依赖注入接口接入
- IntentParser 替换内部实现，对外 API 不变
- SQLite 替换内存 dict，Job API 签名不变

唯一的新增系统能力是**数据持久化层**，但它是基础设施而非业务接口。
