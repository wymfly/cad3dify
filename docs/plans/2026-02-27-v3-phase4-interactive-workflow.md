# Phase 4: 交互式工作流 + 意图理解 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现自然语言输入 → 意图理解 → 参数推荐/确认 → 代码生成 → 可打印性检查的完整交互流程

**Architecture:** IntentParser (LLM) 解析自然语言为 IntentSpec，EngineeringStandards 推荐参数，前端确认后生成 PreciseSpec，TemplateEngine/Pipeline 生成模型，PrintabilityChecker 检查可打印性

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, Jinja2, React 18, TypeScript, Ant Design

**OpenSpec:** `openspec/changes/2026-02-26-v3-text-to-printable/tasks.md` Task 4.1-4.9

---

## 依赖图

```
Wave 1 (并行):  T4.1 ──┐     T4.3 ──┐     T4.7 ──┐
                        │             │             │
Wave 2 (并行):  T4.2 ◄─┘     T4.4 ◄─┘     T4.8 ◄─┘
                  │             │     │             │
Wave 3 (并行):   │           T4.5 ◄──┘     T4.9 ◄──┘
                  │             │
Wave 4 (串行):  T4.6 ◄─────────┘
```

**域标签:** [backend]×6, [frontend]×4, [agent]×1 = 3 域
**可并行:** Wave 1 有 3 个, Wave 2 有 3 个
**总任务:** 9

---

## Task 1: IntentSpec 数据模型 (T4.1)

**标签:** [backend]
**Skill:** —

**Files:**
- Create: `backend/models/intent.py`
- Test: `tests/test_intent_model.py`

### 设计

```python
# backend/models/intent.py
from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel
from backend.knowledge.part_types import DrawingSpec, PartType

class IntentSpec(BaseModel):
    """用户意图的结构化表示 — IntentParser 的输出"""
    part_category: str                     # "法兰盘" / "轴" / "支架"
    part_type: Optional[PartType] = None   # 映射到已知类型
    known_params: dict[str, float] = {}    # 用户明确给出的参数
    missing_params: list[str] = []         # 需要补全的参数名
    constraints: list[str] = []            # 用户约束条件
    reference_image: Optional[str] = None  # 参考图片路径
    confidence: float = 0.0                # 整体置信度 0-1
    raw_text: str = ""                     # 原始输入文本

class ParamRecommendation(BaseModel):
    """单个参数推荐"""
    param_name: str
    value: float
    unit: str = "mm"
    reason: str                            # 推荐理由
    source: str = ""                       # 来源标准 (e.g. "GB/T 9119")

class PreciseSpec(DrawingSpec):
    """所有参数精确确定的零件规范 — IntentSpec 经用户确认后的产物"""
    source: Literal["text_input", "drawing_input", "image_input"] = "text_input"
    confirmed_by_user: bool = True
    intent: Optional[IntentSpec] = None
    recommendations_applied: list[str] = []

def intent_to_precise(
    intent: IntentSpec,
    confirmed_params: dict[str, float],
    base_body_method: str = "extrude",
) -> PreciseSpec:
    """将 IntentSpec + 用户确认参数 → PreciseSpec"""
    ...
```

### 测试重点

- IntentSpec 序列化/反序列化 round-trip
- PreciseSpec 继承 DrawingSpec 所有字段
- ParamRecommendation 数据完整性
- `intent_to_precise()` 转换逻辑：
  - 已知参数 + 确认参数合并到 overall_dimensions
  - part_type 正确映射
  - source 字段保留
- 边界：confidence=0.0, empty params, None part_type

### 验证命令

```bash
pytest tests/test_intent_model.py -v
```

---

## Task 2: IntentParser 实现 (T4.2)

**标签:** [backend] [agent]
**Skill:** —
**依赖:** Task 1 (IntentSpec)

**Files:**
- Create: `backend/core/intent_parser.py`
- Test: `tests/test_intent_parser.py`

### 设计

