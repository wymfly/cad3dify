# cad3dify v2 增强管道实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 cad3dify 中实现两阶段管道（VL 读图 → Coder 写码），大幅提升从工程图纸到 3D CAD 模型的生成质量。

**Architecture:** 新增 v2 管道，在图片输入和代码生成之间插入"图纸分析"阶段，将视觉理解和代码生成解耦到不同模型。引入零件类型知识库，为 Coder 模型注入建模策略和 few-shot 示例。保留 v1 管道不变。

**Tech Stack:** Python 3.12, LangChain (LLMChain/SequentialChain), Qwen VL/Coder (via DashScope OpenAI-compatible), CadQuery, Pydantic v2, Streamlit

**项目根目录：** `/Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify/`

---

### Task 1: 扩展 chat_models.py 支持多模型角色

**Files:**
- Modify: `cad3dify/chat_models.py`

**目标：** 新增 `qwen-vl` 和 `qwen-coder` 模型配置，让同一 pipeline 可以对不同阶段使用不同模型。

**Step 1: 扩展 MODEL_TYPE 和 PROVIDER_TYPE**

在 `chat_models.py` 中：

```python
MODEL_TYPE = Literal["gpt", "claude", "gemini", "llama", "qwen", "qwen-vl", "qwen-coder"]
```

**Step 2: 在 from_model_name 中新增两个模型配置**

在 `model_type_to_parameters` 字典中新增：

```python
"qwen-vl": cls(
    provider="openai",
    model_name="qwen-vl-max",
    temperature=0.1,  # VL 分析需要低温度
    max_tokens=8000,
),
"qwen-coder": cls(
    provider="openai",
    model_name="qwen-coder-plus",
    temperature=0.3,  # 代码生成适度创造性
    max_tokens=32000,
),
```

**Step 3: 验证**

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
.venv/bin/python -c "
from cad3dify.chat_models import ChatModelParameters
vl = ChatModelParameters.from_model_name('qwen-vl')
coder = ChatModelParameters.from_model_name('qwen-coder')
print(f'VL: {vl.model_name}, temp={vl.temperature}')
print(f'Coder: {coder.model_name}, temp={coder.temperature}')
"
```

Expected: 输出正确的模型名和温度。

**Step 4: Commit**

```bash
git add cad3dify/chat_models.py
git commit -m "feat: add qwen-vl and qwen-coder model configs for two-phase pipeline"
```

---

### Task 2: 创建零件类型定义模块

**Files:**
- Create: `cad3dify/knowledge/__init__.py`
- Create: `cad3dify/knowledge/part_types.py`

**目标：** 定义零件分类体系和 DrawingSpec 数据模型。

**Step 1: 创建 knowledge 包**

`cad3dify/knowledge/__init__.py`:

```python
from .part_types import PartType, DrawingSpec
```

**Step 2: 定义零件类型枚举和 DrawingSpec 模型**

`cad3dify/knowledge/part_types.py`:

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class PartType(str, Enum):
    """零件类型分类"""
    ROTATIONAL = "rotational"          # 旋转体（法兰、轴、套筒、轴承座）
    ROTATIONAL_STEPPED = "rotational_stepped"  # 阶梯旋转体
    PLATE = "plate"                    # 板件
    BRACKET = "bracket"                # 支架/角件
    HOUSING = "housing"                # 箱体/壳体
    GEAR = "gear"                      # 齿轮
    GENERAL = "general"                # 通用（无法分类时兜底）


class DimensionLayer(BaseModel):
    """阶梯层尺寸"""
    diameter: float
    height: float
    label: str = ""


class BoreSpec(BaseModel):
    """通孔/盲孔规格"""
    diameter: float
    through: bool = True
    depth: Optional[float] = None


class HolePatternSpec(BaseModel):
    """孔阵列规格"""
    pattern: str = "circular"  # circular, rectangular, linear
    count: int
    diameter: float
    pcd: Optional[float] = None  # pitch circle diameter, for circular pattern
    spacing_x: Optional[float] = None  # for rectangular pattern
    spacing_y: Optional[float] = None
    on_layer: str = ""  # which layer the holes are on


class FilletSpec(BaseModel):
    """圆角规格"""
    radius: float
    locations: list[str] = []  # e.g. ["step_transitions", "outer_edges"]


class ChamferSpec(BaseModel):
    """倒角规格"""
    size: float
    locations: list[str] = []


class BaseBodySpec(BaseModel):
    """基体构建规格"""
    method: str  # revolve, extrude, loft, sweep, shell
    profile: list[DimensionLayer] = []
    bore: Optional[BoreSpec] = None
    width: Optional[float] = None
    length: Optional[float] = None
    height: Optional[float] = None
    wall_thickness: Optional[float] = None


class DrawingSpec(BaseModel):
    """图纸分析结构化结果 — VL 模型输出格式"""
    part_type: PartType
    description: str
    views: list[str] = []  # front, top, side, section, isometric
    overall_dimensions: dict[str, float] = {}
    base_body: BaseBodySpec
    features: list[dict] = []  # HolePatternSpec, FilletSpec, ChamferSpec 等混合
    notes: list[str] = []  # 额外注释（公差、表面处理等）

    def to_prompt_text(self) -> str:
        """将 DrawingSpec 转为 Coder 模型可读的文本描述"""
        lines = [
            f"## 零件规格",
            f"类型: {self.part_type.value}",
            f"描述: {self.description}",
            f"视图: {', '.join(self.views)}",
            f"总体尺寸: {self.overall_dimensions}",
            f"",
            f"## 基体",
            f"构建方法: {self.base_body.method}",
        ]
        if self.base_body.profile:
            lines.append("阶梯轮廓:")
            for layer in self.base_body.profile:
                lines.append(f"  - 直径 {layer.diameter}, 高度 {layer.height} ({layer.label})")
        if self.base_body.bore:
            lines.append(f"中心孔: 直径 {self.base_body.bore.diameter}, {'通孔' if self.base_body.bore.through else f'盲孔 深度{self.base_body.bore.depth}'}")
        if self.base_body.width:
            lines.append(f"宽度: {self.base_body.width}")
        if self.base_body.length:
            lines.append(f"长度: {self.base_body.length}")
        if self.base_body.height:
            lines.append(f"高度: {self.base_body.height}")
        lines.append("")
        if self.features:
            lines.append("## 特征")
            for i, feat in enumerate(self.features, 1):
                lines.append(f"  {i}. {feat}")
        if self.notes:
            lines.append("")
            lines.append("## 注释")
            for note in self.notes:
                lines.append(f"  - {note}")
        return "\n".join(lines)
```

**Step 3: 验证导入**

