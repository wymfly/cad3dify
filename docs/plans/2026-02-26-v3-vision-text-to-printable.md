# V3 愿景：自然语言到工业级 3D 打印文件

> **状态:** 愿景设计，待技术选型确认
> **日期:** 2026-02-26
> **前置:** V2 当前能力见 `docs/V2-CURRENT-CAPABILITIES.md`

---

## 1. 终极目标

**通过自然语言（可附加参数描述、参考图像），生成可直接打印的工业级精度 3D 打印文件。**

### 输入形态

| 输入类型 | 示例 | 优先级 |
|---------|------|-------|
| 纯文字描述 | "做一个法兰盘，外径100，6个螺栓孔" | P0 |
| 文字 + 参数表 | "法兰盘" + {外径:100, 厚度:12, 孔数:6, 孔径:10, PCD:70} | P0 |
| 文字 + 参考图片 | "类似这张图的法兰盘，但外径改为150" | P1 |
| 2D 工程图纸 | 标准工程图纸（V2 已有能力） | P1（继承） |

### 输出要求

| 要求 | 目标值 |
|------|-------|
| 尺寸精度 | < 0.5%（工业级） |
| 输出格式 | STEP + STL/3MF（可直接切片打印） |
| 可打印性 | 通过可打印性检查（壁厚、悬挑、最小特征） |
| 参数化 | 输出带参数化代码，可二次修改 |

---

## 2. 核心设计：交互式精确化

### 2.1 设计哲学

**不要试图一次性从模糊输入得到精确输出，而是通过多轮交互逐步精确化。**

关键洞察：
- 自然语言天然是**模糊的**，工业图纸天然是**精确的**
- LLM 擅长**理解意图、选择方案**，不擅长精确数值计算
- 参数化引擎擅长**精确几何生成**，不擅长理解自然语言
- 因此让 LLM 做意图理解，让参数化引擎做精确计算，人在环路做参数确认

### 2.2 交互流程

```
用户输入（自然语言 + 可选参数/图片）
  │
  ├─ Phase 1: 意图理解（LLM）
  │    ├─ 识别零件类型
  │    ├─ 提取已知参数
  │    ├─ 识别缺失参数
  │    └─ 输出: IntentSpec（零件类型 + 已知参数 + 缺失参数列表）
  │
  ├─ Phase 2: 参数补全与确认（LLM + 工程标准库 + 用户交互）
  │    ├─ 基于工程标准推荐缺失参数的默认值
  │    ├─ 生成参数确认表（含推荐值和推荐理由）
  │    ├─ 用户确认/修改参数
  │    ├─ 约束检查（参数间一致性）
  │    └─ 输出: PreciseSpec（所有参数精确确定）
  │
  ├─ Phase 3: 精确建模（参数化模板引擎）
  │    ├─ 选择匹配的参数化模板
  │    ├─ 填入精确参数 → 生成 CadQuery/OpenSCAD 代码
  │    ├─ 执行代码 → STEP 文件
  │    ├─ 几何验证（体积、包围盒、拓扑）
  │    └─ 输出: STEP 文件 + 参数化源码
  │
  ├─ Phase 4: 可打印性优化
  │    ├─ 可打印性检查（壁厚、悬挑、最小特征、底面稳定性）
  │    ├─ 自动修正建议（如：增加圆角减少应力集中）
  │    ├─ 推荐打印方向和支撑策略
  │    ├─ 预估材料用量和打印时间
  │    └─ 输出: 可打印性报告
  │
  └─ Phase 5: 输出
       ├─ STEP 文件（精确几何）
       ├─ STL/3MF 文件（可控网格密度）
       ├─ 参数化源码（可二次修改）
       └─ 打印建议报告
```

### 2.3 精度保障机制

为什么这个架构能达到工业级精度（< 0.5%）：

| 误差源 | V2 方式（图纸输入） | V3 方式（交互式） | 为什么能消除 |
|--------|------------------|-----------------|------------|
| 输入理解误差 | VL 读图 5-10% | 用户确认参数 ~0% | 人在环路消除模糊性 |
| 参数缺失 | VL 猜测 | 工程标准推荐 + 用户确认 | 不猜测，问用户 |
| 代码生成误差 | LLM 自由生成 | 参数化模板填参数 | 模板结构预验证 |
| 数值计算误差 | LLM 输出数值 | 参数化引擎精确计算 | 数学计算不经过 LLM |