```python
# backend/core/intent_parser.py
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel
from backend.models.intent import IntentSpec
from backend.knowledge.part_types import PartType
from backend.models.template import ParamDefinition

# LLM structured output schema — IntentParser 使用 function calling
class ParsedIntent(BaseModel):
    """LLM 直接输出的结构化意图（中间格式）"""
    part_category: str
    part_type_guess: str           # LLM 猜测的类型名
    extracted_params: dict[str, float]
    extracted_constraints: list[str]
    confidence: float

# 零件类型映射表（中文 → PartType）
PART_TYPE_MAPPING: dict[str, PartType] = {
    "法兰": PartType.ROTATIONAL,
    "法兰盘": PartType.ROTATIONAL,
    "圆盘": PartType.ROTATIONAL,
    "轴": PartType.ROTATIONAL_STEPPED,
    "阶梯轴": PartType.ROTATIONAL_STEPPED,
    "板": PartType.PLATE,
    "板件": PartType.PLATE,
    "支架": PartType.BRACKET,
    "L型": PartType.BRACKET,
    "壳体": PartType.HOUSING,
    "箱体": PartType.HOUSING,
    "齿轮": PartType.GEAR,
    # ... 更多映射
}

class IntentParser:
    """LLM 驱动的意图解析器 — 只做理解，不做计算

    测试中通过注入 mock LLM callable 避免真实 API 调用。
    """

    def __init__(self, llm_callable=None):
        self._llm = llm_callable  # async (prompt, schema) -> ParsedIntent

    async def parse(
        self,
        user_input: str,
        image: Optional[bytes] = None,
    ) -> IntentSpec:
        """解析自然语言输入为 IntentSpec"""
        # 1. 调用 LLM (structured output)
        # 2. 映射 part_type_guess → PartType
        # 3. 根据 PartType 查 ParamDefinition 识别 missing_params
        # 4. 组装 IntentSpec
        ...

    def _resolve_part_type(self, guess: str) -> Optional[PartType]:
        """模糊匹配零件类型"""
        ...

    def _identify_missing_params(
        self,
        part_type: PartType,
        known_params: dict[str, float],
    ) -> list[str]:
        """根据模板的 ParamDefinition 识别缺失参数"""
        ...
```

### 测试策略

**关键：测试中注入 mock LLM callable，不调用真实 API。**

```python
# tests/test_intent_parser.py
async def mock_llm(prompt, schema):
    """模拟 LLM 返回结构化意图"""
    return ParsedIntent(
        part_category="法兰盘",
        part_type_guess="法兰",
        extracted_params={"外径": 100, "孔数": 6},
        extracted_constraints=["需要和M10螺栓配合"],
        confidence=0.85,
    )

async def test_parse_flange():
    parser = IntentParser(llm_callable=mock_llm)
    result = await parser.parse("做一个法兰盘，外径100，6个螺栓孔")
    assert result.part_type == PartType.ROTATIONAL
    assert result.known_params["外径"] == 100
    assert "孔数" in result.known_params or "孔数" in [p for p in result.known_params]
```

### 测试重点

- `_resolve_part_type()`: 中文名 → PartType 映射（精确 + 模糊）
- `_identify_missing_params()`: 已知参数 vs ParamDefinition → 缺失列表
- `parse()` 端到端（mock LLM）：自然语言 → IntentSpec
- 20+ 自然语言输入用例（覆盖 7 种零件类型）
- 边界：无 LLM 返回、空输入、无法识别的零件类型
- confidence 计算逻辑

### 验证命令

```bash
pytest tests/test_intent_parser.py -v
```

---

## Task 3: 工程标准知识库 (T4.3)

**标签:** [backend]
**Skill:** —

**Files:**
- Create: `backend/core/engineering_standards.py`
- Create: `backend/knowledge/standards/bolts.yaml`
- Create: `backend/knowledge/standards/flanges.yaml`
- Create: `backend/knowledge/standards/tolerances.yaml`
- Create: `backend/knowledge/standards/keyways.yaml`
- Create: `backend/knowledge/standards/gears.yaml`
- Test: `tests/test_engineering_standards.py`

