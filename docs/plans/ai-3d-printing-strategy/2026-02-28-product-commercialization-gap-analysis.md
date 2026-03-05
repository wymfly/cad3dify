# 产品商业化差距分析：战略文档 × 双轨制架构 × 产品化建议 × 代码现状

## 一、三份材料的关系图谱

```
感知护城河战略（方向 A/B/C）
    ↓ 解决"输入端"问题
双轨制管道重构
    ↓ 解决"处理端"问题
5 项产品化建议
    ↓ 解决"商业闭环"问题
```

三份材料构成了从**技术底层→架构中层→商业顶层**的完整战略栈。但对照代码库，各层的落地程度差异极大。

---

## 二、逐项产品化建议 vs 代码现状 vs 战略文档对齐

### 建议 1：极客感前端工作台

| 要求 | 代码现状 | 关联战略文档 |
|------|---------|------------|
| 双模式入口 | ✅ 首页两张卡片：精密建模 + 创意雕塑 | 方向 B 的产品形态 |
| Three.js 3D 渲染 | ✅ react-three-fiber + GLTFLoader，360度旋转、线框模式 | — |
| 参数化表单 | ✅ ParamSlider/ParamField，滑块+约束校验 | 方向 B 核心 |
| **滑块调参→3D 实时预览** | 🔴 **不存在**。调参后需点"确认参数"→后端生成→刷新预览，无实时联动 | — |

**差距分析**：前端工作台的基础设施已经 75% 到位。最大的体验断层是**参数化实时预览**——这个功能需要前端本地运行 CadQuery（不现实）或后端提供"参数→GLB"的快速预览 API（~500ms 响应）。双轨制的模板引擎（Jinja2 渲染 CadQuery → 执行 → STEP → GLB）理论上可以做到秒级响应，但当前没有这个增量 API。

**建议优先级**：⭐⭐⭐ 高。"所见即所得"是促成客户下单的关键视觉冲击力。

---

### 建议 2：DfAM 智能拦截器

| 要求 | 代码现状 | 关联战略文档 |
|------|---------|------------|
| 壁厚检测 | ✅ `PrintabilityChecker._check_wall_thickness()` — FDM 0.8mm / SLA 0.3mm / SLS 0.7mm | 双轨制 2.2 "前置约束校验" |
| 悬垂角度检测 | ✅ `_check_overhang()` — FDM 45° / SLA 30° / SLS 90° | — |
| 自动体积+报价 | ✅ `estimate_material()` — PLA密度1.24g/cm³，80元/kg | — |
| **接入主管道** | 🔴 **完全断开**。`backend/api/` 没有任何路由调用 `PrintabilityChecker`，前端 `PrintReport` 组件存在但无数据源 | — |
| 红色高亮危险区域 | 🔴 **不存在**。无网格着色/标注功能 | — |

**差距分析**：这是最令人惋惜的维度——**代码全部写好了，但管道没串起来**。`PrintabilityChecker` 有完整的壁厚/悬垂/体积/成本计算，前端也有 `PrintReport` UI 组件，两端都存在但中间的 API 路由是空的。双轨制文档提到的"前置约束校验"在 `TemplateEngine.validate()` 中已实现参数级约束，但缺少几何级（壁厚/悬垂）的拦截。

**建议优先级**：⭐⭐⭐⭐ 最高。这是"玩具→工业工具"的分水岭，且实现成本极低（只需加一条 API 路由 + 在生成完成后调用 checker）。

---

### 建议 3：HITL 客户确认流

| 要求 | 代码现状 | 关联战略文档 |
|------|---------|------------|
| 文本路径 HITL | ✅ 完整。intent_parsed → awaiting_confirmation → ParamForm 确认 → 生成 | 感知战略方向 A |
| **图纸路径 HITL** | 🔴 **缺失**。`POST /generate/drawing` 直接进管道，不暂停等用户确认 DrawingSpec | 感知战略方向 A 核心诉求 |
| DrawingSpec 可视化 | 🔴 **缺失**。SSE 推送了 spec 数据但前端未渲染零件类型/尺寸/特征列表 | — |
| **免责确认机制** | 🔴 **完全不存在**。无 disclaimer/法律确认/精度免责提示 | — |

**差距分析**：这正是感知护城河文档方向 A 最核心的诉求。文档说"AI 提取 DrawingSpec 后必须拦截让用户确认"，但代码中图纸路径是"火箭发射"模式——上传即生成，用户无法在中途修改 VLM 看错的尺寸。

