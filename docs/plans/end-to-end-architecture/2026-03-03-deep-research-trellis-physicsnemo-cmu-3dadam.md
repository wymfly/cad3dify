# 四大开源项目深度调研：TRELLIS、PhysicsNeMo、CMU DRL、3D-ADAM

> 调研日期：2026-03-03
> 范围：架构深剖、部署指南、验证协议、CADPilot 集成分析
> 方法论：GitHub 代码分析 + 论文阅读 + HuggingFace/NVIDIA 官方文档 + 社区反馈

---

## 目录

1. [Task 1: TRELLIS (Microsoft, MIT License)](#task-1-trellis)
2. [Task 2: NVIDIA PhysicsNeMo (Apache 2.0)](#task-2-nvidia-physicsnemo)
3. [Task 3: CMU ThermalControlLPBF-DRL](#task-3-cmu-thermalcontrollpbf-drl)
4. [Task 4: 3D-ADAM 数据集](#task-4-3d-adam-数据集)
5. [综合评估与 CADPilot 集成路线图](#综合评估)

---

## Task 1: TRELLIS

> Microsoft Research, MIT License, CVPR'25 Spotlight
> GitHub: [microsoft/TRELLIS](https://github.com/microsoft/TRELLIS) (v1) / [microsoft/TRELLIS.2](https://github.com/microsoft/TRELLIS.2) (v2)
> HuggingFace: [microsoft/TRELLIS.2-4B](https://huggingface.co/microsoft/TRELLIS.2-4B)

### 1.1 架构深剖

#### 1.1.1 整体流水线

```
输入图像
  → 背景移除（自动 or 手动）
  → Stage 1: Sparse Structure Generation (稀疏结构生成)
  → Stage 2: SLAT Flow (形状细节合成)
  → Stage 3: PBR Texture Flow (PBR 纹理生成)
  → O-Voxel → GLB 导出 (remesh + UV unwrap + texture bake)
```

#### 1.1.2 Sparse 3D VAE

TRELLIS 的核心创新是 **Structured LATent (SLAT)** 表征——将 3D 资产编码到统一的稀疏体素隐空间中。

- **编码器**：Sparse 3D VAE，支持 16x 空间下采样
- **1024^3 分辨率资产 → ~9,600 个 latent tokens**（感知退化可忽略不计）
- 编码器将纹理网格转为 O-Voxel，CPU 上 <10 秒；逆变换 CUDA 上 <100ms

**关键优势**：统一隐空间允许从同一编码解码到多种格式：
- 辐射场 (Radiance Fields)
- 3D 高斯 (3D Gaussians) → PLY
- 三角网格 (Meshes) → GLB with PBR

#### 1.1.3 Flow-Matching Transformer

- 生成模型采用 **Rectified Flow Transformers (DiTs)**
- TRELLIS v1: 342M~2B 参数，训练于 500K 3D 资产
- TRELLIS.2: **4B 参数**，vanilla DiTs，全量 flow matching
- 三阶段顺序生成：稀疏结构 → 形状细节 → PBR 纹理

#### 1.1.4 O-Voxel 结构

O-Voxel 是 TRELLIS.2 引入的 **"无场"(field-free) 稀疏体素表征**：

| 特性 | 说明 |
|------|------|
| **Flexible Dual Grid** | 双网格公式，鲁棒地表征任意拓扑表面 |
| **开放表面** | 直接支持衣物、树叶等非封闭几何 |
| **非流形几何** | 不依赖 SDF/Flexicubes 等隐式场，绕过其拓扑限制 |
| **内部封闭结构** | 可表征内部空腔等复杂结构 |
| **锐利边缘** | 几何组件使用 Flexible Dual Grids，保持锐利棱边 |

**与传统方法的核心区别**：
- 传统方法（SDF、FlexiCubes、DMTet）依赖等值面场提取，无法处理开放面和非流形
- O-Voxel 直接在稀疏体素网格上编码表面，无需隐式场中间步骤

#### 1.1.5 PBR 材质管线

四通道 PBR 材质属性建模：

| 通道 | 说明 |
|------|------|
| Base Color | 基色纹理 |
| Roughness | 粗糙度 |
| Metallic | 金属度 |
| Opacity | 透明度 |

- 第三阶段 flow model 专门负责纹理合成
- 以生成的几何为条件，独立或集成管线运行
- 默认 OPAQUE 模式输出 GLB；透明度需用户在 3D 软件中手动连接 alpha 通道

### 1.2 输出质量分析

#### 1.2.1 与竞品对比

| 维度 | TRELLIS.2 | Hunyuan3D 2.5 | SPAR3D |
|------|-----------|---------------|--------|
| **拓扑质量** | 最优：O-Voxel 直接处理复杂拓扑 | 良好：整体更平滑但丢失细节 | 较差但最快 |
| **锐利特征** | 通过 Dual Grid 保持锐边 | 边缘倾向平滑化 | 边缘模糊 |
| **PBR 材质** | 完整 4 通道 PBR | 仅基色纹理为主 | 基色 + 简单材质 |
| **非流形支持** | 原生支持 | 不支持 | 不支持 |
| **分辨率上限** | 1536^3 | 未明确 | 未明确 |
| **生成速度 (H100)** | 1024^3: 17s | ~30s | ~5s |
| **参数量** | 4B | 1.5B | <1B |

#### 1.2.2 常见失败模式

| 问题 | 严重度 | 说明 |
|------|--------|------|
| **背景未移除导致伪影** | 高 | 不移除背景会导致严重伪影和几何缺失 |
| **薄壁特征坍缩** | 中 | 激进 decimation (<0.8) 可能压缩手指、面部等细节 |
| **小孔和拓扑不连续** | 低 | 生成的原始网格偶尔包含小孔（可后处理修复） |
| **训练分布偏差** | 中 | 未经 RLHF 对齐，输出反映训练数据分布 |
| **输入质量敏感** | 中 | 结果与输入图像质量强相关 |

### 1.3 部署指南

#### 1.3.1 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Linux（Windows 未完全测试） |
| GPU | NVIDIA GPU，**最低 24GB VRAM**（推荐 A100/H100） |
| CUDA | 12.4（TRELLIS.2）/ 11.8 或 12.2（TRELLIS v1） |
| Python | 3.8+ |
| 包管理 | Conda |

**重要警告**：社区报告 VRAM 峰值可达 **63GB+**（GitHub Issue #24），24GB 消费级 GPU 需要内存优化。推荐 A100 80GB 或 H100。

#### 1.3.2 安装步骤（TRELLIS.2）

```bash
# Step 1: 克隆仓库
git clone -b main https://github.com/microsoft/TRELLIS.2.git --recursive
cd TRELLIS.2

# Step 2: 安装环境（一键脚本）
. ./setup.sh --new-env --basic --flash-attn --nvdiffrast --nvdiffrec --cumesh --o-voxel --flexgemm

# Step 3: 如有多 CUDA 版本，设置 CUDA_HOME
export CUDA_HOME=/usr/local/cuda-12.4

# 创建 conda 环境名: trellis2
# PyTorch 2.6.0 + CUDA 12.4
```

**关键依赖**：

| 包 | 用途 |
|----|------|
| nvdiffrast | 渲染 |
| nvdiffrec | Split-sum PBR 材质渲染 |
| FlexGEMM | Triton 稀疏卷积 |
| CuMesh | CUDA 加速网格工具 |
| Flash-Attention | 优化注意力后端 |
| o-voxel | O-Voxel 表征库 |

#### 1.3.3 推理代码示例

```python
from trellis2.pipelines import Trellis2ImageTo3DPipeline
from PIL import Image

# 加载模型（首次自动从 HuggingFace 下载）
pipeline = Trellis2ImageTo3DPipeline.from_pretrained("microsoft/TRELLIS.2-4B")
pipeline.cuda()

# 生成
image = Image.open("input.png")
mesh = pipeline.run(image)[0]

# 导出 GLB（含 PBR 材质）
import o_voxel
glb = o_voxel.postprocess.to_glb(
    vertices=mesh.vertices,
    faces=mesh.faces,
    attr_volume=mesh.attrs,
    voxel_size=mesh.voxel_size,
    decimation_target=1000000,   # 目标面数
    texture_size=4096,            # 纹理分辨率
    remesh=True                   # 开启重网格化
)
glb.export("output.glb", extension_webp=True)
```

#### 1.3.4 处理时间

| 分辨率 | 形状生成 | 材质生成 | 总计 (H100) |
|--------|----------|----------|-------------|
| 512^3 | 2s | 1s | **~3s** |
| 1024^3 | 10s | 7s | **~17s** |
| 1536^3 | 35s | 25s | **~60s** |

### 1.4 与 CADPilot generate_raw_mesh 集成

#### 1.4.1 链路设计：TRELLIS → MeshAnythingV2 → mesh_healer

```
TRELLIS (generate_raw_mesh, strategy="trellis")
  ├─ 输入: PreciseSpec → 渲染参考图 or 用户上传图片
  ├─ 输出: GLB (O-Voxel export, 含 PBR 材质)
  │
  ├─ [可选] MeshAnythingV2 (retopo 子步骤)
  │   ├─ 输入: TRELLIS 输出的三角网格
  │   ├─ 输出: 优化拓扑的 artist-mesh
  │   └─ 触发条件: face_count > retopo_threshold
  │
  └─ mesh_healer (下游节点)
      ├─ AlgorithmHealStrategy: trimesh → PyMeshFix → MeshLib 逐级升级
      ├─ NeuralHealStrategy: NKSR HTTP endpoint
      └─ 输出: watertight_mesh (GLB/OBJ)
```

#### 1.4.2 格式转换管线

```python
import trimesh

# Step 1: TRELLIS → GLB（TRELLIS 原生输出）
# 已由 o_voxel.postprocess.to_glb() 完成

# Step 2: GLB → trimesh 对象（CADPilot 内部格式）
mesh = trimesh.load("trellis_output.glb", force="mesh")

# Step 3: trimesh → 任意目标格式
mesh.export("output.stl")     # STL（3D 打印）
mesh.export("output.obj")     # OBJ（通用）
mesh.export("output.ply")     # PLY（点云兼容）
mesh.export("output.glb")     # GLB（Web 展示）
```

**与 CADPilot AssetRegistry 对接**：
- TRELLIS 策略的 `execute()` 将 GLB 写入 `jobs/{job_id}/raw_mesh.glb`
- 调用 `ctx.put_asset("raw_mesh", path, "glb")` 注册资产
- mesh_healer 通过 `ctx.get_asset("raw_mesh")` 获取并加载

#### 1.4.3 CADPilot TrellisGenerateStrategy 骨架

```python
class TrellisGenerateStrategy(NodeStrategy):
    """TRELLIS local endpoint strategy for generate_raw_mesh."""

    async def check_available(self) -> bool:
        endpoint = self.config.trellis_endpoint
        if not endpoint:
            return False
        # Health check
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{endpoint}/health")
            return resp.status_code == 200

    async def execute(self, ctx: NodeContext) -> None:
        # 1. 准备输入图像
        image_path = ctx.get_data("reference_image") or self._render_reference(ctx)

        # 2. 调用 TRELLIS endpoint
        async with httpx.AsyncClient(timeout=ctx.config.timeout) as client:
            resp = await client.post(
                f"{ctx.config.trellis_endpoint}/v1/generate",
                files={"image": open(image_path, "rb")},
                data={
                    "resolution": ctx.config.trellis_resolution or 1024,
                    "decimation_target": ctx.config.decimation_target or 500000,
                    "texture_size": ctx.config.texture_size or 2048,
                }
            )
            resp.raise_for_status()
            result = resp.json()

        # 3. 下载 GLB 并注册资产
        mesh_path = f"/workspace/jobs/{ctx.job_id}/raw_mesh.glb"
        # ... download result["mesh_url"] to mesh_path
        ctx.put_asset("raw_mesh", mesh_path, "glb")
```

### 1.5 综合评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **架构创新** | ★★★★★ | O-Voxel + Sparse 3D VAE 是当前最先进的 3D 表征 |
| **输出质量** | ★★★★☆ | 同类最优，但仍有小孔和薄壁问题 |
| **部署易用性** | ★★★☆☆ | 依赖复杂（CUDA 编译），VRAM 需求高 |
| **CADPilot 适配性** | ★★★★☆ | GLB 输出与 trimesh/mesh_healer 无缝对接 |
| **许可合规** | ★★★★★ | MIT License，完全自由 |
| **社区活跃度** | ★★★★★ | 2.6M 月下载，CVPR'25 Spotlight |

### 1.6 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| GPU 不足（<24GB VRAM） | 高 | 阻塞 | 使用云 GPU 或 TRELLIS v1 小模型 |
| 网格质量不足（非水密） | 中 | 低 | mesh_healer 下游修复 |
| CUDA 依赖编译失败 | 中 | 阻塞 | Docker 镜像部署 |
| 工程图零件（非自然物体）质量差 | 中 | 中 | 训练数据偏向自然物体，工程零件效果待验证 |

---

## Task 2: NVIDIA PhysicsNeMo

> NVIDIA, Apache 2.0 License
> GitHub: [NVIDIA/physicsnemo](https://github.com/NVIDIA/physicsnemo)
> 文档: [docs.nvidia.com/physicsnemo](https://docs.nvidia.com/physicsnemo/latest/index.html)
> PyPI: [nvidia-physicsnemo](https://pypi.org/project/nvidia-physicsnemo/)

### 2.1 框架分析

#### 2.1.1 支持的架构

| 架构类别 | 具体模型 | 适用场景 |
|----------|----------|----------|
| **神经算子** | FNO, PINO, DeepONet, DoMINO | PDE 求解、CFD |
| **图神经网络** | MeshGraphNet (Base/Hybrid/X-variant) | 非结构化网格物理仿真 |
| **扩散模型** | Diffusion Models | 生成式物理模拟 |
| **PINN** | Physics-Informed Neural Networks | 约束物理方程的网络训练 |
| **序列模型** | RNN, SwinVRNN, Transformer | 时间序列预测 |
| **几何处理** | CSG 建模（physicsnemo.sym.geometry） | CAD/几何 |

#### 2.1.2 Python API 质量

| 模块 | API 说明 | 文档质量 |
|------|----------|----------|
| `physicsnemo.models` | 优化的模型架构族 | ★★★★☆ |
| `physicsnemo.datapipes` | 科学数据管道 | ★★★★☆ |
| `physicsnemo.distributed` | 基于 torch.distributed 的分布式训练 | ★★★★☆ |
| `physicsnemo.sym.eq` | PDE 实现（物理约束训练） | ★★★☆☆ |
| `physicsnemo.sym.geometry` | CSG 建模几何处理 | ★★★☆☆ |

**API 整体评价**：模块化设计清晰，文档完善有教程和示例，但 sym 模块文档略薄。

#### 2.1.3 安装复杂度

```bash
# 方式 1: PyPI（推荐，最简）
pip install nvidia-physicsnemo

# 方式 2: 指定 CUDA 后端 + 扩展
pip install "nvidia-physicsnemo[cu12,nn-extras]"   # CUDA 12
pip install "nvidia-physicsnemo[cu13,nn-extras]"   # CUDA 13

# 方式 3: 开发模式（uv）
git clone https://github.com/NVIDIA/physicsnemo.git
cd physicsnemo
uv sync --extra cu13
```

**安装复杂度评估**：★★☆☆☆（非常简单），PyPI 一行命令。

#### 2.1.4 GPU 要求

| 场景 | GPU 需求 |
|------|----------|
| 推理 | 单 GPU 即可，甚至笔记本（HP 宣称 "可在笔记本运行"） |
| 训练（单 GPU） | 8~16GB VRAM（小型 MeshGraphNet） |
| 训练（大规模） | 多 GPU/多节点，支持分布式训练 |
| MeshGraphNet 优化 | float16/bfloat16 支持，>200K 节点网格有 1.5~2x 加速 |
| 梯度检查点 | `num_processor_checkpoint_segments` 参数解决深层网络 OOM |

### 2.2 AM 专项内容：Virtual Foundry GraphNet

#### 2.2.1 示例代码分析

**位置**：`examples/additive_manufacturing/sintering_physics/`

**代码结构**：
```
sintering_physics/
├── conf/
│   └── config.yaml          # Hydra 配置
├── data_process/
│   └── rawdata2tfrecord.py   # 原始仿真 → TFRecord 预处理
├── train.py                  # 训练入口
├── inference.py              # 推理入口
├── render_rollout.py         # 结果可视化
├── graph_dataset.py          # 图数据集加载
├── reading_utils.py          # TFRecord 读取
├── utils.py                  # 工具函数
└── requirements.txt          # 示例级依赖
```

#### 2.2.2 烧结物理示例做了什么

**核心功能**：预测金属烧结过程中零件的形变（收缩 25%~50%）。

**工作原理**：
1. **体素化**：STL/OBJ/3MF 设计文件 → 体素数据
2. **图构建**：体素 → 图节点，kd-tree 找邻居（半径 = 1.2 × 体素尺寸，~6 邻居/节点）
3. **GNN 预测**：基于历史位移序列 + 烧结温度曲线，预测下一时间步的位移场
4. **滚动推演**：自回归方式逐步推演完整烧结过程

**模型架构（Encoder-Processor-Decoder）**：
- **Encoder**：图卷积层提取特征，降维到隐空间
- **Processor**：Interaction Network，10 轮消息传递
- **Decoder**：MLP 映射隐节点特征 → 3D 位移向量

**节点特征**：前 n 个时间步的速度 + 边界约束（固定/滑移）
**边特征**：节点间相对距离
**全局特征**：烧结温度序列（可选）
**损失函数**：MSE on 加速度，带折扣因子的多步预测

#### 2.2.3 完备性评估

| 维度 | 评估 |
|------|------|
| **代码完整性** | ★★★★★ 完整的训练/推理/可视化流水线 |
| **数据预处理** | ★★★★☆ 提供 raw → TFRecord 转换工具 |
| **文档质量** | ★★★★☆ 有 README + NVIDIA 官方文档 + 博客 |
| **可复现性** | ★★★☆☆ 需要 HP 的训练数据（仅 7 个几何体），数据未完全开源 |
| **通用性** | ★★★☆☆ 专为 Metal Jet 烧结设计，需修改才能用于其他 AM 过程 |

#### 2.2.4 HP Virtual Foundry GraphNet 详情

| 问题 | 回答 |
|------|------|
| **代码是否可用？** | **是**，已开源在 PhysicsNeMo `examples/additive_manufacturing/sintering_physics/` |
| **模型权重是否可用？** | **部分**，仅示例权重，HP 生产模型未开源 |
| **数据格式** | TFRecord 格式，包含体素位置 + 粒子类型 + 位移历史 + 温度序列 |
| **能否重训练为 FDM/LPBF？** | **理论可行但工程量大**：(1) 需要替换物理模型（烧结→热力学/相变）(2) 需要新的训练数据（FEM 仿真结果）(3) MeshGraphNet 架构本身是通用的，可复用 |

**重训练关键挑战**：
- 烧结物理 vs LPBF 物理完全不同（缓慢收缩 vs 快速熔化/凝固）
- 时间尺度差异巨大（烧结数小时 vs LPBF 微秒级）
- 需要大量 FEM 仿真数据作为 ground truth
- 建议：直接用 PhysicsNeMo 的 MeshGraphNet 模块从零训练 LPBF 模型

### 2.3 部署指南

#### 2.3.1 安装步骤

```bash
# Step 1: 创建环境
conda create -n physicsnemo python=3.10
conda activate physicsnemo

# Step 2: 安装 PyTorch（确保 CUDA 匹配）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# Step 3: 安装 PhysicsNeMo
pip install "nvidia-physicsnemo[cu12,nn-extras]"

# Step 4: 安装 AM 示例额外依赖
pip install torch-scatter torch-geometric tensorflow>=2.15 pyvista wandb

# Step 5: 克隆示例代码
git clone https://github.com/NVIDIA/physicsnemo.git
cd physicsnemo/examples/additive_manufacturing/sintering_physics

# Step 6: 准备数据
python data_process/rawdata2tfrecord.py  # 需要原始仿真数据

# Step 7: 训练
# 修改 conf/config.yaml: mode="train"
python train.py

# Step 8: 评估
# 修改 conf/config.yaml: mode="eval_rollout", eval_split="test", batch_size=1
python train.py

# Step 9: 推理
# 修改 conf/config.yaml: mode="rollout", eval_split="inference"
python inference.py

# Step 10: 可视化
python render_rollout.py
```

#### 2.3.2 资源需求

| 场景 | GPU | VRAM | 预估时间 |
|------|-----|------|----------|
| 训练（小模型） | 1x V100/A100 | 16GB | 数小时~1天 |
| 训练（大规模） | 4x A100 | 80GB/卡 | 数天 |
| 推理 | 1x RTX 3060+ | 8GB | **数秒** |
| 推理（笔记本） | NVIDIA 独显 | 6GB+ | 数十秒 |

### 2.4 验证方法

#### 2.4.1 GNN 代理模型评估流程

```
1. 准备 ground truth: FEM 仿真结果（节点位移场）
2. 数据划分: train/val/test = 5:1:1 (按几何体划分，非随机)
3. 训练 GNN 代理模型
4. 评估指标:
   - 单步 mean deviation (μm)
   - 完整周期 mean deviation (mm)
   - 最大节点误差 (%)
   - 推理速度 vs FEM 速度 (加速比)
5. 对比基线:
   - 物理仿真 (FEM) — 精度上限
   - 简化解析解 — 精度下限
```

#### 2.4.2 HP Virtual Foundry 的已证实精度

| 指标 | 值 | 测试零件 |
|------|-----|----------|
| 单步平均偏差 | **0.7μm** | 63mm 测试件 |
| 完整周期平均偏差 | **0.3mm** | 63mm 测试件（~4h 物理烧结） |
| 最大节点误差 | **<2%** | — |
| 推理时间 | **数秒** | vs 物理仿真数小时 |

### 2.5 综合评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **框架质量** | ★★★★★ | NVIDIA 官方维护，企业级质量 |
| **AM 示例完整度** | ★★★★☆ | 完整流水线但训练数据有限 |
| **安装易用性** | ★★★★★ | pip install 一行搞定 |
| **CADPilot 适配性** | ★★★☆☆ | 需要大量 FEM 数据和物理建模工作 |
| **许可合规** | ★★★★★ | Apache 2.0 |
| **文档质量** | ★★★★☆ | 官方文档 + 博客 + 教程 |

### 2.6 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 缺少 LPBF/FDM 训练数据 | 高 | 阻塞 | 先用开源 FEM 仿真生成合成数据 |
| 从烧结迁移到其他 AM 工艺工程量大 | 高 | 中 | 仅复用 MeshGraphNet 架构，不复用烧结逻辑 |
| 模型精度不满足工程需求 | 中 | 高 | 对比 FEM 基线，设置精度阈值 |
| TFRecord 格式与 CADPilot 不兼容 | 低 | 低 | 预处理脚本已提供 |

---

## Task 3: CMU ThermalControlLPBF-DRL

> Carnegie Mellon University BaratiLab, 无明确许可
> GitHub: [BaratiLab/ThermalControlLPBF-DRL](https://github.com/BaratiLab/ThermalControlLPBF-DRL)
> 论文: "Thermal Control of Laser Powder Bed Fusion using Deep Reinforcement Learning"

### 3.1 代码质量分析

#### 3.1.1 代码结构

```
ThermalControlLPBF-DRL/
├── EagarTsaiModel.py           # RUSLS 热模型核心
├── power_square_gym.py         # Gym 环境: 功率控制 + 方形扫描路径
├── power_triangle_gym.py       # Gym 环境: 功率控制 + 三角扫描路径
├── velocity_square_gym.py      # Gym 环境: 速度控制 + 方形扫描路径
├── velocity_triangle_gym.py    # Gym 环境: 速度控制 + 三角扫描路径
├── RL_learn_square.py          # PPO 训练脚本（方形路径）
├── RL_learn_triangle.py        # PPO 训练脚本（三角路径）
├── evaluate_learned_policy.py  # 策略评估
├── test_eagar_tsai_model.py    # 热模型测试
├── pretrained_models/          # 预训练模型（4 组）
├── figures/                    # 可视化素材
└── requirements.txt            # 依赖列表
```

#### 3.1.2 代码质量评估

| 维度 | 评分 | 说明 |
|------|------|------|
| **代码结构** | ★★★☆☆ | 单层目录，无模块化，但文件命名清晰 |
| **文档质量** | ★★★☆☆ | README 覆盖基本用法，但缺少架构说明 |
| **代码注释** | ★★☆☆☆ | 关键物理模型缺少详细注释 |
| **测试覆盖** | ★★☆☆☆ | 仅 1 个测试文件（test_eagar_tsai_model.py） |
| **可维护性** | ★★☆☆☆ | 4 个 gym 文件大量重复代码 |

#### 3.1.3 依赖过时问题

| 依赖 | 项目版本 | 最新版本 | 过时程度 |
|------|----------|----------|----------|
| `gym` | 0.17.3 | gymnasium 1.0+ | **极度过时**（gym 已更名为 gymnasium） |
| `torch` | 1.5.0 | 2.5+ | **极度过时**（5 年前版本） |
| `stable_baselines3` | 0.7.0 | 2.4+ | **极度过时**（SB3 已大幅重构） |
| `scikit-image` | 0.19.3 | 0.24+ | 中度过时 |

**能否在现代 Python/PyTorch 上运行？**

- **直接运行**：几乎不可能。gym 0.17 与 gymnasium 接口不兼容，SB3 0.7 的 PPO 接口已大改
- **迁移工作量**：约 1~2 天
  1. `gym` → `gymnasium`（API 签名变更：`step()` 返回值从 4 元组变 5 元组）
  2. `stable_baselines3` 0.7 → 2.x（PPO 参数名和回调接口变更）
  3. `torch` 1.5 → 2.x（基本兼容，少量 deprecated API）

### 3.2 RUSLS 热模型

#### 3.2.1 RUSLS 是什么

**RUSLS = Repeated Usage of Stored Line Solutions**（重复使用存储线解法）

- 出自 Wolfer et al. (2019) "Fast solution strategy for transient heat conduction for arbitrary scan paths in additive manufacturing"
- 基于 **Rosenthal 方程**（移动点热源的解析解）的改进方法
- 核心思想：将激光扫描路径离散为线段，预计算并存储每段的热响应（线解），通过叠加组合快速求解任意路径的瞬态温度场

#### 3.2.2 与精确解的对比

| 方法 | 精度 | 速度 | 适用场景 |
|------|------|------|----------|
| **FEM 仿真** | ★★★★★ | 极慢（小时~天） | 最终验证 |
| **RUSLS** | ★★★☆☆ | 快（秒~分钟） | RL 环境、快速估算 |
| **Rosenthal 解析解** | ★★☆☆☆ | 最快 | 粗估 |

**RUSLS 局限性**：
- 假设半无限域（忽略零件几何约束）
- 不考虑相变潜热
- 不模拟对流和辐射散热
- 对多层堆积的累积热效应建模有限
- 适合作为 RL 训练的"快速环境"，但不适合替代 FEM 做最终验证

#### 3.2.3 能否适配 CADPilot？

| 适用性 | 评估 |
|--------|------|
| 作为 RL 环境 | ★★★★☆ 可直接复用 RUSLS 做快速热场估算 |
| 作为精确热模型 | ★☆☆☆☆ 精度不足，不可替代 FEM |
| 扩展到 FDM | ★★★☆☆ Rosenthal 方程对 FDM 也近似适用，但需调整参数 |
| 扩展到 Metal AM | ★★★★☆ LPBF 就是主要目标场景 |

### 3.3 PPO Agent 详情

#### 3.3.1 State / Action / Reward 设计

基于仓库中 gym 环境文件的分析：

| 组件 | 设计 |
|------|------|
| **State** | 当前熔池温度场（从 RUSLS 模型获取）+ 当前扫描位置 + 历史控制参数 |
| **Action** | 连续值：激光功率（power_xxx_gym）或扫描速度（velocity_xxx_gym） |
| **Reward** | 负的温度偏差：惩罚熔池深度偏离目标值的程度 |
| **Episode** | 一条完整扫描路径（方形水平交叉影线 or 三角同心路径） |

#### 3.3.2 Agent 学到了什么

PPO Agent 学习的是 **自适应控制策略**：

- 在扫描路径的不同位置（转角、直线段、边缘区域）自动调节激光功率或扫描速度
- 目标：维持一致的熔池深度，避免过热（球化/裂纹）或欠热（未熔合）
- 优于传统 PID 控制器——因为 RL 可以学习非线性的前馈补偿

#### 3.3.3 训练收敛行为

- 4 种组合（2 路径 × 2 参数）各需独立训练
- 预训练模型已提供在 `pretrained_models/` 目录
- 收敛通常需要 ~100K~500K 步（具体未文档化）
- 通过 TensorBoard 监控训练曲线

### 3.4 可复现性评估

| 维度 | 评分 | 说明 |
|------|------|------|
| **开箱即用** | ★☆☆☆☆ | 依赖极度过时，不能直接 pip install |
| **预训练模型** | ★★★★☆ | 4 组预训练模型已提供 |
| **数据可用性** | ★★★★★ | 无需外部数据，RUSLS 环境自生成 |
| **论文可追溯** | ★★★★☆ | 论文已发表，方法清晰 |
| **社区维护** | ★☆☆☆☆ | 无近期更新，无 maintainer 回应 |

### 3.5 部署指南

#### 3.5.1 方式 A：使用原始版本（不推荐，仅考古）

```bash
# 创建隔离环境（Python 3.8）
conda create -n lpbf-drl python=3.8
conda activate lpbf-drl

# 克隆
git clone https://github.com/BaratiLab/ThermalControlLPBF-DRL.git
cd ThermalControlLPBF-DRL

# 安装依赖
pip install gym==0.17.3
pip install torch==1.5.0
pip install stable_baselines3==0.7.0
pip install scikit-image==0.19.3
pip install tensorboard

# 训练（方形路径 + 功率控制）
python RL_learn_square.py --param power

# 训练（三角路径 + 速度控制）
python RL_learn_triangle.py --param velocity

# 评估预训练模型
python evaluate_learned_policy.py
```

#### 3.5.2 方式 B：现代化迁移（推荐）

```bash
# 创建现代环境
conda create -n lpbf-drl-modern python=3.10
conda activate lpbf-drl-modern

# 安装现代依赖
pip install gymnasium>=0.29
pip install torch>=2.0
pip install stable-baselines3>=2.0
pip install scikit-image>=0.22
pip install tensorboard

# 克隆并修改
git clone https://github.com/BaratiLab/ThermalControlLPBF-DRL.git
cd ThermalControlLPBF-DRL

# 需要修改的文件:
# 1. *_gym.py: gym.Env → gymnasium.Env
#    - step() 返回值: (obs, reward, done, info) → (obs, reward, terminated, truncated, info)
#    - reset() 返回值: obs → (obs, info)
# 2. RL_learn_*.py: stable_baselines3 PPO 参数名更新
#    - n_steps, batch_size 等参数名可能变化
# 3. EagarTsaiModel.py: 基本无需修改（纯 numpy 计算）
```

#### 3.5.3 训练时间预估

| 配置 | GPU | 预估时间 |
|------|-----|----------|
| 方形+功率 | CPU | 2~4 小时 |
| 方形+功率 | GPU (RTX 3060) | 30~60 分钟 |
| 全部 4 配置 | GPU | 2~4 小时 |

注：RUSLS 热模型在 CPU 上运行，GPU 仅加速 PPO 网络前向/反向传播。

#### 3.5.4 结果可视化

```bash
# TensorBoard 训练曲线
tensorboard --logdir training_checkpoints/

# 评估并生成热场动画
python evaluate_learned_policy.py
# 输出: 温度场 + 控制参数随时间变化的动画
```

### 3.6 综合评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **学术价值** | ★★★★☆ | 首个开源的 AM RL 热控制代码 |
| **代码质量** | ★★☆☆☆ | 单层结构、无模块化、依赖过时 |
| **部署难度** | ★★★☆☆ | 需迁移工作，但 RUSLS 核心稳定 |
| **CADPilot 适配性** | ★★★☆☆ | RUSLS 可复用，RL 框架需重写 |
| **许可风险** | ★★☆☆☆ | **无明确许可**，商用需联系作者 |

### 3.7 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 依赖过时无法运行 | 高 | 阻塞 | 方式 B 现代化迁移 |
| 无许可证 | 高 | 法律风险 | 联系 BaratiLab 获取许可 |
| RUSLS 精度不足 | 中 | 中 | 仅用作 RL 环境，不做最终验证 |
| 无 maintainer | 高 | 中 | Fork + 自维护 |

---

## Task 4: 3D-ADAM 数据集

> 创建者: Paul McHard, CC-BY-NC-SA-4.0
> HuggingFace: [pmchard/3D-ADAM](https://huggingface.co/datasets/pmchard/3D-ADAM)
> 论文: [arXiv:2507.07838](https://arxiv.org/abs/2507.07838)
> DOI: 10.57967/hf/5526

### 4.1 数据结构

#### 4.1.1 总体规模

| 项目 | 数值 |
|------|------|
| 总扫描数 | **14,120** |
| 唯一零件数 | **217** |
| 零件类别 | **29** |
| 缺陷标注数 | **27,346** |
| 机械特征标注数 | **27,346** |
| 传感器数 | **4** |
| 数据大小 | ~5GB (Parquet 格式) |

#### 4.1.2 传感器规格

| 传感器 | 制造商 | 分辨率 | 最优距离 | 精度 |
|--------|--------|--------|----------|------|
| LSR-L | MechMind | 2048×1536 | 1500-3000mm | 0.5-1.0mm |
| Nano | MechMind | 1280×1024 | 300-600mm | **0.1mm** |
| RealSense D455 | Intel | 1280×720 | 600-6000mm | 80mm |
| Zed2i | Stereolabs | 1920×1080 | 300-1200mm | 30mm |

每传感器 ~3,048 扫描，均匀分布。

#### 4.1.3 图像类型

- **6 通道图像**：RGB (3ch) + XYZ 深度坐标 (3ch)
- **点云**：PLY 格式，RGB + XYZ 1:1 对应
- **格式**：原始为 imagefolder，自动转为 Parquet

### 4.2 缺陷类别（12 类）

| # | 缺陷类型 | 英文 | AM 相关性 |
|---|----------|------|-----------|
| 1 | 切割 | Cuts | 中 |
| 2 | 鼓包 | Bulges | 高（过挤出） |
| 3 | 孔洞 | Holes | 高 |
| 4 | 间隙 | Gaps | 高（层间缺陷） |
| 5 | 毛刺 | Burrs | 中 |
| 6 | 裂纹 | Cracks | 高 |
| 7 | 划痕 | Scratches | 低 |
| 8 | 印记 | Marks | 低 |
| 9 | 翘曲 | Warping | 高（核心 AM 问题） |
| 10 | 粗糙度 | Roughness | 高 |
| 11 | 过挤出 | Over-extrusion | 高 |
| 12 | 欠挤出 | Under-extrusion | 高 |

### 4.3 机械特征类别（16 类）

| # | 特征 | 说明 |
|---|------|------|
| 1 | 面 (Faces) | 平面特征 |
| 2 | 边 (Edges) | 棱边 |
| 3 | 内圆角 (Internal Fillets) | 内凹圆角 |
| 4 | 外圆角 (External Fillets) | 外凸圆角 |
| 5 | 内倒角 (Internal Chamfers) | 内凹倒角 |
| 6 | 外倒角 (External Chamfers) | 外凸倒角 |
| 7 | 孔 (Holes) | 通孔/盲孔 |
| 8 | 槽 (Kerfs) | 切槽 |
| 9 | 锥度 (Tapers) | 渐变特征 |
| 10 | 凹陷 (Indents) | 凹槽 |
| 11 | 沉头孔 (Counterbores) | 阶梯孔 |
| 12 | 锪孔 (Countersinks) | 锥形沉头孔 |
| 13 | 直齿轮齿 (Spur Gear Teeth) | — |
| 14 | 齿条齿 (Rack Gear Teeth) | — |
| 15 | 螺旋齿 (Spiral Gear Teeth) | — |
| 16 | 斜齿轮齿 (Helical Gear Teeth) | CW/CCW |

### 4.4 标注格式

- **零件分割掩码**：像素级分割
- **机械特征**：边界框 + 类别标签
- **缺陷**：分割掩码 + 类别标签
- **标注工具**：半自动（Cutie-based）+ 人工校验
- **多传感器一致性**：单应性变换 (Homography) 对齐

### 4.5 基线模型

#### 4.5.1 论文中评估的模型

**2D 异常检测**：
| 模型 | 类型 | 说明 |
|------|------|------|
| PatchCore | 基线 | 经典异常检测 |
| UniNet | CVPR 2025 | 对比学习 + 特征选择 |
| DinoMaly | CVPR 2025 | 编码器-解码器，预训练模型驱动 |

**3D 异常检测**：
| 模型 | 类型 | 说明 |
|------|------|------|
| CFA | 基线 | — |
| PaDiM | 基线 | — |
| PatchCore-3D | 基线 | 3D 扩展 |
| TransFusion | SOTA | — |
| 3DSR | SOTA | — |
| GLFM | SOTA | **3D-ADAM 上表现最好的 3D 模型** |

#### 4.5.2 关键发现

- 2D 模型在 Image AUROC 和 Pixel AUROC 上表现一致
- **3D 模型在 3D-ADAM 上性能显著下降**（vs MVTec3D-AD 上的表现）
- 3D-ADAM 的工业环境真实性（光照变化、位姿变化、遮挡）构成显著更大的挑战
- **GLFM 是 3D 检测中表现最好的模型**，但仍远低于在 MVTec3D-AD 上的精度

### 4.6 部署指南

#### 4.6.1 数据加载

```python
from datasets import load_dataset

# 方式 1: 完整加载
dataset = load_dataset("pmchard/3D-ADAM")

# 方式 2: 流式加载（推荐，避免全量下载）
dataset = load_dataset("pmchard/3D-ADAM", streaming=True)

# 方式 3: 单传感器子集（用于 anomalib）
dataset_anomalib = load_dataset("pmchard/3D-ADAM_anomalib")
```

#### 4.6.2 数据可视化

```python
import matplotlib.pyplot as plt
from datasets import load_dataset

# 加载数据
ds = load_dataset("pmchard/3D-ADAM", split="train", streaming=True)

# 可视化样本
sample = next(iter(ds))
image = sample["image"]  # PIL Image
plt.figure(figsize=(10, 8))
plt.imshow(image)
plt.title("3D-ADAM Sample")
plt.axis("off")
plt.show()
```

#### 4.6.3 使用 anomalib 运行基线

```bash
# 安装
pip install anomalib
# 或使用 3D-ADAM fork
git clone https://github.com/PaulMcHard/3D-ADAM_anomalib.git
cd 3D-ADAM_anomalib
pip install -e .

# 训练 PatchCore
anomalib train --model Patchcore --data anomalib.data.MVTecAD  # 替换为 3D-ADAM config

# 评估
anomalib test --model Patchcore --data anomalib.data.MVTecAD
```

### 4.7 验证方法：建议的基线实验

#### 4.7.1 实验 1：2D 缺陷分类（快速验证）

```python
# 使用预训练 ResNet 做缺陷分类 fine-tune
# 预计训练时间: 1-2 小时 (single GPU)
# 目标指标: Image AUROC > 0.80

from torchvision.models import resnet50
import torch.nn as nn

model = resnet50(pretrained=True)
model.fc = nn.Linear(2048, 12)  # 12 defect classes
# ... training loop with 3D-ADAM
```

#### 4.7.2 实验 2：异常检测 (anomalib)

```python
# 使用 anomalib 的 PatchCore 模型
# 预计训练时间: 30 分钟 (无需训练，feature extraction only)
# 目标指标:
#   - Image AUROC > 0.75
#   - Pixel AUPRO > 0.50

from anomalib.data import MVTecAD  # 替换为 3D-ADAM
from anomalib.models import Patchcore
from anomalib.engine import Engine

datamodule = ...  # 3D-ADAM DataModule
model = Patchcore()
engine = Engine()
engine.fit(datamodule=datamodule, model=model)
predictions = engine.predict(datamodule=datamodule, model=model)
```

#### 4.7.3 实验 3：YOLOv8 缺陷检测（建议替代 YOLOv5）

```bash
# YOLOv8 更适合作为 baseline
pip install ultralytics

# 转换 3D-ADAM 标注为 YOLO 格式
# ... 需要自行编写转换脚本

# 训练
yolo detect train data=3dadam.yaml model=yolov8n.pt epochs=100 imgsz=640

# 评估
yolo detect val data=3dadam.yaml model=runs/detect/train/weights/best.pt
```

### 4.8 综合评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **数据质量** | ★★★★★ | 工业级扫描、4 传感器、严格标注 |
| **规模** | ★★★★☆ | 14K 扫描、27K 标注，AM 领域最大 |
| **标注丰富度** | ★★★★★ | 12 缺陷类 + 16 机械特征类 |
| **CADPilot 适配性** | ★★★★☆ | 缺陷检测直接对应 printability_check |
| **许可风险** | ★★★☆☆ | CC-BY-NC-SA-4.0：**非商业限制** |
| **易用性** | ★★★★☆ | HuggingFace 一行加载 + anomalib 集成 |

### 4.9 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| NC 许可限制商用 | 确定 | 高 | 仅研究使用，商用需联系作者获取商业许可 |
| 数据量下载耗时 | 低 | 低 | 流式加载或 anomalib 子集 |
| 3D 模型效果差 | 高 | 中 | 先用 2D 模型做基线，3D 模型作为研究方向 |
| 缺少 FDM 专属缺陷 | 中 | 中 | 数据来自 FDM 打印，但部分缺陷类适用多种 AM |

---

## 综合评估

### 项目对比矩阵

| 维度 | TRELLIS | PhysicsNeMo | CMU DRL | 3D-ADAM |
|------|---------|-------------|---------|---------|
| **综合评分** | ★★★★☆ | ★★★★☆ | ★★★☆☆ | ★★★★☆ |
| **许可** | MIT ✅ | Apache 2.0 ✅ | **无许可** ⚠️ | CC-BY-NC-SA ⚠️ |
| **安装难度** | 难（CUDA 编译） | 简（pip） | 难（过时依赖） | 简（HF 加载） |
| **CADPilot 节点** | generate_raw_mesh | （未直接对应） | （研究储备） | printability_check |
| **投入产出比** | 高 | 中 | 低 | 高 |
| **技术成熟度** | 高 | 高 | 低 | 中 |
| **维护活跃度** | 高 | 高 | 低 | 中 |

### CADPilot 集成优先级

```
P0（立即可用）:
  └─ TRELLIS → generate_raw_mesh strategy "trellis"
     - GLB 输出 → trimesh → mesh_healer 完整链路
     - 需部署 GPU 服务（A100 推荐）

P1（短期可用）:
  └─ 3D-ADAM → printability_check 训练数据
     - anomalib 集成做缺陷检测 baseline
     - 注意 NC 许可限制

P2（中期研究）:
  └─ PhysicsNeMo MeshGraphNet → AM 仿真代理模型
     - 需大量 FEM 数据生成
     - 长期价值：数字孪生 + 实时变形预测

P3（长期储备）:
  └─ CMU DRL RUSLS → RL 热控制
     - 需现代化重写
     - 许可问题需先解决
```

### 关键行动建议

1. **TRELLIS 优先部署**：作为 generate_raw_mesh 的 "trellis" 策略，直接对接现有 mesh_healer 节点。建议用 Docker 打包部署，绕过 CUDA 编译问题。

2. **3D-ADAM 快速验证**：用 anomalib + PatchCore 跑出 baseline，验证缺陷检测可行性。如果 Image AUROC > 0.8，可进入 printability_check 集成。

3. **PhysicsNeMo 做技术储备**：不急于集成，但建议跑通 sintering_physics 示例，理解 MeshGraphNet 训练流程，为未来自有 AM 仿真模型打基础。

4. **CMU DRL 仅参考**：RUSLS 热模型可作为参考实现学习，但不建议直接使用其代码。如需 RL 热控制，建议用现代框架（Gymnasium + SB3 2.x + PyTorch 2.x）重写。

---

## 参考资料

### TRELLIS
- [GitHub: microsoft/TRELLIS](https://github.com/microsoft/TRELLIS)
- [GitHub: microsoft/TRELLIS.2](https://github.com/microsoft/TRELLIS.2)
- [HuggingFace: microsoft/TRELLIS.2-4B](https://huggingface.co/microsoft/TRELLIS.2-4B)
- [项目主页: 3dtrellis.com](https://3dtrellis.com/)
- [论文: Structured 3D Latents for Scalable and Versatile 3D Generation (CVPR'25)](https://microsoft.github.io/TRELLIS/)
- [论文: Native and Compact Structured Latents for 3D Generation](https://microsoft.github.io/TRELLIS.2/)
- [VRAM Issue #24](https://github.com/microsoft/TRELLIS.2/issues/24)

### NVIDIA PhysicsNeMo
- [GitHub: NVIDIA/physicsnemo](https://github.com/NVIDIA/physicsnemo)
- [官方文档](https://docs.nvidia.com/physicsnemo/latest/index.html)
- [MeshGraphNet 教程](https://docs.nvidia.com/physicsnemo/latest/user-guide/model_architecture/meshgraphnet.html)
- [Virtual Foundry GraphNet 示例](https://docs.nvidia.com/physicsnemo/latest/physicsnemo/examples/additive_manufacturing/sintering_physics/README.html)
- [HP 3D Printing 合作博客](https://developer.nvidia.com/blog/spotlight-hp-3d-printing-and-nvidia-physicsnemo-collaborate-on-open-source-manufacturing-digital-twin/)
- [GNN for AM 博客](https://developer.nvidia.com/blog/develop-physics-informed-machine-learning-models-with-graph-neural-networks/)
- [PyPI: nvidia-physicsnemo](https://pypi.org/project/nvidia-physicsnemo/)
- [论文: Virtual Foundry Graphnet (arXiv:2404.11753)](https://arxiv.org/abs/2404.11753)

### CMU ThermalControlLPBF-DRL
- [GitHub: BaratiLab/ThermalControlLPBF-DRL](https://github.com/BaratiLab/ThermalControlLPBF-DRL)
- [CMU 项目页](https://engineering.cmu.edu/next/research/project-details/deep-reinforcement-learning.html)
- [Wolfer et al. (2019) RUSLS 论文](https://www.sciencedirect.com/science/article/abs/pii/S221486042300550X)

### 3D-ADAM
- [HuggingFace: pmchard/3D-ADAM](https://huggingface.co/datasets/pmchard/3D-ADAM)
- [论文: arXiv:2507.07838](https://arxiv.org/abs/2507.07838)
- [anomalib Fork: PaulMcHard/3D-ADAM_anomalib](https://github.com/PaulMcHard/3D-ADAM_anomalib)
- [anomalib 官方](https://github.com/open-edge-platform/anomalib)