### 设计

```python
# backend/core/engineering_standards.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Optional
import yaml
from pydantic import BaseModel

_STANDARDS_DIR = Path(__file__).parent.parent / "knowledge" / "standards"

class StandardEntry(BaseModel):
    """标准数据条目"""
    category: str          # "bolt", "flange", "tolerance", "keyway", "gear"
    name: str              # "M10", "DN50", "H7/h6"
    params: dict[str, Any] # 标准参数

class ParamRecommendation(BaseModel):
    """参数推荐结果（复用 intent.py 的定义或独立）"""
    param_name: str
    value: float
    unit: str = "mm"
    reason: str
    source: str = ""

class ConstraintViolation(BaseModel):
    """约束违反"""
    constraint: str
    message: str
    severity: str = "error"  # error / warning

class EngineeringStandards:
    """工程标准知识库 — 参数推荐 + 约束检查"""

    def __init__(self, standards_dir: Optional[Path] = None):
        self._dir = standards_dir or _STANDARDS_DIR
        self._data: dict[str, list[StandardEntry]] = {}
        self._load()

    def _load(self):
        """从 YAML 加载所有标准数据"""
        ...

    def list_categories(self) -> list[str]:
        """列出所有标准分类"""
        ...

    def get_category(self, category: str) -> list[StandardEntry]:
        """获取某类标准详情"""
        ...

    def recommend_params(
        self,
        part_type: str,
        known_params: dict[str, float],
    ) -> list[ParamRecommendation]:
        """基于已知参数推荐缺失值

        规则示例:
        - 法兰外径100 → 推荐 PCD=70, 孔数=4, 孔径=11 (GB/T 9119)
        - M10 螺栓 → 通孔直径=11mm
        - 齿轮模数=2 → 推荐标准齿数
        """
        ...

    def check_constraints(
        self,
        part_type: str,
        params: dict[str, float],
    ) -> list[ConstraintViolation]:
        """参数间工程一致性检查

        规则示例:
        - PCD 必须 < 外径
        - 螺栓孔径 < PCD/(孔数*2) (不重叠)
        - 壁厚 ≥ 最小壁厚
        """
        ...
```

### YAML 数据结构

```yaml
# backend/knowledge/standards/bolts.yaml
category: bolt
entries:
  - name: M6
    through_hole: 6.6
    counterbore_dia: 11
    counterbore_depth: 6
    head_height: 4
  - name: M8
    through_hole: 9
    counterbore_dia: 14
    counterbore_depth: 8
    head_height: 5.5
  - name: M10
    through_hole: 11
    counterbore_dia: 17.5
    counterbore_depth: 10
    head_height: 7
  # ... M12-M30

# backend/knowledge/standards/flanges.yaml
category: flange
standard: GB/T 9119
entries:
  - name: DN25
    outer_diameter: 115
    thickness: 14
    pcd: 85
    hole_count: 4
    hole_diameter: 14
    bore_diameter: 26
  - name: DN50
    outer_diameter: 160
    thickness: 16
    pcd: 125
    hole_count: 4
    hole_diameter: 18
    bore_diameter: 51
  # ... DN80-DN300
```

### 测试重点

- 标准数据加载（5 个 YAML 文件）
- `recommend_params()`:
  - 法兰外径 100 → 推荐 PCD/孔数/孔径
  - M10 螺栓 → 通孔直径 11mm
  - 齿轮模数 2 → 标准齿数系列
- `check_constraints()`:
  - PCD < 外径 → OK
  - PCD > 外径 → violation
  - 孔重叠检测
- 边界：未知 part_type、空参数、无推荐

### 验证命令

```bash
pytest tests/test_engineering_standards.py -v
```

---

## Task 4: 工程标准 API + 前端 (T4.4)

**标签:** [backend] [frontend]
**Skill:** `frontend-design`, `ant-design`
**依赖:** Task 3 (EngineeringStandards)