```bash
.venv/bin/python -c "
from cad3dify.knowledge import PartType, DrawingSpec
from cad3dify.knowledge.part_types import BaseBodySpec, DimensionLayer, BoreSpec
spec = DrawingSpec(
    part_type=PartType.ROTATIONAL_STEPPED,
    description='test',
    base_body=BaseBodySpec(method='revolve', profile=[DimensionLayer(diameter=100, height=10, label='base')], bore=BoreSpec(diameter=10)),
)
print(spec.to_prompt_text())
"
```

**Step 4: Commit**

```bash
git add cad3dify/knowledge/
git commit -m "feat: add part type definitions and DrawingSpec data model"
```

---

### Task 3: 创建建模策略知识库

**Files:**
- Create: `cad3dify/knowledge/modeling_strategies.py`
- Create: `cad3dify/knowledge/examples/__init__.py`
- Create: `cad3dify/knowledge/examples/rotational.py`
- Create: `cad3dify/knowledge/examples/plate.py`
- Create: `cad3dify/knowledge/examples/bracket.py`
- Create: `cad3dify/knowledge/examples/housing.py`

**目标：** 为每种零件类型提供 CadQuery 建模策略指南和高质量 few-shot 代码示例。

**Step 1: 创建建模策略映射**

`cad3dify/knowledge/modeling_strategies.py`:

```python
from .part_types import PartType

# 每种零件类型的 CadQuery 建模策略指南
STRATEGIES: dict[PartType, str] = {
    PartType.ROTATIONAL: """\
## 旋转体零件建模策略

### 基体构建：使用 revolve（旋转）
- 在 XZ 平面绘制半截面轮廓（polyline），然后 revolve(360°)
- 轮廓点按 (radius, height) 从内孔底部开始，逆时针排列
- 结束时 close() 自动闭合轮廓

### CadQuery 代码模式
```python
profile_pts = [
    (r_bore, 0),      # 内孔底部
    (r_outer, 0),     # 外缘底部
    (r_outer, height), # 外缘顶部
    (r_bore, height),  # 内孔顶部
]
result = cq.Workplane("XZ").polyline(profile_pts).close().revolve(360, (0,0,0), (0,1,0))
```

### 特征添加顺序（严格遵守）
1. revolve 基体
2. fillet 圆角（在 cut 之前！否则边被破坏）
3. cut 孔特征

### 圆角选择器
- 使用 NearestToPointSelector 精确选择边：
```python
result.edges(cq.selectors.NearestToPointSelector((x, y, z))).fillet(r)
```
- 不要用 >Z / <Z 等方向选择器，对复杂几何不可靠

### 螺栓孔阵列
```python
import math
for i in range(n_bolts):
    angle = math.radians(i * 360 / n_bolts)
    x = (pcd / 2) * math.cos(angle)
    y = (pcd / 2) * math.sin(angle)
    hole = cq.Workplane("XY").center(x, y).circle(d_bolt / 2).extrude(thickness + 1)
    result = result.cut(hole)
```

### 常见陷阱
- 绝对不要用多个圆柱 union 再 fillet，会导致圆角操作失败
- revolve 一次成型的单一实体，fillet 成功率极高
- fillet 用 try/except 包裹，某些边可能因几何原因无法倒角
""",

    PartType.ROTATIONAL_STEPPED: """\
## 阶梯旋转体建模策略

### 基体构建：revolve profile 一次成型
- 在 XZ 平面绘制包含所有阶梯的半截面轮廓
- 每个阶梯对应轮廓中的一段水平+垂直线
- revolve 360° 一次生成完整阶梯结构

### CadQuery 代码模式（关键！）
```python
# 半截面轮廓点 (radius, height)，从内孔底部开始逆时针
profile_pts = [
    (r_bore, 0),                          # 内孔底部
    (r_base, 0),                          # 最大直径底面
    (r_base, h_base),                     # 最大直径顶面
    (r_mid, h_base),                      # 中间阶梯底面
    (r_mid, h_base + h_mid),              # 中间阶梯顶面
    (r_top, h_base + h_mid),              # 顶部阶梯底面
    (r_top, h_base + h_mid + h_top),      # 顶部阶梯顶面
    (r_bore, h_base + h_mid + h_top),     # 内孔顶部
]
result = cq.Workplane("XZ").polyline(profile_pts).close().revolve(360, (0,0,0), (0,1,0))
```

### 阶梯过渡圆角
- 每个阶梯交界处有 2 条环形边需要圆角
- 用 NearestToPointSelector 逐一选择：
```python
# 外径→小径的水平拐角
result = result.edges(cq.selectors.NearestToPointSelector((r_large, 0, z_transition))).fillet(r)
# 小径→内侧的垂直拐角
result = result.edges(cq.selectors.NearestToPointSelector((r_small, 0, z_transition))).fillet(r)
```

### 关键原则
1. 所有阶梯在一个 revolve profile 中完成——不要分段建模
2. fillet 在 cut（螺栓孔）之前
3. 螺栓孔穿过法兰部分，extrude 高度 > 法兰厚度
4. 每个 fillet 用 try/except 包裹
""",

    PartType.PLATE: """\
## 板件建模策略

### 基体构建：sketch + extrude
- 在 XY 平面绘制轮廓，extrude 到板厚
- 复杂轮廓用 polyline + close + extrude
- 简单矩形用 box

### CadQuery 代码模式
```python
# 矩形板
result = cq.Workplane("XY").box(length, width, thickness)

# 异形板
pts = [(0,0), (100,0), (100,50), (80,50), (80,20), (0,20)]
result = cq.Workplane("XY").polyline(pts).close().extrude(thickness)
```

### 特征添加
1. 孔位：faces(">Z").workplane().pushPoints(pts).hole(d)
2. 沉头孔：cboreHole(hole_d, cbore_d, cbore_depth)
3. 槽：faces(">Z").workplane().slot2D(length, width).cutBlind(-depth)
4. 圆角：edges("|Z").fillet(r) 选择垂直边
""",

    PartType.BRACKET: """\
## 支架/角件建模策略

### 基体构建：分部件 union
- 分解为底板 + 立板（+ 可选加强筋）
- 各部分独立 extrude 后 union
- 或使用 L 形轮廓一次 extrude

### CadQuery 代码模式
```python
# L 形支架
base = cq.Workplane("XY").box(base_l, base_w, base_t)
wall = (cq.Workplane("XY")
    .workplane(offset=base_t)
    .center(-base_l/2 + wall_t/2, 0)
    .box(wall_t, base_w, wall_h))
result = base.union(wall)