更重要的是，**HITL 是数据飞轮的入口**。用户修正 DrawingSpec 的每一次操作，就是一条 `[图片 → 修正后 JSON]` 的高质量标注数据。没有 HITL，方向 C 的数据飞轮永远转不起来。

**建议优先级**：⭐⭐⭐⭐ 最高。既是品控/法务必需，也是数据资产的源头。

---

### 建议 4：数据资产管理与版本控制

| 要求 | 代码现状 | 关联战略文档 |
|------|---------|------------|
| Job 持久化 | 🔴 **纯内存 `dict`**。进程重启全部丢失 | 感知战略方向 C "数据沉淀" |
| 我的零件库 | 🔴 **不存在**。无 /history、/my-parts 等页面 | — |
| 参数修改重生成 | ⚠️ 首次生成时可调参，但无"打开历史→改参数→重生成"的流程 | 双轨制 3.3 "数据资产沉淀" |
| **模板沉淀机制** | ✅ `TemplateEditor` 支持在线创建/编辑 YAML 模板 | 双轨制 "Day N 工程师编写 YAML 切入轨道 A" |

**差距分析**：这是**差距最大的维度（15% 完成度）**，也是三份文档共同指向的关键缺口。双轨制文档说"历史模型是结构化 JSON 参数，为二次编辑和微调提供数据资产"；感知战略方向 C 说"持续收集图片→JSON 数据对"——两者都依赖 Job 持久化，而当前是内存存储。

这个缺口意味着：
- 用户无法查看历史订单
- 高频零件无法自动识别为模板候选
- 微调训练数据为零
- B 端客户的反复打样修改流程无法支撑

**建议优先级**：⭐⭐⭐ 高。需要引入数据库（PostgreSQL 或 SQLite），但工作量相对大。

---

### 建议 5：文件格式导出矩阵

| 要求 | 代码现状 | 关联战略文档 |
|------|---------|------------|
| 消费级 STL/3MF | ✅ 精密建模支持 STEP/STL/3MF/GLB | — |
| 工业级 STEP | ✅ CadQuery 原生输出 | — |
| 有机路径 3MF | ⚠️ 前端有 3MF 按钮但后端不生成（threemf_url 始终 null） | — |
| **车间直连** | 🔴 **不存在**。无 webhook/G-Code/Octoprint 对接 | — |

**差距分析**：文件格式支持是**完成度最高的维度（80%）**。只需补上有机路径的 3MF 导出（一行 `mesh.export("model.3mf")`）即可基本完备。车间直连是远期功能，不影响 MVP。

**建议优先级**：⭐⭐ 中。有机 3MF 是 quick win，5 分钟修复。

---

## 三、感知护城河战略落地现状

### 方向 A：多模态 + CV + Human-in-the-loop

```
完成度：████████░░ 75%  组件齐全，未串联
```

| 子能力 | 状态 | 关键文件 |
|--------|------|---------|
| VLM 宏观拓扑提取 | ✅ qwen-vl-max，CoT+JSON 双输出 | `cad3dify/v2/drawing_analyzer.py`, `backend/core/drawing_analyzer.py` |
| OCR 精确数值提取 | ⚠️ 代码完整，未接入主管道 | `backend/core/ocr_assist.py` |
| 多模型投票/自洽 | ⚠️ 框架存在，默认关闭 | `backend/core/voting.py`, `PipelineConfig` |
| Human-in-the-loop | 🔴 文本路径有，图纸路径缺失 | `backend/api/generate.py` |

### 方向 B：参数化表单输入

```
完成度：█████████░ 90%  最完整
```

| 子能力 | 状态 | 关键文件 |
|--------|------|---------|
| 参数化模板系统 | ✅ 17 个 YAML 模板 + Jinja2 渲染 + 约束校验 | `backend/knowledge/templates/*.yaml` |
| 前端表单 UI | ✅ ParamSlider/ParamField + ConstraintAlert | `frontend/src/components/ParamForm/` |
| IntentParser | ⚠️ 代码完整，主流程未使用 | `backend/core/intent_parser.py` |
| 模板管理后台 | ✅ CRUD + 在线编辑 | `frontend/src/pages/Templates/` |

### 方向 C：数据飞轮 / 微调

```
完成度：██░░░░░░░░ 20%  框架存在，零数据积累
```