**Files:**
- Create: `backend/api/standards.py`
- Modify: `backend/main.py` — 注册 standards router
- Create: `frontend/src/types/standard.ts`
- Create: `frontend/src/pages/Standards/index.tsx`
- Create: `frontend/src/pages/Standards/StandardBrowser.tsx`
- Create: `frontend/src/pages/Standards/StandardQuery.tsx`
- Test: `tests/test_standards_api.py`

### API 设计

```python
# backend/api/standards.py
router = APIRouter()

@router.get("/standards")
async def list_categories() -> list[dict[str, str]]:
    """列出所有标准分类"""
    ...

@router.get("/standards/{category}")
async def get_category(category: str) -> list[dict]:
    """获取某类标准详情（如螺栓标准表）"""
    ...

@router.post("/standards/recommend")
async def recommend(body: dict) -> list[dict]:
    """基于已知参数推荐缺失值
    body: {"part_type": "rotational", "known_params": {"outer_diameter": 100}}
    """
    ...

@router.post("/standards/check")
async def check_constraints(body: dict) -> list[dict]:
    """约束检查
    body: {"part_type": "rotational", "params": {"outer_diameter": 100, "pcd": 120}}
    """
    ...
```

### 前端设计

- `StandardBrowser`: 按类别展示标准数据表格（Ant Design Table）
- `StandardQuery`: 选择类别 → 输入已知参数 → 显示推荐结果

### 测试重点

- 4 个 API 端点的正常/异常响应
- 推荐端到端：输入"M10 螺栓" → 返回通孔直径推荐
- 前端构建通过

### 验证命令

```bash
pytest tests/test_standards_api.py -v
cd frontend && npm run build
```

---

## Task 5: 参数确认 UI (T4.5)

**标签:** [frontend]
**Skill:** `frontend-design`, `ant-design`, `ui-ux-pro-max`
**依赖:** Task 3 (EngineeringStandards 用于推荐值)

**Files:**
- Create: `frontend/src/components/ParamForm/index.tsx`
- Create: `frontend/src/components/ParamForm/ParamSlider.tsx`
- Create: `frontend/src/components/ParamForm/ParamField.tsx`
- Create: `frontend/src/components/ParamForm/ConstraintAlert.tsx`

### 设计

```typescript
// ParamForm 根据 ParamDefinition 动态生成表单
interface ParamFormProps {
  params: ParamDefinition[];
  values: Record<string, number | string | boolean>;
  recommendations?: ParamRecommendation[];
  violations?: ConstraintViolation[];
  onChange: (name: string, value: number | string | boolean) => void;
  onConfirm: () => void;
}

// ParamSlider 实时调整
interface ParamSliderProps {
  param: ParamDefinition;
  value: number;
  recommendation?: ParamRecommendation;
  onChange: (value: number) => void;
}
```

### 功能

1. 动态参数表单（根据 ParamDefinition 自动生成 input/slider）
2. 每个参数显示推荐值 + 推荐理由 + 来源标准
3. 参数滑块实时调整（范围由 min/max 确定）
4. 约束违反实时红色提示
5. 确认按钮提交 PreciseSpec

### 测试重点

- 前端构建通过
- 组件渲染无错误（手动验证）

### 验证命令

```bash
cd frontend && npm run build
```

---

## Task 6: 生成工作台集成 (T4.6)

**标签:** [frontend] [backend]
**Skill:** `frontend-design`, `streaming-api-patterns`
**依赖:** Task 2 (IntentParser), Task 5 (ParamForm)

**Files:**
- Modify: `backend/api/generate.py` — 完整实现 SSE 流 + job 会话
- Create: `backend/models/job.py` — Job 状态模型
- Modify: `frontend/src/pages/Generate/index.tsx` — 集成完整工作流
- Create: `frontend/src/pages/Generate/ChatInput.tsx` — 对话式输入
- Create: `frontend/src/pages/Generate/GenerateWorkflow.tsx` — SSE 状态机

### 后端：Job 会话协议