**精度公式：**
```
V2 精度 = VL准确率 × LLM代码正确率 = 90% × 70% ≈ 63%
V3 精度 = 用户确认率 × 模板正确率 = ~100% × ~99% ≈ 99%
```

---

## 3. 核心模块设计

### 3.1 IntentParser — 意图解析器

```python
class IntentSpec(BaseModel):
    """用户意图的结构化表示"""
    part_category: str          # "法兰盘" / "轴" / "支架" / ...
    part_type: PartType | None  # 映射到已知类型，未知则 None
    known_params: dict          # 用户明确给出的参数
    missing_params: list[str]   # 需要补全的参数
    constraints: list[str]      # 用户提到的约束 ("需要和M10螺栓配合")
    reference_image: str | None # 参考图片路径
    raw_text: str               # 原始输入文本
```

**LLM 的任务范围：** 只做意图理解和参数提取，不做数值计算或代码生成。

### 3.2 EngineeringStandards — 工程标准知识库

```python
class EngineeringStandards:
    """工程标准查询引擎"""

    def recommend_params(
        self, part_category: str, known_params: dict
    ) -> list[ParamRecommendation]:
        """基于已知参数和工程标准，推荐缺失参数的默认值。"""
        ...

    def check_constraints(
        self, params: dict
    ) -> list[ConstraintViolation]:
        """检查参数间的几何/工程一致性。"""
        ...
```

**知识库内容：**

| 标准类别 | 示例 | 用途 |
|---------|------|------|
| 螺栓/螺母标准 | M6-M30 通孔直径、沉孔尺寸 | 孔径推荐 |
| 法兰标准 | GB/T 9119, ASME B16.5 | PCD、螺栓数推荐 |
| 配合公差 | H7/h6, H7/p6 | 轴孔配合尺寸 |
| 键/键槽标准 | GB/T 1096 | 键槽宽度、深度 |
| 齿轮参数 | 模数系列、压力角 | 齿轮参数推荐 |
| 3D 打印约束 | FDM/SLA 最小壁厚、最小孔径 | 可打印性检查 |

### 3.3 ParametricTemplateEngine — 参数化模板引擎

```python
class ParametricTemplate:
    """参数化零件模板"""
    name: str                          # "standard_flange"
    part_type: PartType
    parameters: list[ParamDefinition]  # 参数定义（名称、类型、范围、默认值）
    code_template: str                 # CadQuery 参数化代码模板
    validation_rules: list[Rule]       # 参数间约束规则

class ParamDefinition(BaseModel):
    name: str
    display_name: str       # "外径"
    unit: str               # "mm"
    type: str               # "float" / "int"
    min_value: float | None
    max_value: float | None
    default: float | None
    depends_on: list[str]   # 依赖的其他参数
```

**与 V2 知识库的区别：**

| 维度 | V2 TaggedExample | V3 ParametricTemplate |
|------|-----------------|----------------------|
| 代码 | 固定示例代码 | 参数化模板，可填参数 |
| 精度 | 依赖 LLM 模仿示例 | 模板预验证，参数精确注入 |
| 灵活性 | 有限（示例覆盖范围） | 同一模板覆盖该类型所有尺寸 |
| 维护 | 每个尺寸一个示例 | 每种零件类型一个模板 |

### 3.4 PrintabilityChecker — 可打印性检查器

```python
class PrintProfile(BaseModel):
    """打印机配置"""
    technology: str          # "FDM" / "SLA" / "SLS"
    min_wall: float          # 最小壁厚 mm
    max_overhang: float      # 最大悬挑角度 degrees
    min_hole: float          # 最小孔径 mm
    min_feature: float       # 最小特征尺寸 mm
    build_volume: tuple      # 构建体积 (x, y, z) mm
    layer_height: float      # 层高 mm

PRESET_PROFILES = {
    "fdm_standard": PrintProfile(
        technology="FDM", min_wall=0.8, max_overhang=45,
        min_hole=0.5, min_feature=0.4,
        build_volume=(220, 220, 250), layer_height=0.2,
    ),
    "sla_standard": PrintProfile(
        technology="SLA", min_wall=0.3, max_overhang=30,
        min_hole=0.2, min_feature=0.15,
        build_volume=(145, 145, 175), layer_height=0.05,
    ),
}
```

