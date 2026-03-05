---
title: HuggingFace 数据集目录
tags:
  - research
  - huggingface
  - dataset-catalog
  - deep-analysis
status: active
created: 2026-03-03
last_updated: 2026-03-03
---

# HuggingFace 数据集目录

> [!abstract] 说明
> 本页汇总 HuggingFace Hub 上与 3D 打印/CAD/增材制造相关的所有数据集。按用途分类，标注规模和许可。含深入质量评估和部署指南。

---

## CAD/CadQuery 代码数据集

### ThomasTheMaker/cadquery ⭐ 质量评级: 3/5

> [!success] 唯一直接可用的 CadQuery 代码数据集

| 属性 | 详情 |
|:-----|:-----|
| **链接** | [ThomasTheMaker/cadquery](https://huggingface.co/datasets/ThomasTheMaker/cadquery) |
| **规模** | ==147,289== 条（图像 + CadQuery 代码） |
| **格式** | Parquet，~670MB 磁盘 / 896MB 内存 |
| **来源** | CADCODER/GenCAD-Code 数据集子集 |
| **字段** | `images`（渲染图）+ `texts`（含 CadQuery 代码） |

#### 深入质量分析

**CadQuery API 覆盖（前 100 条统计）**：

| API 函数 | 调用次数 | 说明 |
|:---------|:--------|:-----|
| `Vector` | 537 | 工作平面原点/方向 |
| `lineTo` | 486 | 直线段（最高频） |
| `moveTo` | 247 | 移动起点 |
| `extrude` | 179 | 拉伸操作 |
| `circle` | 109 | 圆形轮廓 |
| `threePointArc` | 78 | 三点弧线 |
| `union` | 53 | 布尔并集 |
| `cut` | 26 | 布尔减法 |

> [!danger] 关键局限
> - ==仅使用约 12 个 CadQuery API 函数==
> - ==无 `revolve`、`sweep`、`loft`、`fillet`、`chamfer`、`shell`==
> - 完全基于 sketch-and-extrude + boolean 范式
> - user 字段完全相同（"Generate the CADQuery code..."），==无自然语言描述==
> - 尺寸归一化在 0-1.5 范围，非工程实际尺寸
> - 代码风格非标准（`wp.add(loop).extrude()` 模式）

**代码长度分布**：均值 872 chars / 中位数 593 chars / 最大 2,857 chars

#### CADPilot 兼容性

| CADPilot 零件类型 | 数据集覆盖 | 缺口 |
|:-----------------|:---------|:-----|
| PLATE（板件） | ✅ sketch+extrude | 覆盖 |
| BRACKET（支架） | ✅ | 覆盖 |
| GENERAL（通用） | ✅ | 覆盖 |
| ROTATIONAL（回转体） | ==❌ 无 revolve== | ==严重缺口== |
| ROTATIONAL_STEPPED | ==❌== | ==严重缺口== |
| HOUSING（壳体） | ⚠️ 缺 shell | 中等缺口 |
| GEAR（齿轮） | ==❌== | ==严重缺口== |

#### 部署指南

```python
from datasets import load_dataset
ds = load_dataset("ThomasTheMaker/cadquery", split="train")
# 147,289 条

# 提取代码
codes = [row['texts'][0]['assistant'] for row in ds]

# 验证可执行性（抽样 100 条）
import cadquery as cq
import random
samples = random.sample(codes, 100)
success = sum(1 for c in samples if _try_exec(c))
print(f"成功率: {success}%")
```

---

### Text2CAD 质量评级: 2.5/5

| 属性 | 详情 |
|:-----|:-----|
| **链接** | [SadilKhan/Text2CAD](https://huggingface.co/datasets/SadilKhan/Text2CAD) |
| **规模** | 170K 模型 + ==660K 多级文本标注==（==605 GB 总量==） |
| **许可** | ==CC-BY-NC-SA 4.0==（非商用） |
| **核心数据** | `minimal_json/`（246MB）—— 真正需要下载的部分 |

#### 深入分析

**多级文本标注**（4 个级别）：
- Level 0 Abstract: "Generate two concentric cylinders"
- Level 1 Beginner: "Create a ring-like shape..."
- Level 2 Intermediate: 含草图和拉伸细节
- Level 3 Expert: 精确参数化指令

> [!warning] 已知质量问题
> - GitHub Issue #38 指出 minimal_json 存在==缩放不一致问题==
> - CAD 序列为 DeepCAD JSON 格式，==非 CadQuery 代码==
> - 605GB 中 397GB 为渲染图像，核心 JSON 仅 246MB
> - 文本标注由 LLM/VLM 自动生成，存在幻觉风险

**建议**：仅下载 `minimal_json/`（246MB），用于参考 CAD 序列结构和多级文本标注设计。

---

### Omni-CAD 质量评级: 3.5/5

| 属性 | 详情 |
|:-----|:-----|
| **链接** | [jingwei-xu-00/Omni-CAD](https://huggingface.co/datasets/jingwei-xu-00/Omni-CAD) |
| **规模** | ~==450K== 实例 |
| **许可** | ==MIT== |
| **内容** | 首个多模态 CAD 数据集：文本+多视图图像+点云+CAD 命令序列+==STEP 文件== |

> [!tip] CADPilot 集成价值
> - MIT 许可证非常友好
> - 含 STEP 文件可直接用于 CadQuery 验证
> - 多模态数据与 CADPilot V3 多输入设计一致
> - 但命令序列非 CadQuery 格式，需转换

---

### thingiverse-openscad 质量评级: 3.5/5

| 属性 | 详情 |
|:-----|:-----|
| **链接** | [redcathode/thingiverse-openscad](https://huggingface.co/datasets/redcathode/thingiverse-openscad) |
| **规模** | 7,378 条 |
| **许可** | CC-BY-NC-SA 4.0 |
| **内容** | ==真实世界== Thingiverse 参数化 OpenSCAD 代码 + Gemini 合成提示词 |

> [!tip] 特殊价值
> - 包含 `rotate_extrude()`（==可映射到 CadQuery `revolve()`==）
> - 包含 `hull()`、`minkowski()` 等高级操作
> - 参数化设计模式（含 Customizer 注释）可启发 ParametricTemplate
> - LLM 辅助 OpenSCAD→CadQuery 转换是可行路径

### openscad-vision

| 属性 | 详情 |
|:-----|:-----|
| **链接** | [adrlau/openscad-vision](https://huggingface.co/datasets/adrlau/openscad-vision) |
| **规模** | 1,963 条（1,766 train + 197 test） |
| **内容** | NL 提示 + OpenSCAD 代码 + 多角度渲染（1.39GB） |

---

## 3D 模型数据集

### Thingi10K 质量评级: 4/5

> [!tip] Mesh 修复研究宝库——含详细缺陷统计和 Python API

| 属性 | 详情 |
|:-----|:-----|
| **链接** | [Thingi10K/Thingi10K](https://huggingface.co/datasets/Thingi10K/Thingi10K) |
| **GitHub** | [Thingi10K/Thingi10K](https://github.com/Thingi10K/Thingi10K) |
| **Python API** | `pip install thingi10k` |
| **规模** | 10,000 STL / 72 类 |
| **月下载** | 1,271 |

#### 缺陷分布统计

| 缺陷类型 | 占比 |
|:---------|:-----|
| ==Non-solid== | 50% |
| ==Self-intersecting== | 45% |
| Non-manifold | 22% |
| Degenerate faces | 16% |

→ 详见 [[mesh-processing-repair#Thingi10K 测试基准]]

### Objaverse / Objaverse-XL

| 数据集 | 规模 | 许可 | 月下载 |
|:-------|:-----|:-----|:-------|
| [Objaverse](https://huggingface.co/datasets/allenai/objaverse) | 800K+ 3D | ODC-By | 525K |
| [Objaverse-XL](https://huggingface.co/datasets/allenai/objaverse-xl) | 10M+ 3D | ODC-By | - |

### 其他 3D 数据集

| 数据集 | 规模 | 内容 |
|:-------|:-----|:-----|
| [ShapeNetCore](https://huggingface.co/datasets/ShapeNet/ShapeNetCore) | 51K / 55 类 | 日常物体（非商业） |
| [Cap3D](https://huggingface.co/datasets/tiange/Cap3D) | - | 3D 对象文本描述 |
| [MeshCoderDataset](https://huggingface.co/datasets/InternRobotics/MeshCoderDataset) | 10万-100万 | 点云+Blender 脚本 |

---

## G-code 数据集

### ablam/gcode 质量评级: 1.5/5

> [!warning] 数据价值密度极低

| 属性 | 详情 |
|:-----|:-----|
| **链接** | [ablam/gcode](https://huggingface.co/datasets/ablam/gcode) |
| **规模** | ==442,674,171 行==，但仅对应 ==400 个模型 / 740 个切片文件== |
| **格式** | 逐行拍平的 Parquet 单列文本 |
| **切片器** | 仅 PrusaSlicer 2.1.1+ |
| **打印机** | 仅 Original Prusa i3 MK3S |

> [!danger] 关键问题
> - 逐行拍平==丢失了文件边界信息==
> - 442M 行的"大"是假象——平均每文件 ~60 万行移动指令
> - 无对应的 STL/STEP 源文件
> - 单一切片器 + 单一打印机 + 单一类别（Art & Design）
> - 更适合 G-code 语言模型训练，对 CADPilot 价值低

---

## 增材制造/缺陷检测数据集

### 3D-ADAM ⭐ 质量评级: 4/5

> [!success] AM 领域最大的 RGB+3D 缺陷检测数据集

| 属性 | 详情 |
|:-----|:-----|
| **链接** | [pmchard/3D-ADAM](https://huggingface.co/datasets/pmchard/3D-ADAM) |
| **论文** | [arXiv:2507.07838](https://arxiv.org/abs/2507.07838) |
| **规模** | ==14,120 扫描==、217 零件、29 类别 |
| **标注** | ==27,346 缺陷标注==（12 类）+ ==27,346 机械特征标注==（16 类） |
| **传感器** | 4 种工业深度传感器 |
| **许可** | ==CC-BY-NC-SA 4.0==（非商用） |
| **月下载** | 15,411 |

#### 12 类缺陷（深入分析）

| # | 缺陷类型 | AM 相关性 |
|:--|:---------|:---------|
| 1 | 鼓包 Bulges | ==高==（过挤出） |
| 2 | 孔洞 Holes | ==高== |
| 3 | 间隙 Gaps | ==高==（层间缺陷） |
| 4 | 裂纹 Cracks | ==高== |
| 5 | 翘曲 Warping | ==高==（核心 AM 问题） |
| 6 | 粗糙度 Roughness | ==高== |
| 7 | 过挤出 Over-extrusion | ==高== |
| 8 | 欠挤出 Under-extrusion | ==高== |
| 9 | 切割 Cuts | 中 |
| 10 | 毛刺 Burrs | 中 |
| 11 | 划痕 Scratches | 低 |
| 12 | 印记 Marks | 低 |

#### 部署指南

```python
from datasets import load_dataset

# 流式加载（推荐）
ds = load_dataset("pmchard/3D-ADAM", streaming=True)

# anomalib 集成
ds_anomalib = load_dataset("pmchard/3D-ADAM_anomalib")
```

→ 详见 [[defect-detection-monitoring#3D-ADAM 深入分析]]

### VISION-Datasets

| 属性 | 详情 |
|:-----|:-----|
| **链接** | [VISION-Workshop/VISION-Datasets](https://huggingface.co/datasets/VISION-Workshop/VISION-Datasets) |
| **规模** | 14 数据集，18K+ 图像，44 种缺陷 |
| **许可** | CC-BY-NC 4.0 |
| **涵盖** | Cable, Capacitor, ==Casting==, Console, ==Cylinder==, Electronics 等 |

### Defect Spectrum

| 属性 | 详情 |
|:-----|:-----|
| **链接** | [DefectSpectrum/Defect_Spectrum](https://huggingface.co/datasets/DefectSpectrum/Defect_Spectrum) |
| **规模** | 13,069 条 / 1.95 GB |
| **许可** | ==MIT== |
| **月下载** | 7,882 |
| **特点** | 富语义标注 + VLM 字幕 |

### failures-3D-print

| 属性 | 详情 |
|:-----|:-----|
| **链接** | [Javiai/failures-3D-print](https://huggingface.co/datasets/Javiai/failures-3D-print) |
| **规模** | 73 张 / 3.55 MB |
| **分类** | error / extrusor / part / spaghetti |

---

## 材料/微观结构数据集

### porous-microstructure-strain-fields

| 属性 | 详情 |
|:-----|:-----|
| **链接** | [cmudrc/porous-microstructure-strain-fields](https://huggingface.co/datasets/cmudrc/porous-microstructure-strain-fields) |
| **许可** | CC BY 4.0 |
| **内容** | 多种缺陷形状的微观结构+应变场 |

### Materials

| 属性 | 详情 |
|:-----|:-----|
| **链接** | [Allanatrix/Materials](https://huggingface.co/datasets/Allanatrix/Materials) |
| **规模** | 86,988 条 |
| **许可** | CC BY 4.0 |

---

## 非 HuggingFace 关键数据源

| 数据集 | 来源 | 内容 | 获取 |
|:-------|:-----|:-----|:-----|
| **ORNL Peregrine** | 橡树岭国家实验室 | LPBF 原位监控 | [Globus](https://doi.ccs.ornl.gov) |
| **NIST AM-Bench** | NIST | AM 基准 | [NIST](https://www.nist.gov/ambench) |
| **Slice-100K** | NeurIPS 2024 | 100K+ G-code + CAD + 渲染 | [GitHub](https://github.com/idealab-isu/Slice-100K) |

---

## 按 CADPilot 关联度排序

> [!success] 第一梯队：直接可用

1. **ThomasTheMaker/cadquery** — 147K CadQuery 代码对（==唯一直接兼容，但 API 覆盖窄==）
2. **Omni-CAD** — 450K 多模态 CAD（MIT 许可，含 STEP 文件）
3. **Thingi10K** — mesh 修复测试基准（含 Python API + 缺陷统计）
4. **3D-ADAM** — 14K 扫描 AM 缺陷检测（非商用）

> [!info] 第二梯队：需要转换或仅作参考

5. **thingiverse-openscad** — 7.4K 真实 OpenSCAD 参数化设计（需 LLM 转换）
6. **Text2CAD** — 660K 多级标注（核心 JSON 仅 246MB，非 CadQuery 格式）
7. **Defect Spectrum** — 工业缺陷（MIT 许可）

> [!warning] 第三梯队：价值有限

8. **ablam/gcode** — 逐行拍平、单一配置，实际仅 400 模型

---

## 关键缺口分析

> [!danger] CADPilot 训练数据缺口
> 所有公开 CadQuery 数据集都严重偏向 ==sketch+extrude==，缺少 revolve/fillet/chamfer/shell 等高级操作。CADPilot 的回转体、齿轮等核心零件类型==无法从现有数据集获得训练数据==，需要自建。

---

## 更新日志

| 日期 | 变更 |
|:-----|:-----|
| 2026-03-03 | 深入研究更新：ThomasTheMaker/cadquery API 覆盖分析和代码质量评估；Text2CAD 605GB 实用性分析；Omni-CAD/OpenSCAD 集成可行性；ablam/gcode 数据质量问题揭示；关键缺口分析 |
| 2026-03-03 | 初始版本 |