```python
# backend/models/job.py
class JobStatus(str, Enum):
    CREATED = "created"
    INTENT_PARSED = "intent_parsed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    GENERATING = "generating"
    REFINING = "refining"
    COMPLETED = "completed"
    FAILED = "failed"
    VALIDATION_FAILED = "validation_failed"

class Job(BaseModel):
    job_id: str
    status: JobStatus
    input_type: str
    intent: Optional[IntentSpec] = None
    precise_spec: Optional[PreciseSpec] = None
    result: Optional[dict] = None
    error: Optional[str] = None

# 内存 Job Store
_jobs: dict[str, Job] = {}
```

```python
# backend/api/generate.py — 完整实现
@router.post("/generate")
async def generate(...) -> EventSourceResponse:
    """支持两种模式:
    1. text 模式: 文本 → IntentParser → 暂停确认 → 生成
    2. drawing 模式: 图纸 → V2 Pipeline → 直接生成
    """
    ...

@router.post("/generate/{job_id}/confirm")
async def confirm_params(job_id: str, body: dict) -> EventSourceResponse:
    """确认参数后恢复生成流程"""
    ...

@router.get("/generate/{job_id}")
async def get_job_status(job_id: str) -> dict:
    """查询 Job 状态"""
    ...
```

### 前端：SSE 状态机

```
IDLE → PARSING → CONFIRMING → GENERATING → REFINING → COMPLETED
                                                        ↗
                              → VALIDATION_FAILED → (重试或终止)
```

### 测试重点

- Job 模型状态流转
- API: 创建 job → 查询状态 → 确认参数 → 完成
- SSE 事件流（mock pipeline）
- 前端构建通过

### 验证命令

```bash
pytest tests/test_generate_api.py -v
cd frontend && npm run build
```

---

## Task 7: 可打印性检查 (T4.7)

**标签:** [backend]
**Skill:** —

**Files:**
- Create: `backend/core/printability.py`
- Create: `backend/models/printability.py`
- Test: `tests/test_printability.py`

### 设计

```python
# backend/models/printability.py
class PrintProfile(BaseModel):
    """打印配置"""
    name: str                    # "fdm_standard", "sla_standard", "sls_standard"
    technology: str              # "FDM", "SLA", "SLS"
    min_wall_thickness: float    # mm
    max_overhang_angle: float    # degrees
    min_hole_diameter: float     # mm
    min_rib_thickness: float     # mm
    build_volume: tuple[float, float, float]  # (x, y, z) mm

class PrintIssue(BaseModel):
    """单个可打印性问题"""
    check: str                   # "wall_thickness", "overhang", "hole_diameter", etc.
    severity: str                # "error", "warning", "info"
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    suggestion: str = ""

class PrintabilityResult(BaseModel):
    """可打印性检查结果"""
    printable: bool
    profile: str
    issues: list[PrintIssue]
    material_volume_cm3: Optional[float] = None
    bounding_box: Optional[dict[str, float]] = None

PRESET_PROFILES: dict[str, PrintProfile] = {
    "fdm_standard": PrintProfile(
        name="fdm_standard", technology="FDM",
        min_wall_thickness=0.8, max_overhang_angle=45.0,
        min_hole_diameter=2.0, min_rib_thickness=0.8,
        build_volume=(220, 220, 250),
    ),
    "sla_standard": PrintProfile(...),
    "sls_standard": PrintProfile(...),
}
```

```python
# backend/core/printability.py
class PrintabilityChecker:
    """可打印性检查器

    测试中通过注入 mock geometry_analyzer 避免 CadQuery 依赖。
    """

    def __init__(self, geometry_analyzer=None):
        self._analyzer = geometry_analyzer  # 可注入 mock

    def check(
        self,
        geometry_info: dict,
        profile: str = "fdm_standard",
    ) -> PrintabilityResult:
        """检查几何信息是否满足打印要求

        geometry_info 包含:
        - bounding_box: {x, y, z}
        - min_wall_thickness: float (预计算)
        - max_overhang_angle: float (预计算)
        - min_hole_diameter: float (预计算)
        - min_rib_thickness: float (预计算)
        - volume_cm3: float
        """
        ...

    def _check_wall_thickness(self, value, threshold) -> Optional[PrintIssue]: ...
    def _check_overhang(self, value, threshold) -> Optional[PrintIssue]: ...
    def _check_hole_diameter(self, value, threshold) -> Optional[PrintIssue]: ...
    def _check_rib_thickness(self, value, threshold) -> Optional[PrintIssue]: ...
    def _check_build_volume(self, bbox, build_volume) -> Optional[PrintIssue]: ...
```