# 加强筋（三角形）
rib_pts = [(0,0), (rib_l, 0), (0, rib_h)]
rib = (cq.Workplane("XZ")
    .center(-base_l/2, base_t)
    .polyline(rib_pts).close()
    .extrude(rib_t))
result = result.union(rib)
```

### 连接处圆角
- union 后在连接边做 fillet
- 选择内角边：edges 用 NearestToPointSelector
""",

    PartType.HOUSING: """\
## 箱体/壳体建模策略

### 基体构建：extrude + shell 抽壳
- 先建实体外形
- 用 shell 命令抽壳（指定保留面）

### CadQuery 代码模式
```python
# 矩形箱体
result = (cq.Workplane("XY")
    .box(length, width, height)
    .faces(">Z")  # 顶面开口
    .shell(-wall_thickness))  # 负值=向内抽壳

# 带安装凸台
result = (result
    .faces("<Z").workplane(invert=True)
    .rect(bolt_spacing_x, bolt_spacing_y, forConstruction=True)
    .vertices()
    .circle(boss_d/2).extrude(boss_h))
```
""",

    PartType.GEAR: """\
## 齿轮建模策略

### 基体构建：参数曲线 + twistExtrude
- 用参数方程生成齿形轮廓
- twistExtrude 创建螺旋齿

### CadQuery 代码模式
```python
from math import sin, cos, pi, floor

def gear_profile(t, r1, r2):
    # 外摆线和内摆线组合
    ...

result = (cq.Workplane("XY")
    .parametricCurve(lambda t: gear_profile(t * 2 * pi, module, teeth))
    .twistExtrude(face_width, helix_angle)
    .faces(">Z").workplane().circle(bore_d/2).cutThruAll())
```
""",

    PartType.GENERAL: """\
## 通用建模策略

### 分析步骤
1. 识别基体形状（最大的连续实体）
2. 确定基体构建方式（extrude/revolve/loft）
3. 按从大到小的顺序添加特征
4. 圆角/倒角最后做

### CadQuery 基本原则
- 选择合适的初始 Workplane（XY/XZ/YZ）
- 所有尺寸参数化（用变量不用硬编码数字）
- 布尔操作后检查 val().isValid()
- fillet/chamfer 在所有 cut 操作之前
- 导出用 cq.exporters.export(result, filepath)
""",
}


def get_strategy(part_type: PartType) -> str:
    """获取零件类型对应的建模策略"""
    return STRATEGIES.get(part_type, STRATEGIES[PartType.GENERAL])
```

**Step 2: 创建旋转体 few-shot 示例**

`cad3dify/knowledge/examples/__init__.py`:

```python
from .rotational import ROTATIONAL_EXAMPLES
from .plate import PLATE_EXAMPLES
from .bracket import BRACKET_EXAMPLES
from .housing import HOUSING_EXAMPLES

from ..part_types import PartType

EXAMPLES_BY_TYPE: dict[PartType, list[tuple[str, str]]] = {
    PartType.ROTATIONAL: ROTATIONAL_EXAMPLES,
    PartType.ROTATIONAL_STEPPED: ROTATIONAL_EXAMPLES,  # 共享旋转体示例
    PartType.PLATE: PLATE_EXAMPLES,
    PartType.BRACKET: BRACKET_EXAMPLES,
    PartType.HOUSING: HOUSING_EXAMPLES,
}


def get_examples(part_type: PartType) -> list[tuple[str, str]]:
    """获取零件类型对应的 few-shot 示例列表，每项为 (说明, 代码)"""
    return EXAMPLES_BY_TYPE.get(part_type, [])
```

**Step 3: 旋转体示例**

`cad3dify/knowledge/examples/rotational.py`:

```python
ROTATIONAL_EXAMPLES: list[tuple[str, str]] = [
    (
        "三层阶梯法兰盘：φ100/φ40/φ24，中心通孔φ10，6×φ10螺栓孔PCD70，R3圆角",
        '''\
import cadquery as cq
import math

# 尺寸参数
d_base, d_mid, d_top, d_bore = 100, 40, 24, 10
h_base, h_mid, h_top = 10, 10, 10
n_bolts, d_bolt, pcd = 6, 10, 70
r_fillet = 3

r_base, r_mid, r_top, r_bore = d_base/2, d_mid/2, d_top/2, d_bore/2

# 1. revolve profile 一次成型
profile_pts = [
    (r_bore, 0),
    (r_base, 0),
    (r_base, h_base),
    (r_mid, h_base),
    (r_mid, h_base + h_mid),
    (r_top, h_base + h_mid),
    (r_top, h_base + h_mid + h_top),
    (r_bore, h_base + h_mid + h_top),
]
result = cq.Workplane("XZ").polyline(profile_pts).close().revolve(360, (0,0,0), (0,1,0))

# 2. 阶梯过渡圆角（在 cut 之前）
for pt in [(r_base, 0, h_base), (r_mid, 0, h_base), (r_mid, 0, h_base+h_mid)]:
    try:
        result = result.edges(cq.selectors.NearestToPointSelector(pt)).fillet(r_fillet)
    except Exception:
        pass

# 3. 螺栓孔
for i in range(n_bolts):
    angle = math.radians(i * 360 / n_bolts)
    x, y = (pcd/2) * math.cos(angle), (pcd/2) * math.sin(angle)
    hole = cq.Workplane("XY").center(x, y).circle(d_bolt/2).extrude(h_base + 1)
    result = result.cut(hole)

cq.exporters.export(result, "${output_filename}")
''',
    ),
    (
        "简单轴：总长120，两端φ30轴颈各长25，中间φ50轴身长70，键槽",
        '''\
import cadquery as cq

# 尺寸参数
d_journal, d_body = 30, 50
l_journal, l_body = 25, 70
total_length = l_journal * 2 + l_body
key_width, key_depth, key_length = 8, 4, 30

r_journal, r_body = d_journal/2, d_body/2

# 1. revolve profile
profile_pts = [
    (0, 0),
    (r_journal, 0),
    (r_journal, l_journal),
    (r_body, l_journal),
    (r_body, l_journal + l_body),
    (r_journal, l_journal + l_body),
    (r_journal, total_length),
    (0, total_length),
]
result = cq.Workplane("XZ").polyline(profile_pts).close().revolve(360, (0,0,0), (0,1,0))

# 2. 过渡圆角
for z in [l_journal, l_journal + l_body]:
    try:
        result = result.edges(cq.selectors.NearestToPointSelector((r_body, 0, z))).fillet(2)
    except Exception:
        pass

# 3. 键槽
key_slot = (cq.Workplane("XZ")
    .center(r_body - key_depth/2, total_length/2)
    .rect(key_depth, key_length)
    .extrude(key_width/2, both=True))
result = result.cut(key_slot)

cq.exporters.export(result, "${output_filename}")
''',
    ),
]
```

