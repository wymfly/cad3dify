# CADPilot 多视角深度差距综合分析报告

> 日期：2026-03-01
> 分析视角：Claude Opus（主导）+ 4 Agent Team + Codex (GPT) + Gemini 2.5 Pro
> 对照文档：产品商业化差距分析 + 白盒化工业级 AI 设计中台规范

---

## 一、六方视角来源

| 视角 | 负责模型/角色 | 聚焦维度 |
|------|-------------|---------|
| arch-analyst | Claude Agent | 架构对齐：SpecCompiler / 拦截器管道 / SSE / 双引擎隔离 / IR 规范化 |
| ux-analyst | Claude Agent | 前端白盒化：看板 / Reasoning / 热力图 / 实时预览 / HITL / 代码编辑 |
| data-analyst | Claude Agent | 数据飞轮：持久化 / 纠偏闭环 / 版本管理 / 导出 / Benchmark / 成本追踪 |
| innovation-analyst | Claude Agent | 竞品对标 / 护城河评估 / 创新机会 / 用户旅程 / 规模化 |
| Codex (GPT) | OpenAI o4-mini | 对抗性代码审查：安全漏洞 / 功能伪实现 / 枚举不匹配 |
| Gemini 2.5 Pro | Google | 架构命门：eval() 安全 / DfAM 伪三维 / 事件溯源 / SSE 粒度 |

---

## 二、跨视角共识（6/6 一致认同）

以下发现被所有 6 个视角独立确认，可信度最高：

### 共识 1：SpecCompiler 统一调度入口缺失 — P0/P1
- **arch-analyst**：路由逻辑散布 3 处（routing.py / vision_cad_pipeline.py / analysis.py），IntentParser.part_type 未驱动 TemplateEngine.find_matches
- **Codex**：text-path 模板未匹配时 hard-fail，无 LLM fallback（`generation.py:87`）
- **Gemini**：`eval()` 安全漏洞在 `template_engine.py:63`，这不是编译器而是字符串拼接
- **innovation-analyst**：keyword 匹配路由在竞品对比中是劣势（Zoo.dev 有原生 KCL 参数化）

### 共识 2：DfAM 3D 热力图完全不存在 — P0
- **ux-analyst**：Viewer3D 无顶点着色/shader/区域高亮能力，PrintReport 与 3D 模型零联动
- **Codex**：标记为 P0，`Viewer3D:26` 无任何 heatmap overlay path
- **Gemini**：最犀利 — `printability.py:139` 是"伪三维计算"，仅接受标量 dict 不接触 Mesh 数据，根本无法产生顶点级热力图
- **innovation-analyst**：用户旅程环节 4（可打印性检查）体验评分 ⭐（1/5），"厨房做好了菜但没人端出来"

### 共识 3：管道看板仅是线性进度条，非可交互节点图 — P1
- **ux-analyst**：Ant Design `<Steps>` 6 阶段线性组件，无点击回溯、无每节点耗时、无 DAG 拓扑
- **arch-analyst**：SSE 事件缺乏 `elapsed_ms`、`started_at`、`decision` 字段
- **Codex**：确认 `PipelineProgress:21` 和 `PipelineLog:42` 只是进度条+日志列表
- **Gemini**：`Steps` 组件没有绑定 `onClick` 事件，只有 `setInterval` 数字递增

### 共识 4：数据飞轮"收集有、闭环无" — P1
- **data-analyst**：correction_tracker.py 双写（JSON + DB）, ~170 条纠偏文件已积累，但清洗→分析→训练→部署全链路断裂
- **Gemini**：DB 关系断裂（注释中的绝望: "corrections may reference jobs in the in-memory store"），JSON 文件是"数据坟场"
- **innovation-analyst**：数据飞轮依赖链第一环（图纸 HITL）尚不完善，后面全断

### 共识 5："代码孤岛"模式 — 多个完整模块未串入主管道
- **data-analyst**：TokenTracker、CostOptimizer 代码 100% 完成但使用率 0%；Benchmark _run_single() 是 TODO
- **Codex**：pipeline_config 被 API 接收但执行时被忽略（"假功能"）；recommendations 字段存在但从未被填充
- **arch-analyst**：PrintabilityChecker 检测到 printable=False 也不中断管道（non-fatal 日志后继续执行）

---

## 三、独特发现（仅单一视角发现，需重点关注）

### Codex 独有发现

| 发现 | 严重度 | 详情 |
|------|--------|------|
| **template_engine.py `eval()` 安全漏洞** | P0 | `template_engine.py:72` 用 `eval()` 执行约束校验，且模板 API 无认证 — 远程代码执行风险 |
| **前后端枚举不匹配** | P1 | 前端 `DrawingSpecForm:24` 用大写 `ROTATIONAL`，后端 `part_types.py:11` 可能用小写 — 数据断层 |
| **sandbox.py 仅 subprocess 隔离** | P1 | `sandbox.py:154` 无 OS 级沙箱（如 Docker/gVisor），用户提交代码存在逃逸风险 |
| **LangGraph MemorySaver 重启丢失** | P1 | `builder.py:100` 用内存 checkpointer，进程重启后 HITL 中间状态全部丢失 |