### 测试策略

**关键：输入预计算的 geometry_info dict，不依赖 CadQuery 几何分析。**

### 测试重点

- 3 个预设配置加载
- 壁厚检查：0.5mm (< FDM 0.8mm) → error
- 悬挑角检查：60° (> FDM 45°) → warning
- 最小孔径检查：1.0mm (< FDM 2.0mm) → error
- 构建体积检查：超出 → error
- 全部通过 → printable=True
- FDM vs SLA 不同阈值产生不同结果

### 验证命令

```bash
pytest tests/test_printability.py -v
```

---

## Task 8: 可打印性报告 UI (T4.8)

**标签:** [frontend]
**Skill:** `frontend-design`, `ant-design`
**依赖:** Task 7 (PrintabilityChecker)

**Files:**
- Create: `frontend/src/components/PrintReport/index.tsx`
- Create: `frontend/src/components/PrintReport/IssueList.tsx`
- Create: `frontend/src/components/PrintReport/ProfileSelector.tsx`
- Create: `frontend/src/types/printability.ts`

### 设计

- `ProfileSelector`: FDM/SLA/SLS 预设选择 + 自定义配置
- `IssueList`: 检查项列表（✅/⚠️/❌ 状态 + 描述 + 修复建议）
- 材料用量 + 预估打印时间显示
- 打印方向推荐（基于 bounding_box 最小支撑面）

### 验证命令

```bash
cd frontend && npm run build
```

---

## Task 9: 打印配置管理 (T4.9)

**标签:** [frontend] [backend]
**Skill:** `ant-design`
**依赖:** Task 7 (PrintProfile), Task 8 (PrintReport)

**Files:**
- Create: `backend/api/print_config.py`
- Modify: `backend/main.py` — 注册 print_config router
- Create: `frontend/src/pages/Settings/PrintConfigPanel.tsx`
- Test: `tests/test_print_config_api.py`

### API 设计

```python
# backend/api/print_config.py
@router.get("/print-profiles")
async def list_profiles() -> list[dict]: ...

@router.get("/print-profiles/{name}")
async def get_profile(name: str) -> dict: ...

@router.post("/print-profiles")
async def create_profile(body: dict) -> dict: ...

@router.put("/print-profiles/{name}")
async def update_profile(name: str, body: dict) -> dict: ...

@router.delete("/print-profiles/{name}")
async def delete_profile(name: str) -> dict: ...
```

### 持久化

自定义配置存储为 YAML 文件在 `backend/knowledge/print_profiles/` 目录下，预设配置内存加载。

### 测试重点

- CRUD 端点（list/get/create/update/delete）
- 预设配置不可删除
- 自定义配置持久化 round-trip

### 验证命令

```bash
pytest tests/test_print_config_api.py -v
cd frontend && npm run build
```

---

## 执行顺序与并行策略

| Wave | 任务 | 并行 | 说明 |
|------|------|------|------|
| 1 | T4.1 + T4.3 + T4.7 | 3 并行 | 三个独立数据模型/知识库 |
| 2 | T4.2 + T4.4 + T4.8 | 3 并行 | 各依赖 Wave 1 的一个任务 |
| 3 | T4.5 + T4.9 | 2 并行 | T4.5 依赖 T4.3, T4.9 依赖 T4.7/T4.8 |
| 4 | T4.6 | 串行 | 大集成任务，依赖 T4.2 + T4.5 |

**预计新增测试:** ~120-150 个
**预计新增/修改文件:** ~25 个