**Step 4: 板件示例**

`cad3dify/knowledge/examples/plate.py`:

```python
PLATE_EXAMPLES: list[tuple[str, str]] = [
    (
        "矩形安装板：200x150x10，四角4×φ12安装孔，中心φ60通孔",
        '''\
import cadquery as cq

length, width, thickness = 200, 150, 10
hole_d, center_hole_d = 12, 60
margin = 20

result = (cq.Workplane("XY")
    .box(length, width, thickness)
    .faces(">Z").workplane()
    .hole(center_hole_d)
    .faces(">Z").workplane()
    .rect(length - 2*margin, width - 2*margin, forConstruction=True)
    .vertices()
    .hole(hole_d))

cq.exporters.export(result, "${output_filename}")
''',
    ),
]
```

**Step 5: 支架和箱体示例**

`cad3dify/knowledge/examples/bracket.py`:

```python
BRACKET_EXAMPLES: list[tuple[str, str]] = [
    (
        "L 形支架：底板100x80x10，立板80x60x10，底板4孔，立板2孔",
        '''\
import cadquery as cq

# 底板
base_l, base_w, base_t = 100, 80, 10
# 立板
wall_h, wall_t = 60, 10

# L 形截面 extrude
pts = [
    (0, 0), (base_l, 0), (base_l, base_t),
    (wall_t, base_t), (wall_t, base_t + wall_h), (0, base_t + wall_h),
]
result = cq.Workplane("XZ").polyline(pts).close().extrude(base_w)

# 底板安装孔
result = (result.faces("<Z").workplane()
    .rect(base_l - 20, base_w - 20, forConstruction=True)
    .vertices().hole(10))

# 立板安装孔
result = (result.faces("<X").workplane()
    .center(0, wall_h/2 + base_t/2)
    .rect(base_w - 30, wall_h - 20, forConstruction=True)
    .vertices().hole(8))

# 内角圆角
try:
    result = result.edges(cq.selectors.NearestToPointSelector((wall_t/2, base_w/2, base_t))).fillet(5)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
''',
    ),
]
```

`cad3dify/knowledge/examples/housing.py`:

```python
HOUSING_EXAMPLES: list[tuple[str, str]] = [
    (
        "矩形箱体：120x80x60，壁厚3，顶面开口，四角安装凸台",
        '''\
import cadquery as cq

length, width, height = 120, 80, 60
wall_t = 3
boss_d, boss_h = 12, 5

# 箱体 + 抽壳
result = (cq.Workplane("XY")
    .box(length, width, height)
    .faces(">Z").shell(-wall_t))

# 底部安装凸台
result = (result.faces("<Z").workplane(invert=True)
    .rect(length - 15, width - 15, forConstruction=True)
    .vertices()
    .circle(boss_d/2).extrude(boss_h)
    .faces("<Z").workplane(invert=True)
    .rect(length - 15, width - 15, forConstruction=True)
    .vertices()
    .hole(5))

cq.exporters.export(result, "${output_filename}")
''',
    ),
]
```

**Step 6: 验证知识库加载**

```bash
.venv/bin/python -c "
from cad3dify.knowledge.part_types import PartType
from cad3dify.knowledge.modeling_strategies import get_strategy
from cad3dify.knowledge.examples import get_examples

for pt in PartType:
    strategy = get_strategy(pt)
    examples = get_examples(pt)
    print(f'{pt.value}: strategy={len(strategy)} chars, examples={len(examples)}')
"
```

**Step 7: Commit**

```bash
git add cad3dify/knowledge/
git commit -m "feat: add modeling strategies knowledge base with per-type examples"
```

---

### Task 4: 实现 Drawing Analyzer（VL 图纸分析阶段）

**Files:**
- Create: `cad3dify/v2/__init__.py`
- Create: `cad3dify/v2/drawing_analyzer.py`

**目标：** 用 qwen-vl-max 分析工程图纸，输出 DrawingSpec JSON。

**Step 1: 创建 v2 包**

`cad3dify/v2/__init__.py`:

```python
from .drawing_analyzer import DrawingAnalyzerChain
from .code_generator import CodeGeneratorChain
from .smart_refiner import SmartRefinerChain
```

（先创建空文件，后续 task 补充 code_generator 和 smart_refiner）

**Step 2: 实现 DrawingAnalyzerChain**

`cad3dify/v2/drawing_analyzer.py`:

```python
import json
import re
from typing import Any, Union

from langchain.chains import LLMChain, SequentialChain, TransformChain
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    PromptTemplate,
)
from langchain_core.prompts.image import ImagePromptTemplate
from loguru import logger

from ..chat_models import ChatModelParameters
from ..image import ImageData
from ..knowledge.part_types import DrawingSpec, PartType

_DRAWING_ANALYSIS_PROMPT = """\
你是一位经验丰富的机械工程师，擅长阅读工程图纸。请仔细分析附带的 2D 工程图纸，提取所有几何信息。

## 任务
1. 识别零件类型（从以下选项中选择）：
   - rotational: 旋转体（圆柱、圆锥）
   - rotational_stepped: 阶梯旋转体（法兰盘、阶梯轴）
   - plate: 板件
   - bracket: 支架/角件
   - housing: 箱体/壳体
   - gear: 齿轮
   - general: 其他

2. 识别图纸中包含的视图（front, top, side, section, isometric）

3. 提取所有标注尺寸，包括：
   - 直径（φ）、半径（R）、长度、宽度、高度
   - 孔的数量、直径、分布（PCD）
   - 圆角（R）、倒角（C）
   - 公差（如有）

4. 确定基体构建方式：
   - revolve: 旋转体零件（首选！阶梯轴、法兰盘等）
   - extrude: 板件、型材
   - loft: 变截面体
   - shell: 箱体（先实体后抽壳）

## 输出格式
严格输出以下 JSON 格式，不要输出其他内容：

```json
{
  "part_type": "rotational_stepped",
  "description": "零件的文字描述",
  "views": ["front_section", "top"],
  "overall_dimensions": {"max_diameter": 100, "total_height": 30},
  "base_body": {
    "method": "revolve",
    "profile": [
      {"diameter": 100, "height": 10, "label": "base_flange"},
      {"diameter": 40, "height": 10, "label": "middle_boss"}
    ],
    "bore": {"diameter": 10, "through": true}
  },
  "features": [
    {"type": "hole_pattern", "pattern": "circular", "count": 6, "diameter": 10, "pcd": 70, "on_layer": "base_flange"},
    {"type": "fillet", "radius": 3, "locations": ["step_transitions"]},
    {"type": "chamfer", "size": 1, "locations": ["top_edge"]}
  ],
  "notes": ["表面粗糙度 Ra 3.2"]
}
```

## 重要提示
- 所有数值必须是数字，不要加单位
- diameter 是直径，不是半径
- 仔细区分剖视图中的虚线（隐藏线）和实线
- 如果某个尺寸无法确定，根据比例关系合理推测并在 notes 中说明
"""


def _parse_drawing_spec(input: dict) -> dict:
    """从 LLM 输出中提取 JSON 并解析为 DrawingSpec"""
    text = input["text"]
    # 尝试从 markdown 代码块中提取 JSON
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        json_str = match.group(1).strip()
    else:
        # 尝试直接解析整个文本
        json_str = text.strip()

    try:
        data = json.loads(json_str)
        # 验证 part_type 合法
        part_type = data.get("part_type", "general")
        if part_type not in [pt.value for pt in PartType]:
            data["part_type"] = "general"
        spec = DrawingSpec(**data)
        logger.info(f"Drawing analysis result: part_type={spec.part_type}, dims={spec.overall_dimensions}")
        return {"result": spec}
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Failed to parse DrawingSpec: {e}\nRaw text: {text}")
        return {"result": None}


class DrawingAnalyzerChain(SequentialChain):
    """阶段1：VL 模型分析工程图纸，输出结构化 DrawingSpec"""

    def __init__(self) -> None:
        prompt = ChatPromptTemplate(
            input_variables=["image_type", "image_data"],
            messages=[
                HumanMessagePromptTemplate(
                    prompt=[
                        PromptTemplate(
                            input_variables=[],
                            template=_DRAWING_ANALYSIS_PROMPT,
                        ),
                        ImagePromptTemplate(
                            input_variables=["image_type", "image_data"],
                            template={
                                "url": "data:image/{image_type};base64,{image_data}",
                            },
                        ),
                    ]
                )
            ],
        )
        llm = ChatModelParameters.from_model_name("qwen-vl").create_chat_model()

        super().__init__(
            chains=[
                LLMChain(prompt=prompt, llm=llm),
                TransformChain(
                    input_variables=["text"],
                    output_variables=["result"],
                    transform=_parse_drawing_spec,
                    atransform=None,
                ),
            ],
            input_variables=["image_type", "image_data"],
            output_variables=["result"],
            verbose=True,
        )

    def prep_inputs(self, inputs: Union[dict[str, Any], Any]) -> dict[str, str]:
        if isinstance(inputs, ImageData):
            inputs = {"input": inputs}
        elif "input" not in inputs:
            raise ValueError("inputs must be ImageData or dict with 'input' key")
        image = inputs["input"]
        assert isinstance(image, ImageData)
        inputs["image_type"] = image.type
        inputs["image_data"] = image.data
        return inputs
```

**Step 3: 验证（dry run，不实际调用 API）**

```bash
.venv/bin/python -c "
from cad3dify.v2.drawing_analyzer import _parse_drawing_spec
import json
# 模拟 LLM 输出
mock = {'text': '''json
{\"part_type\": \"rotational_stepped\", \"description\": \"test\",
 \"views\": [\"front\"], \"overall_dimensions\": {\"max_diameter\": 100},
 \"base_body\": {\"method\": \"revolve\", \"profile\": [{\"diameter\": 100, \"height\": 10, \"label\": \"base\"}]},
 \"features\": [], \"notes\": []}
'''.replace('json', '\`\`\`json') + '\n\`\`\`'}
# Use actual markdown fences
mock = {'text': json.dumps({
    'part_type': 'rotational_stepped', 'description': 'test',
    'views': ['front'], 'overall_dimensions': {'max_diameter': 100},
    'base_body': {'method': 'revolve', 'profile': [{'diameter': 100, 'height': 10, 'label': 'base'}]},
    'features': [], 'notes': []
})}
result = _parse_drawing_spec(mock)
print(f'Parsed: {result[\"result\"].part_type}')
print(result['result'].to_prompt_text())
"
```

**Step 4: Commit**

```bash
git add cad3dify/v2/
git commit -m "feat: implement DrawingAnalyzerChain — VL model extracts DrawingSpec from drawings"
```

---

### Task 5: 实现 Modeling Strategist（建模策略选择）

**Files:**
- Create: `cad3dify/v2/modeling_strategist.py`

**目标：** 规则引擎，根据 DrawingSpec 的零件类型选择建模策略和 few-shot 示例。无需 LLM 调用。

**Step 1: 实现 ModelingStrategist**

`cad3dify/v2/modeling_strategist.py`:

```python
from dataclasses import dataclass

from ..knowledge.part_types import DrawingSpec, PartType
from ..knowledge.modeling_strategies import get_strategy
from ..knowledge.examples import get_examples


@dataclass
class ModelingContext:
    """建模上下文 — 传递给 Code Generator 的全部信息"""
    drawing_spec: DrawingSpec
    strategy: str
    examples: list[tuple[str, str]]

    def to_prompt_text(self) -> str:
        """组装为 Coder 模型的完整输入 prompt"""
        parts = [
            self.drawing_spec.to_prompt_text(),
            "",
            self.strategy,
            "",
        ]
        if self.examples:
            parts.append("## 参考代码示例")
            parts.append("")
            for desc, code in self.examples:
                parts.append(f"### {desc}")
                parts.append(f"```python\n{code}\n```")
                parts.append("")
        return "\n".join(parts)


class ModelingStrategist:
    """阶段 1.5：根据零件类型选择建模策略（纯规则引擎，无 LLM）"""

    def select(self, spec: DrawingSpec) -> ModelingContext:
        strategy = get_strategy(spec.part_type)
        examples = get_examples(spec.part_type)
        return ModelingContext(
            drawing_spec=spec,
            strategy=strategy,
            examples=examples,
        )
```

**Step 2: 验证**

```bash
.venv/bin/python -c "
from cad3dify.knowledge.part_types import DrawingSpec, PartType, BaseBodySpec, DimensionLayer, BoreSpec
from cad3dify.v2.modeling_strategist import ModelingStrategist

spec = DrawingSpec(
    part_type=PartType.ROTATIONAL_STEPPED,
    description='三层阶梯法兰盘',
    views=['front_section', 'top'],
    overall_dimensions={'max_diameter': 100, 'total_height': 30},
    base_body=BaseBodySpec(
        method='revolve',
        profile=[
            DimensionLayer(diameter=100, height=10, label='base'),
            DimensionLayer(diameter=40, height=10, label='mid'),
            DimensionLayer(diameter=24, height=10, label='top'),
        ],
        bore=BoreSpec(diameter=10),
    ),
    features=[
        {'type': 'hole_pattern', 'count': 6, 'diameter': 10, 'pcd': 70},
        {'type': 'fillet', 'radius': 3},
    ],
)

ctx = ModelingStrategist().select(spec)
text = ctx.to_prompt_text()
print(text[:500])
print(f'...total {len(text)} chars')
"
```