### Gemini 独有发现

| 发现 | 详情 |
|------|------|
| **DfAM 是"伪三维计算"** | `printability.py:139` `check(geometry_info: dict)` 仅接受预计算的标量字典，不接触 mesh 拓扑。壁厚/悬垂检测依赖上游传入的浮点数而非自主计算 |
| **建议 Event-Sourcing 架构** | 用 Redis Streams 或 Kafka 替代当前 JSON 文件，用户每次操作均为 Event，微调模块作为 Consumer 自动提取训练数据 |
| **建议语义化几何 IR** | 构建 LLVM 风格的 IR 表示取代 Jinja2 模板拼接，实现 AST 级几何拓扑推演 |

### innovation-analyst 独有发现

| 发现 | 详情 |
|------|------|
| **双轨制全球独一无二** | 遍历所有竞品（Zoo.dev/Tripo3D/Meshy/Backflip/CADAM），无一同时覆盖精密+有机。CADPilot 拥有 12-18 个月窗口期 |
| **Backflip AI 是潜在颠覆者** | $30M 融资 + 1 亿合成数据训练 + 直接生成 SolidWorks 特征树。方向：Scan-to-CAD（逆向工程）|
| **被忽视的 6 个创新机会** | 逆向工程管道(Photo-to-CAD)、CAD Agent 对话式编辑、社区零件库、切片器集成、FEA 仿真、多材料建模 |
| **1000 用户成本估算** | 月 ~¥6,000（Tripo3D API 是最大变量，占 75%） |

---

## 四、统一差距优先级矩阵

综合 6 方评级，取最严格值：

| # | 差距 | 共识度 | 统一评级 | 影响维度 | 修复工作量 | ROI |
|---|------|--------|---------|---------|-----------|-----|
| 1 | `eval()` 安全漏洞 + 模板 API 无认证 | 2/6 | **P0** | 安全 | 1-2 天 | ★★★★★ |
| 2 | DfAM 标量计算 → 需升级为顶点级 + 3D 热力图 | 6/6 | **P0** | 核心卖点 | 7-10 天 | ★★★★★ |
| 3 | SpecCompiler 统一调度 + text-path fallback | 6/6 | **P0** | 架构 | 3-5 天 | ★★★★ |
| 4 | 用户系统（零 user_id 概念） | 1/6 | **P0** | 商业化 | 3-5 天 | ★★★★★ |
| 5 | 管道看板 → 可交互 DAG 节点图 | 6/6 | **P1** | 白盒化核心 | 5-7 天 | ★★★★ |
| 6 | SSE 事件标准化（耗时 + reasoning + start/end 配对） | 4/6 | **P1** | 白盒化基础 | 2-3 天 | ★★★★ |
| 7 | LangGraph MemorySaver → 持久化 checkpointer | 2/6 | **P1** | 可靠性 | 2-3 天 | ★★★ |
| 8 | pipeline_config 接受但执行忽略 | 1/6 | **P1** | 功能真实性 | 1-2 天 | ★★★ |
| 9 | DesignPackage 全固化（CadQuery 代码未持久化 + 无版本链） | 3/6 | **P1** | 数据资产 | 3-5 天 | ★★★ |
| 10 | AI 决策解释层（Reasoning Trace） | 4/6 | **P2** | 白盒化体验 | 3-5 天 | ★★★ |
| 11 | TokenTracker / CostOptimizer 串入管道 | 2/6 | **P2** | 成本控制 | 1-2 天 | ★★★ |
| 12 | Benchmark _run_single() 实装 | 3/6 | **P2** | 质量度量 | 2-3 天 | ★★★ |
| 13 | 零件库版本管理 + Fork + 参数重生成 | 2/6 | **P2** | 产品体验 | 5-7 天 | ★★ |
| 14 | IR 规范化（DrawingSpec 去自然语言） | 2/6 | **P2** | 架构质量 | 3-5 天 | ★★ |
| 15 | 拦截器/插件注册表 | 3/6 | **P2** | 扩展性 | 3-5 天 | ★★ |
| 16 | 数据飞轮训练闭环 | 4/6 | **P2** | 长期护城河 | 持续 | ★★★ |
| 17 | 后加工推荐系统 | 2/6 | **P2** | 差异化 | 3-5 天 | ★★ |
| 18 | 代码编辑器（Monaco 嵌入） | 1/6 | **P3** | 高级用户 | 7-10 天 | ★ |
| 19 | 切片器 / G-Code 集成 | 1/6 | **P3** | 远期 | 3-4 周 | ★ |
| 20 | 车间直连 API | 1/6 | **P4** | 远期 | 远期 | — |

---

## 五、"已完成但文档标注为缺失"的纠正

