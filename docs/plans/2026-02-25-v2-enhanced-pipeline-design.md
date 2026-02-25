# cad3dify v2 增强管道设计

> 日期: 2026-02-25
> 状态: 已批准

## 问题

当前 cad3dify 让单个 VL 模型同时承担图纸理解和代码生成，导致：
1. VL 模型的视觉理解能力被代码生成任务稀释
2. Prompt 只有通用 CadQuery 指导，没有针对零件类型的建模策略
3. Refine 循环是盲修——用 SVG 渲染图对比原图，LLM 很难精确判断几何误差
4. 没有中间结构化表示，无法校验参数是否正确

## 方案

两阶段管道 + 零件类型知识库：
- VL 模型专做图纸分析，输出结构化 JSON
- Coder 模型专做代码生成，接收 JSON + 建模策略 + few-shot 示例
- 知识库提供零件类型→建模策略映射

## 约束

- 仅 Qwen 系列模型（qwen-vl-max、qwen-coder-plus 等），通过 DashScope API
- 保留原架构（LangChain + Streamlit），插入新阶段
- v1 管道不改动，保持向后兼容
- 支持任意工程图纸，通过配置针对性优化

## 新增模块

```
cad3dify/
├── v2/                              # 新版管道
│   ├── __init__.py
│   ├── drawing_analyzer.py          # 阶段1：VL 图纸分析 → DrawingSpec JSON
│   ├── modeling_strategist.py       # 阶段1.5：零件类型 → 建模策略（规则引擎）
│   ├── code_generator.py            # 阶段2：Coder 模型生成代码
│   └── smart_refiner.py             # 阶段3：增强版改进（带维度对比）
├── knowledge/                       # 知识库
│   ├── __init__.py
│   ├── part_types.py                # 零件类型定义 + 分类规则
│   ├── modeling_strategies.py       # 每种类型的 CadQuery 最佳建模方式
│   └── examples/                    # 按类型组织的 few-shot 示例
│       ├── __init__.py
│       ├── rotational.py            # 旋转体（法兰、轴、套筒）
│       ├── plate.py                 # 板件
│       ├── bracket.py               # 支架
│       └── housing.py               # 箱体
```

## 管道流程

```
图片输入
  ↓
[阶段1] Drawing Analyzer (qwen-vl-max, temp=0.1)
  │  提取：零件类型、尺寸、特征、视图布局
  │  输出：DrawingSpec JSON
  ↓
[阶段1.5] Modeling Strategist (规则引擎，无 LLM)
  │  根据零件类型匹配建模策略
  │  选择：基体构建方式、特征添加顺序、圆角策略
  │  注入：对应的 few-shot 示例
  ↓
[阶段2] Code Generator (qwen-coder-plus, temp=0.3)
  │  输入：DrawingSpec + 建模策略 + few-shot 示例
  │  输出：CadQuery Python 代码
  ↓
[阶段3] 执行 + 调试（复用现有 agents.py）
  ↓
[阶段4] Smart Refiner
  │  4a. qwen-vl-max 对比原图 vs 渲染图 + DrawingSpec
  │  4b. 输出针对性修改指令
  │  4c. qwen-coder-plus 修改代码
  ↓
输出 STEP/STL
```

## DrawingSpec JSON 格式

```json
{
  "part_type": "rotational_stepped",
  "description": "三层阶梯法兰盘，带中心通孔和螺栓孔阵列",
  "views": ["front_section", "top"],
  "overall_dimensions": {
    "max_diameter": 100,
    "total_height": 30
  },
  "base_body": {
    "method": "revolve",
    "profile": [
      {"diameter": 100, "height": 10, "label": "base_flange"},
      {"diameter": 40, "height": 10, "label": "middle_boss"},
      {"diameter": 24, "height": 10, "label": "top_boss"}
    ],
    "bore": {"diameter": 10, "through": true}
  },
  "features": [
    {
      "type": "hole_pattern",
      "pattern": "circular",
      "count": 6,
      "diameter": 10,
      "pcd": 70,
      "on_layer": "base_flange"
    },
    {
      "type": "fillet",
      "radius": 3,
      "locations": ["step_transitions"]
    }
  ]
}
```

## 建模策略知识库

### 旋转体 (rotational)

```
基体构建：revolve profile（一次成型）
- 在 XZ 平面绘制半截面轮廓，revolve 360°
- 绝对不要用多个圆柱 union（导致圆角失败）
- 轮廓点按 (radius, height) 逆时针排列

特征添加顺序：
1. revolve 基体
2. fillet 阶梯过渡处（NearestToPointSelector）
3. cut 孔特征（通孔、螺栓孔阵列）

陷阱：
- fillet 必须在 cut 之前
- NearestToPointSelector 比 >Z/<Z 更可靠
- 螺栓孔用独立 Workplane + circle + extrude + cut
```

### 板件 (plate)

```
基体构建：sketch + extrude
- 在 XY 平面绘制轮廓，extrude 厚度
- 复杂轮廓用 polyline + arc 组合

特征添加：
1. extrude 基板
2. 切槽/开孔：faces(">Z").workplane().hole()
3. 圆角/倒角：edges 选择器
```

### 支架 (bracket)

```
基体构建：多平面 sketch + extrude + union
- 分解为底板 + 立板 + 加强筋
- 各部分独立建模后 union

特征：
1. 底板孔位
2. 连接处圆角
3. 加强筋用 loft 或 extrude
```

### 箱体 (housing)

```
基体构建：shell 或 extrude + cut
- 外形 extrude 后 shell 抽壳
- 或外形 - 内腔 cut

特征：
1. shell 抽壳
2. 安装凸台
3. 密封面加工
```

## 模型分工

| 阶段 | 模型 | 温度 | 说明 |
|------|------|------|------|
| 图纸分析 | qwen-vl-max | 0.1 | 低温度确保参数提取准确 |
| 代码生成 | qwen-coder-plus | 0.3 | 中低温度平衡创造性和准确性 |
| 代码修复 | qwen-coder-plus | 0.1 | 低温度精确修复 |
| 视觉对比 | qwen-vl-max | 0.1 | 判断渲染结果与原图差异 |

## 对现有代码的改动

| 文件 | 改动 |
|------|------|
| `chat_models.py` | 新增 `qwen-vl` 和 `qwen-coder` 模型配置，支持 pipeline 内使用不同模型 |
| `pipeline.py` | 新增 `generate_step_v2()` 入口函数 |
| `scripts/app.py` | UI 新增 v2 模式选项，显示中间 JSON 供用户确认 |
| `v1/*` | 不改动 |

## 验收标准

1. 使用 sample_data/g1-3.jpg 测试，v2 管道生成的法兰盘应具备：
   - 正确的三层阶梯结构 (φ100/φ40/φ24)
   - 中心通孔 φ10
   - 6×φ10 螺栓孔，PCD φ70
   - 阶梯过渡 R3 圆角
2. DrawingSpec JSON 参数与图纸标注一致
3. 生成的 STEP 文件可在 CQ-Editor 中正确打开和渲染
4. v1 管道不受影响，向后兼容
