## Why

cad3dify 存在严重的"最后一公里"问题：PrintabilityChecker、OCR、IntentParser 等关键模块代码已写好却未串入主管道。图纸路径缺少 HITL 确认流（上传即生成，工业客户无法修正 AI 误识别），Job 存储是纯内存 dict（进程重启全部丢失），参数化预览不存在（调参后需完整重生成）。这些缺口直接阻碍了从"技术 Demo"到"可对外接单的 SaaS 产品"的转化。现在是补齐的时机——有机路径已完善，需要将重心转向商业化基础能力。

## What Changes

- 将已实现的 `PrintabilityChecker` 接入精密建模和有机路径管道，生成完成后自动运行壁厚/悬垂/材料/成本分析
- 新增几何信息提取器（`geometry_extractor`），从 STEP/mesh 提取 `geometry_info` 供 PrintabilityChecker 使用
- 为图纸路径添加 HITL 确认流：DrawingSpec 可视化 + 用户编辑 + 免责声明 + 确认后继续生成
- 接入 PaddleOCR 作为 OCR 引擎，与 VLM 结果融合提升图纸识别精度
- 用 IntentParser（LLM 驱动）替换现有 keyword 匹配的模板路由
- 补全有机路径 3MF 导出（前端按钮已有，后端未生成）
- **引入 SQLite 持久化层**（SQLAlchemy 2.0 + aiosqlite + Alembic），替换内存 dict，持久化 Job/DrawingSpec/用户修正数据
- 新增"我的零件库"历史页面（分页查询 + 改参数重生成）
- 新增参数实时预览 API（模板引擎→CadQuery→GLB，目标 <1s 响应）

## Capabilities

### New Capabilities

- `printability-pipeline`: 可打印性检查管道集成——几何信息提取、自动检查触发、结果通过 SSE 推送到前端 PrintReport
- `drawing-hitl`: 图纸路径 HITL 确认流——DrawingSpec 可视化/编辑/免责声明/用户修正数据收集
- `ocr-engine`: PaddleOCR 引擎集成——OCR 文本提取、尺寸解析、与 VLM 结果融合
- `intent-routing`: 智能意图路由——IntentParser 替换 keyword 匹配，LLM 驱动的零件类型识别和参数提取
- `data-persistence`: SQLite 数据持久化层——Job/Spec/修正数据持久化、Alembic 迁移、异步数据库操作
- `parts-library`: 零件库与历史管理——分页查询、详情查看、改参数重生成、删除
- `realtime-preview`: 参数实时预览——后端快速预览 API、缓存策略、前端 Three.js 热替换

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

**后端**：
- `backend/api/generate.py` — 主生成路由改动最大（HITL 暂停点 + IntentParser + PrintabilityChecker 调用）
- `backend/api/organic.py` — 添加 PrintabilityChecker + 3MF 导出
- `backend/models/job.py` — 从内存 dict 改为数据库模型
- `backend/core/` — 新增 geometry_extractor.py、ocr_engine.py；修改 drawing_analyzer.py
- `backend/db/` — 全新数据库层（database.py + models.py + repository.py + migrations/）
- `backend/api/preview.py` — 全新预览 API

**前端**：
- `frontend/src/pages/Generate/DrawingSpecReview.tsx` — 全新 HITL 确认界面
- `frontend/src/pages/History/` — 全新零件库页面
- `frontend/src/components/PrintReport/` — 对接真实数据
- `frontend/src/pages/Generate/` — 参数变更触发实时预览

**依赖**：
- 新增：paddleocr、aiosqlite、alembic
- SQLAlchemy 2.0 已在 pyproject.toml 但需确认版本

**数据**：
- 新增 SQLite 数据库文件（`backend/data/cad3dify.db`）
- Alembic 迁移脚本