**Step 3: Commit**

```bash
git add cad3dify/v2/modeling_strategist.py
git commit -m "feat: implement ModelingStrategist — rule-based strategy and example selection"
```

---

### Task 6: 实现 Code Generator（Coder 代码生成阶段）

**Files:**
- Create: `cad3dify/v2/code_generator.py`

**目标：** 用 qwen-coder-plus 根据 ModelingContext 生成 CadQuery 代码。

**Step 1: 实现 CodeGeneratorChain**

`cad3dify/v2/code_generator.py`:

```python
import re
from typing import Any, Union

from langchain.chains import LLMChain, SequentialChain, TransformChain
from langchain.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, PromptTemplate

from ..chat_models import ChatModelParameters
from .modeling_strategist import ModelingContext


_CODE_GEN_PROMPT = """\
你是一位专业的 CAD 程序员，精通 Python cadquery 库。请根据下面的零件规格和建模策略，编写生成 3D CAD 模型的 Python 代码。

{modeling_context}

## 代码要求
1. 使用 cadquery 库（已安装，直接 import cadquery as cq）
2. 所有尺寸必须参数化（用变量，不要硬编码数字）
3. 严格遵循上面的建模策略（特别是基体构建方式和特征添加顺序）
4. 使用 `cq.exporters.export(result, "${{output_filename}}")` 导出 STEP 文件
5. 代码用 markdown 代码块包裹

## 关键原则
- 旋转体零件必须用 revolve profile 一次成型，不要用多个圆柱 union
- fillet 在 cut 之前
- 每个 fillet 操作用 try/except 包裹
- 螺栓孔用 for 循环 + math.cos/sin 计算位置

## 开始
请输出完整的 Python 代码：
"""


def _parse_code(input: dict) -> dict:
    """从 LLM 输出中提取 Python 代码"""
    match = re.search(r"```(?:python)?\n(.*?)\n```", input["text"], re.DOTALL)
    if match:
        return {"result": match.group(1).strip()}
    return {"result": None}


class CodeGeneratorChain(SequentialChain):
    """阶段2：Coder 模型根据 ModelingContext 生成 CadQuery 代码"""

    def __init__(self) -> None:
        prompt = ChatPromptTemplate(
            input_variables=["modeling_context"],
            messages=[
                HumanMessagePromptTemplate(
                    prompt=[
                        PromptTemplate(
                            input_variables=["modeling_context"],
                            template=_CODE_GEN_PROMPT,
                        ),
                    ]
                )
            ],
        )
        llm = ChatModelParameters.from_model_name("qwen-coder").create_chat_model()

        super().__init__(
            chains=[
                LLMChain(prompt=prompt, llm=llm),
                TransformChain(
                    input_variables=["text"],
                    output_variables=["result"],
                    transform=_parse_code,
                    atransform=None,
                ),
            ],
            input_variables=["modeling_context"],
            output_variables=["result"],
            verbose=True,
        )

    def prep_inputs(self, inputs: Union[dict[str, Any], Any]) -> dict[str, str]:
        if isinstance(inputs, ModelingContext):
            inputs = {"modeling_context": inputs.to_prompt_text()}
        elif "modeling_context" in inputs and isinstance(inputs["modeling_context"], ModelingContext):
            inputs["modeling_context"] = inputs["modeling_context"].to_prompt_text()
        return inputs
```

**Step 2: Commit**

```bash
git add cad3dify/v2/code_generator.py
git commit -m "feat: implement CodeGeneratorChain — coder model generates CadQuery from ModelingContext"
```

---

### Task 7: 实现 Smart Refiner（增强改进阶段）

**Files:**
- Create: `cad3dify/v2/smart_refiner.py`

**目标：** 用 VL 模型对比原图和渲染图，结合 DrawingSpec 输出精确修改指令，然后用 Coder 模型修改代码。

**Step 1: 实现 SmartRefinerChain**

`cad3dify/v2/smart_refiner.py`:

```python
import re
from typing import Any, Union

from langchain.chains import LLMChain, SequentialChain, TransformChain
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    PromptTemplate,
)
from langchain_core.prompts.image import ImagePromptTemplate
from loguru import logger

from ..chat_models import ChatModelParameters
from ..image import ImageData
from ..knowledge.part_types import DrawingSpec

# ---- 阶段 4a: VL 模型分析差异 ----

_COMPARE_PROMPT = """\
你是一位经验丰富的机械工程师。请对比以下两张图片：
1. 第一张是原始的 2D 工程图纸
2. 第二张是根据代码生成的 3D 模型渲染图

## 预期规格（来自图纸分析）
{drawing_spec}

## 当前代码
```python
{code}
```

## 任务
请仔细对比渲染结果与原始图纸，找出所有不一致的地方。对每个问题，给出：
1. 问题描述（什么地方不对）
2. 预期值（图纸上的尺寸）
3. 修改建议（需要怎么改代码）

输出格式：
```
问题1: [描述]
预期: [值]
修改: [建议]