| 子能力 | 状态 | 关键文件 |
|--------|------|---------|
| 数据收集 | 🔴 不存在，内存 Job 无持久化 | `backend/models/job.py` |
| 标注工具 | 🔴 无 | — |
| Benchmark | ⚠️ 框架存在，_run_single() 是 TODO | `backend/benchmark/` |
| 微调代码 | ⚠️ SFTConfig + GRPO 奖励，无训练数据 | `scripts/training/` |

---

## 四、双轨制架构落地现状

| 设计要素 | 文档设想 | 代码实现 |
|---------|---------|---------|
| SpecCompiler 统一调度 | spec_compiler.py，按 part_type 路由 | 🔴 不存在。当前是 keyword 匹配 (`_match_template()`) |
| 轨道 A：模板引擎 | YAML + Jinja2 确定性渲染 | ✅ 17 个模板，TemplateEngine 完整 |
| 轨道 B：LLM 兜底 | ModelingStrategist → Coder | ✅ V2 管道完整运行 |
| 智能降级 (NoMatchingTemplateError) | try/except 路由切换 | ⚠️ 逻辑存在但缺少统一入口 |
| IR 规范化 | DrawingSpec 去自然语言依赖 | ⚠️ DrawingSpec 仍含 description 字段 |
| 前置约束校验 | 数学约束 + DfAM 拒绝 | ✅ TemplateEngine.validate() 参数级约束 |

---

## 五、全局优先级矩阵

综合三份材料和代码现状，按**商业影响 × 实现成本**排序：

| 优先级 | 行动项 | 影响维度 | 工作量 | 理由 |
|--------|--------|---------|--------|------|
| **P0** | PrintabilityChecker 接入主管道 | 建议2 | 1-2天 | 代码全部写好了，只需加 API 路由+管道调用。从"玩具"到"工业工具"的最小改动 |
| **P0** | 图纸路径 HITL 确认流 | 建议3 + 方向A | 3-5天 | DrawingSpec 可视化 + 暂停确认 + 数据飞轮入口。品控/法务/数据三重价值 |
| **P1** | OCR 辅助层接入 V2 管道 | 方向A | 2-3天 | 代码已写好（ocr_assist.py），只需在 DrawingAnalyzer 中调用 merge_ocr_with_vl() |
| **P1** | IntentParser 替换 keyword 匹配 | 建议1 + 方向B | 2天 | 已实现但主流程未使用。提升自然语言→模板路由的智能度 |
| **P1** | 有机路径 3MF 导出 | 建议5 | 0.5天 | 一行代码 quick win |
| **P2** | Job 持久化 + 数据库 | 建议4 + 方向C | 5-7天 | SQLite/PostgreSQL，Job/DrawingSpec/用户修正数据全部持久化。数据飞轮基础设施 |
| **P2** | 参数实时 3D 预览 | 建议1 | 5-7天 | 需要后端"快速预览 API"（模板引擎 → CadQuery → GLB，目标 <1s） |
| **P3** | 我的零件库 / 历史版本 | 建议4 | 7-10天 | 依赖 P2 数据库完成后 |
| **P3** | Benchmark 集成 + 数据标注工具 | 方向C | 5-7天 | _run_single() 是 TODO，需接入实际管道 |
| **P4** | 微调训练启动 | 方向C | 持续 | 等 P2+P3 积累足够数据后 |
| **P4** | 车间直连 API | 建议5 | 远期 | 需要对接具体车间系统 |

---

## 六、核心结论

1. **三份文档形成了完整的战略闭环**，方向正确，但代码落地存在明显的"最后一公里"问题——很多模块（OCR、PrintabilityChecker、IntentParser、Benchmark）代码已写好却未串入主管道。

2. **最高 ROI 的两个行动**：PrintabilityChecker 接入（改几行代码，价值巨大）和图纸路径 HITL（品控+法务+数据三重收益）。

3. **数据持久化是所有远期战略的基础设施**。没有数据库，建议 4（零件库）、方向 C（数据飞轮）、双轨制 3.3（数据资产沉淀）全部无法启动。这是 P2 但绝不能跳过。

4. **双轨制架构已经在代码中成型**（17 个 YAML 模板 + TemplateEngine + LLM fallback），但缺少文档中的 `SpecCompiler` 这个统一调度入口——当前是 keyword 匹配而非 spec-level 的智能路由。