差距分析文档（2026-02-28）基于较早代码版本，以下项目已在后续迭代中实现：

| 行动项 | 文档判断 | 实际状态 | 确认视角 |
|--------|---------|---------|---------|
| PrintabilityChecker 接入管道 | "🔴 未串联" | ✅ `builder.py:48,79-80` 已接入 LangGraph 图 | arch-analyst, Codex |
| 图纸路径 HITL | "🔴 缺失" | ✅ DrawingSpecReview.tsx 完整实现（免责确认+置信度标签） | ux-analyst |
| OCR 辅助层 | "未调用" | ✅ `drawing_analyzer.py:148-149` 已导入调用 | arch-analyst |
| IntentParser | "keyword 匹配" | ✅ `analysis.py:35-44` LLM-driven IntentParser | arch-analyst |
| 有机 3MF 导出 | "始终 null" | ✅ `organic.py:270` mesh.export("3mf") | data-analyst |
| Job 持久化 | "纯内存" | ✅ SQLite + Alembic 迁移 | data-analyst |

**但 Codex 和 Gemini 指出**：虽然 PrintabilityChecker 在图中串联了，但 geometry_extractor.py 传入的壁厚/孔径等为 None → 检查实际不触发 → 属于"伪串联"。

---

## 六、30 天行动路线图（综合 6 方建议）

### Week 1：安全修复 + DfAM 真实化 [P0]

| 行动 | 来源 | 工作量 |
|------|------|--------|
| 消除 `eval()` — 改用 AST 安全评估或声明式约束 | Codex | 1 天 |
| 模板 API 增加认证中间件 | Codex | 0.5 天 |
| geometry_extractor.py 实装顶点级壁厚/悬垂计算 | Gemini, Codex | 3 天 |
| GLB vertex color 编码 DfAM 风险值 | ux-analyst, Gemini | 2 天 |
| Viewer3D ShaderMaterial 热力图渲染 | ux-analyst | 2 天 |

### Week 2：SpecCompiler + SSE 标准化 [P0-P1]

| 行动 | 来源 | 工作量 |
|------|------|--------|
| 创建 `spec_compiler.py` 统一路由：part_type → 模板优先 → LLM fallback | arch-analyst, Codex | 3 天 |
| text-path 模板 miss 时 fallback 到 coder（消除 hard-fail） | Codex | 1 天 |
| SSE 事件标准化：`node.started/completed` + `elapsed_ms` + `decision` | arch-analyst | 2 天 |

### Week 3：白盒化 UI + 数据串联 [P1]

| 行动 | 来源 | 工作量 |
|------|------|--------|
| PipelineProgress → ReactFlow DAG 看板（可点击回溯） | ux-analyst | 4 天 |
| TokenTracker / CostOptimizer 串入 LangGraph 节点 | data-analyst | 1 天 |
| pipeline_config 执行路径实装 | Codex | 1 天 |
| LangGraph checkpointer → PostgreSQL/Redis | Codex | 1 天 |

### Week 4：数据飞轮 + Benchmark [P1-P2]

| 行动 | 来源 | 工作量 |
|------|------|--------|
| 纠偏数据清洗脚本 + 统计仪表盘 | data-analyst | 2 天 |
| Benchmark _run_single() 实装（5 case 回归） | data-analyst, innovation-analyst | 2 天 |
| CadQuery 代码持久化到 JobModel | data-analyst | 1 天 |
| Reasoning Trace：关键节点添加 explanation 字段 | ux-analyst, arch-analyst | 2 天 |

---

## 七、核心结论

### 战略层面
> **CADPilot 的双轨制（精密+有机）定位全球独一无二，白盒化透明度理念远超所有竞品。12-18 个月的窗口期内，这是真正的护城河。** —— innovation-analyst

### 执行层面
> **项目呈现强烈的"代码孤岛"模式：TokenTracker、CostOptimizer、Benchmark、PrintabilityChecker、OCR、IntentParser 等模块代码完整精良，但彼此间及与主管道的集成严重不足。商业化的第一步不是写新代码，而是把已有代码串起来。** —— data-analyst

### 安全层面
> **`eval()` 在可编辑模板约束中 + 无认证 API = 远程代码执行漏洞。sandbox.py 仅 subprocess 隔离。这两个问题必须在任何公开部署前修复。** —— Codex

### 技术深度层面
> **所谓"DfAM 可打印性检查"是伪三维计算——仅接受标量字典，不接触 Mesh 拓扑。要实现规范中的 3D 热力图，必须引入 SDF 或 Ray-casting 算法在后端计算顶点级壁厚。** —— Gemini

### 一句话总结

**战略远超竞品，代码 80% 就绪，但"最后一公里"的管道串联 + 安全修复 + 白盒化 UI 是从"AI 玩具"进化为"工业级中台"的关键跨越。30 天内聚焦 eval() 修复、DfAM 真实化、SpecCompiler 统一调度、白盒化看板——代码基本都写好了，只需要"端菜上桌"。**