问题2: [描述]
预期: [值]
修改: [建议]
```

如果渲染结果与图纸完全一致，输出 "PASS"。
"""

# ---- 阶段 4b: Coder 模型修改代码 ----

_FIX_CODE_PROMPT = """\
你是一位 CAD 程序员。以下代码生成的 3D 模型与预期不符，请根据修改指令修正代码。

## 当前代码
```python
{code}
```

## 修改指令
{fix_instructions}

## 要求
1. 只修改必要的部分，保持代码结构不变
2. 确保所有尺寸参数化
3. 保留 export 语句
4. 代码用 markdown 代码块包裹

请输出修正后的完整代码：
"""


def _parse_code(input: dict) -> dict:
    match = re.search(r"```(?:python)?\n(.*?)\n```", input["text"], re.DOTALL)
    if match:
        return {"result": match.group(1).strip()}
    return {"result": None}


def _extract_comparison(input: dict) -> dict:
    """提取对比结果"""
    text = input["text"]
    if "PASS" in text.upper() and len(text.strip()) < 20:
        return {"result": None}  # 完全匹配，无需修改
    return {"result": text}


class SmartCompareChain(SequentialChain):
    """阶段 4a: VL 模型对比原图和渲染图"""

    def __init__(self) -> None:
        prompt = ChatPromptTemplate(
            input_variables=[
                "drawing_spec", "code",
                "original_image_type", "original_image_data",
                "rendered_image_type", "rendered_image_data",
            ],
            messages=[
                HumanMessagePromptTemplate(
                    prompt=[
                        PromptTemplate(
                            input_variables=["drawing_spec", "code"],
                            template=_COMPARE_PROMPT,
                        ),
                        ImagePromptTemplate(
                            input_variables=["original_image_type", "original_image_data"],
                            template={"url": "data:image/{original_image_type};base64,{original_image_data}"},
                        ),
                        ImagePromptTemplate(
                            input_variables=["rendered_image_type", "rendered_image_data"],
                            template={"url": "data:image/{rendered_image_type};base64,{rendered_image_data}"},
                        ),
                    ]
                )
            ],
        )
        llm = ChatModelParameters.from_model_name("qwen-vl").create_chat_model()

        super().__init__(
            chains=[
                LLMChain(prompt=prompt, llm=llm),
                TransformChain(
                    input_variables=["text"],
                    output_variables=["result"],
                    transform=_extract_comparison,
                    atransform=None,
                ),
            ],
            input_variables=[
                "drawing_spec", "code",
                "original_image_type", "original_image_data",
                "rendered_image_type", "rendered_image_data",
            ],
            output_variables=["result"],
            verbose=True,
        )


class SmartFixChain(SequentialChain):
    """阶段 4b: Coder 模型根据修改指令修正代码"""

    def __init__(self) -> None:
        prompt = ChatPromptTemplate(
            input_variables=["code", "fix_instructions"],
            messages=[
                HumanMessagePromptTemplate(
                    prompt=[
                        PromptTemplate(
                            input_variables=["code", "fix_instructions"],
                            template=_FIX_CODE_PROMPT,
                        ),
                    ]
                )
            ],
        )
        llm = ChatModelParameters.from_model_name("qwen-coder").create_chat_model()

        super().__init__(
            chains=[
                LLMChain(prompt=prompt, llm=llm),
                TransformChain(
                    input_variables=["text"],
                    output_variables=["result"],
                    transform=_parse_code,
                    atransform=None,
                ),
            ],
            input_variables=["code", "fix_instructions"],
            output_variables=["result"],
            verbose=True,
        )


class SmartRefiner:
    """增强版改进器：VL 对比 + Coder 修正"""

    def __init__(self):
        self.compare_chain = SmartCompareChain()
        self.fix_chain = SmartFixChain()

    def refine(
        self,
        code: str,
        original_image: ImageData,
        rendered_image: ImageData,
        drawing_spec: DrawingSpec,
    ) -> str | None:
        """
        对比原图和渲染图，如有差异则修正代码。
        返回修正后的代码，如果 PASS 则返回 None。
        """
        # 4a: VL 对比
        comparison = self.compare_chain.invoke({
            "drawing_spec": drawing_spec.to_prompt_text(),
            "code": code,
            "original_image_type": original_image.type,
            "original_image_data": original_image.data,
            "rendered_image_type": rendered_image.type,
            "rendered_image_data": rendered_image.data,
        })["result"]

        if comparison is None:
            logger.info("Smart refiner: PASS — rendering matches drawing")
            return None

        logger.info(f"Smart refiner: found differences:\n{comparison}")

        # 4b: Coder 修正
        result = self.fix_chain.invoke({
            "code": code,
            "fix_instructions": comparison,
        })["result"]

        return result
```

**Step 2: 更新 v2/__init__.py**

```python
from .drawing_analyzer import DrawingAnalyzerChain
from .code_generator import CodeGeneratorChain
from .smart_refiner import SmartRefiner
from .modeling_strategist import ModelingStrategist, ModelingContext
```

**Step 3: Commit**

```bash
git add cad3dify/v2/
git commit -m "feat: implement SmartRefiner — VL comparison + Coder targeted fix"
```

---

### Task 8: 实现 v2 Pipeline 集成

**Files:**
- Modify: `cad3dify/pipeline.py`
- Modify: `cad3dify/__init__.py`

**目标：** 新增 `generate_step_v2()` 函数，串联所有 v2 阶段。

**Step 1: 在 pipeline.py 中新增 v2 入口**

在 `pipeline.py` 末尾追加：

```python
from .v2.drawing_analyzer import DrawingAnalyzerChain
from .v2.modeling_strategist import ModelingStrategist
from .v2.code_generator import CodeGeneratorChain
from .v2.smart_refiner import SmartRefiner


def generate_step_v2(
    image_filepath: str,
    output_filepath: str,
    num_refinements: int = 3,
    on_spec_ready: callable = None,
):
    """V2 增强管道：VL 读图 → 策略选择 → Coder 写码 → 智能改进

    Args:
        image_filepath: 输入图片路径
        output_filepath: 输出 STEP 文件路径
        num_refinements: 改进轮数（默认 3）
        on_spec_ready: DrawingSpec 就绪回调（可选，用于 UI 展示中间结果）
    """
    image_data = ImageData.load_from_file(image_filepath)

    # 阶段 1: VL 分析图纸
    logger.info("[V2] Stage 1: Analyzing drawing with VL model...")
    analyzer = DrawingAnalyzerChain()
    spec = analyzer.invoke(image_data)["result"]

    if spec is None:
        logger.error("[V2] Drawing analysis failed, falling back to v1 pipeline")
        return generate_step_from_2d_cad_image(
            image_filepath, output_filepath, num_refinements, model_type="qwen"
        )

    logger.info(f"[V2] Drawing spec: {spec.part_type}, dims={spec.overall_dimensions}")

    if on_spec_ready:
        on_spec_ready(spec)

    # 阶段 1.5: 选择建模策略
    logger.info("[V2] Stage 1.5: Selecting modeling strategy...")
    strategist = ModelingStrategist()
    context = strategist.select(spec)
    logger.info(f"[V2] Strategy selected for {spec.part_type}, {len(context.examples)} examples")

    # 阶段 2: Coder 生成代码
    logger.info("[V2] Stage 2: Generating CadQuery code with Coder model...")
    generator = CodeGeneratorChain()
    result = generator.invoke(context)["result"]

    if result is None:
        logger.error("[V2] Code generation failed")
        return

    code = Template(result).substitute(output_filename=output_filepath)
    logger.info("[V2] Code generation complete. Executing...")
    logger.debug(f"Generated code:\n{code}")

    # 阶段 3: 执行代码
    output = execute_python_code(code, model_type="qwen-coder", only_execute=False)
    logger.debug(output)

    # 阶段 4: 智能改进
    refiner = SmartRefiner()
    for i in range(num_refinements):
        logger.info(f"[V2] Stage 4: Smart refinement round {i+1}/{num_refinements}...")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            try:
                render_and_export_image(output_filepath, f.name)
            except Exception as e:
                logger.error(f"[V2] Rendering failed: {e}")
                continue

            rendered_image = ImageData.load_from_file(f.name)
            refined_code = refiner.refine(
                code=code,
                original_image=image_data,
                rendered_image=rendered_image,
                drawing_spec=spec,
            )

            if refined_code is None:
                logger.info(f"[V2] Refinement round {i+1}: PASS — no changes needed")
                break

            code = Template(refined_code).substitute(output_filename=output_filepath)
            logger.info(f"[V2] Refinement round {i+1}: applying fixes...")
            logger.debug(f"Refined code:\n{code}")

            try:
                output = execute_python_code(code, model_type="qwen-coder", only_execute=False)
                logger.debug(output)
            except Exception as e:
                logger.error(f"[V2] Execution failed after refinement: {e}")
                continue

    logger.info(f"[V2] Pipeline complete. Output: {output_filepath}")
```