---

## 4. 与 V2 的关系

### 可复用的模块

| V2 模块 | V3 中的角色 |
|---------|-----------|
| DrawingSpec 数据模型 | 扩展为 PreciseSpec，向后兼容 |
| ModelingStrategist（策略选择） | 升级为 TemplateSelector |
| CodeGenerator（代码生成） | 替换为 ParametricTemplateEngine |
| SmartRefiner（智能改进） | 保留用于参考图片输入场景 |
| validators（几何验证） | 保留并增强 |
| 知识库示例 | 逐步替换为参数化模板 |

### 需要新建的模块

| 新模块 | 职责 |
|-------|------|
| IntentParser | 自然语言 → IntentSpec |
| EngineeringStandards | 工程标准知识库 + 参数推荐 |
| ParametricTemplateEngine | 参数化模板管理 + 代码生成 |
| InteractiveConfirmer | 参数确认交互逻辑 |
| PrintabilityChecker | 可打印性检查 + 优化建议 |
| FormatExporter | STEP → STL/3MF 转换 |

---

## 5. 分阶段实施路线

### Phase A: V2 质量优化（当前）

目标：夯实基础，精度从 5-10% 提升到 3-5%

工作内容：`docs/plans/2026-02-26-v2-quality-improvement-directions.md` 中的 13 个方案

### Phase B: 参数化模板引擎 + STL 输出

目标：为常见零件类型建立参数化模板，输出可打印文件

关键工作：
1. 设计 ParametricTemplate 数据模型
2. 为 7 种 PartType 各建 2-3 个参数化模板（共 ~20 个）
3. 实现 STEP → STL/3MF 转换
4. 基础可打印性检查

精度提升：模板覆盖的零件类型精度提升到 < 1%

### Phase C: 意图解析 + 交互式参数确认

目标：支持自然语言输入，通过交互达到工业级精度

关键工作：
1. IntentParser（LLM → IntentSpec）
2. 工程标准知识库（螺栓、法兰、配合公差等）
3. 参数推荐 + 约束检查
4. 交互确认流程（对话/表单）

精度提升：用户确认参数的零件精度达到 < 0.5%

### Phase D: 多模态输入 + 高级能力

目标：支持参考图片输入、复杂零件、高级打印优化

关键工作：
1. 参考图片理解（复用 V2 的 VL 能力 + 交互确认）
2. 复杂零件模板（sweep、loft、渐开线齿轮）
3. 高级可打印性优化（支撑策略、打印方向优化）
4. 多材料支持

---

## 6. 技术选型待确认

| 决策点 | 选项 | 待评估 |
|--------|------|-------|
| CAD 内核 | CadQuery（当前）vs FreeCAD vs OpenSCAD vs Build123d | 参数化模板开发效率、社区活跃度 |
| 参数化引擎 | 自研模板 vs 现有参数化 CAD 框架 | 灵活性 vs 开发成本 |
| 工程标准库 | 自建 vs 开源数据集 | 覆盖度、许可证 |
| LLM | 通义千问 vs GPT vs 本地模型 | 意图理解精度、成本、延迟 |
| 前端交互 | 对话式 vs 表单式 vs 混合 | 用户体验 |

> 技术选型需要对比调研现有开源项目，见下一步工作。

---

## 7. 成功标准

| 阶段 | 衡量指标 | 目标值 |
|------|---------|-------|
| Phase B | 参数化模板覆盖的零件类型数 | ≥ 7 种 |
| Phase B | 模板生成零件的尺寸精度 | < 1% |
| Phase B | STL 输出可直接切片打印 | 100% |
| Phase C | 自然语言输入的意图识别准确率 | ≥ 95% |
| Phase C | 参数推荐被用户接受的比例 | ≥ 80% |
| Phase C | 最终输出精度（用户确认后） | < 0.5% |
| Phase D | 支持的零件复杂度 | 10+ 特征 |
| Phase D | 可打印性检查通过率 | ≥ 95% |