**Step 2: 更新 __init__.py 导出**

在 `cad3dify/__init__.py` 追加：

```python
from .pipeline import generate_step_v2
```

**Step 3: 验证导入**

```bash
.venv/bin/python -c "from cad3dify import generate_step_v2; print('v2 pipeline imported OK')"
```

**Step 4: Commit**

```bash
git add cad3dify/pipeline.py cad3dify/__init__.py
git commit -m "feat: integrate v2 pipeline — VL analysis → strategy → coder → smart refine"
```

---

### Task 9: 更新 Streamlit UI 支持 v2 模式

**Files:**
- Modify: `scripts/app.py`

**目标：** UI 新增 v2 模式切换，v2 模式下展示中间 DrawingSpec JSON。

**Step 1: 重写 app.py**

```python
import argparse
import json
import os

import streamlit as st
from PIL import Image
from dotenv import load_dotenv

load_dotenv()
from cad3dify import generate_step_from_2d_cad_image, generate_step_v2


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_type", type=str, default="qwen")
    return parser.parse_args()


args = parse_args()

st.title("2D図面 → 3D CAD")

# 侧边栏
st.sidebar.header("设置")
pipeline_mode = st.sidebar.radio(
    "管道模式",
    ["v2 增强 (推荐)", "v1 经典"],
    index=0,
)
if pipeline_mode == "v1 经典":
    model_type = st.sidebar.selectbox(
        "模型",
        ["qwen", "qwen-vl", "gpt", "claude", "gemini"],
        index=0,
    )

uploaded_file = st.sidebar.file_uploader("上传工程图纸", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    ext = os.path.splitext(uploaded_file.name)[1].lstrip(".")
    st.image(image, caption="上传的图纸", use_column_width=True)
    st.write(f"图像尺寸: {image.size[0]} × {image.size[1]}")

    temp_file = f"temp.{ext}"
    with open(temp_file, "wb") as f:
        f.write(uploaded_file.getbuffer())

    if pipeline_mode == "v2 增强 (推荐)":
        # V2 模式：显示中间结果
        spec_container = st.empty()

        def on_spec_ready(spec):
            with spec_container.container():
                st.subheader("图纸分析结果")
                st.write(f"**零件类型:** {spec.part_type.value}")
                st.write(f"**描述:** {spec.description}")
                st.write(f"**总体尺寸:** {spec.overall_dimensions}")
                with st.expander("详细 JSON", expanded=False):
                    st.json(spec.model_dump())

        with st.spinner("V2 管道处理中..."):
            generate_step_v2(
                temp_file, "output.step",
                on_spec_ready=on_spec_ready,
            )
        st.success("3D CAD 模型生成完成!")
    else:
        # V1 经典模式
        with st.spinner("处理中..."):
            generate_step_from_2d_cad_image(
                temp_file, "output.step", model_type=model_type
            )
        st.success("3D CAD 模型生成完成!")
else:
    st.info("请在左侧上传工程图纸。")
```

**Step 2: Commit**

```bash
git add scripts/app.py
git commit -m "feat: update Streamlit UI with v2 pipeline mode and DrawingSpec display"
```

---

### Task 10: 端到端测试

**Files:**
- 使用: `sample_data/g1-3.jpg`

**目标：** 用法兰盘图纸端到端测试 v2 管道。

**Step 1: CLI 测试**

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
.venv/bin/python -c "
from dotenv import load_dotenv
load_dotenv()
from cad3dify import generate_step_v2
generate_step_v2('sample_data/g1-3.jpg', 'scripts/output_v2.step')
"
```

Expected:
- 日志显示 Stage 1/1.5/2/3/4 各阶段进度
- DrawingSpec 正确识别出 rotational_stepped 类型
- 生成 `scripts/output_v2.step` 文件

**Step 2: 验证输出文件**

```bash
.venv/bin/python -c "
import cadquery as cq
result = cq.importers.importStep('scripts/output_v2.step')
print(f'Valid: {result.val().isValid()}')
bb = result.val().BoundingBox()
print(f'Bounding box: {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f}')
"
```

Expected: Valid=True, bounding box 接近 100 x 100 x 30

**Step 3: CQ-Editor 预览**

```bash
echo 'import cadquery as cq
result = cq.importers.importStep("scripts/output_v2.step")
show_object(result, name="v2 output")' > scripts/view_v2.py
.venv/bin/python -m cq_editor scripts/view_v2.py
```

**Step 4: 对比 v1 和 v2 结果**

如果 v2 结果明显优于 v1（法兰盘有正确的阶梯结构、螺栓孔、圆角），则验证通过。

**Step 5: Web UI 测试**

```bash
cd /Users/wangym/workspace/agents/agentic-runtime/vendor/cad3dify
.venv/bin/python -m streamlit run scripts/app.py
```

上传 g1-3.jpg，选择 v2 模式，验证：
- 中间 DrawingSpec JSON 正确显示
- 最终生成 output.step

**Step 6: Commit**

```bash
git add scripts/view_v2.py
git commit -m "test: add v2 pipeline e2e test with flange drawing"
```

---

## 任务依赖关系

```
Task 1 (chat_models) ──┐
                        ├── Task 4 (DrawingAnalyzer)
Task 2 (part_types) ────┤                              ├── Task 8 (Pipeline v2) ── Task 9 (UI) ── Task 10 (E2E)
                        ├── Task 5 (Strategist) ────────┤
Task 3 (knowledge) ─────┤                              │
                        └── Task 6 (CodeGenerator) ─────┤
                                                        │
                            Task 7 (SmartRefiner) ──────┘
```

可并行：Task 1 | Task 2 + Task 3（知识库），然后 Task 4 + Task 5 + Task 6 + Task 7 可部分并行，最后 Task 8 → Task 9 → Task 10。
