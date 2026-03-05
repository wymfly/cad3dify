# 工业金属 3D 打印中的 AI 模型深度调研：强化学习、神经网络与开源生态

> 调研日期：2026-03-03
> 基于 end-to-end-architecture 前期调研的延伸，聚焦工业金属增材制造（Metal AM）领域

---

## 目录

1. [强化学习（RL）在金属 AM 中的应用](#一强化学习rl在金属-am-中的应用)
2. [神经网络与深度学习](#二神经网络与深度学习)
3. [代理模型与数字孪生](#三代理模型与数字孪生)
4. [HuggingFace 开源模型目录](#四huggingface-开源模型目录)
5. [HuggingFace 开源数据集目录](#五huggingface-开源数据集目录)
6. [与 CADPilot 的关联分析](#六与-cadpilot-的关联分析)
7. [关键趋势与战略建议](#七关键趋势与战略建议)

---

## 一、强化学习（RL）在金属 AM 中的应用

RL 通过"试错-奖励"机制学习最优控制策略，特别适合 AM 中的实时自适应控制和多变量耦合优化。

### 1.1 LPBF/SLM 热场控制与工艺优化

| 项目 | 年份 | RL 算法 | 问题 | 关键结果 | 开源 |
|------|------|---------|------|----------|------|
| **ThermalControlLPBF-DRL** (CMU BaratiLab) | 2021 | **PPO** | LPBF 熔池深度一致性控制 | 优于 PID 控制器的温度轮廓控制 | [GitHub](https://github.com/BaratiLab/ThermalControlLPBF-DRL) (40★) |
| Multi-layer SLM Control | 2024 | **AWAC** | SLM 多层平均层温度控制 | 首次展示完整 3D 零件的 RL 过程控制 | 未开源 |
| AM Process Parameter Optimization | 2023 | **Q-learning** | 最优激光功率+扫描速度组合 | 维持稳态熔池深度 | 未开源 |

### 1.2 扫描路径规划与扫描策略优化

| 项目 | 年份 | RL 算法 | 问题 | 关键结果 | 开源 |
|------|------|---------|------|----------|------|
| **DRL Toolpath Generation** | 2024 | **DQN** | LPBF 扫描路径→温度场均匀分布 | 最大变形比 zigzag 减少 **47%**，比棋盘格减少 **29%** | 未开源 |
| **Reinforced Scan** | 2025 | 分层 RL | Ti-6Al-4V 最优扫描序列 | 平均残余应力降至 **309 MPa**（vs 顺序法 327 MPa） | 未开源 |
| Phase-Field + DRL | 2025 | Deep RL + 3D U-Net | 优化扫描路径获得目标微观结构（等轴晶粒） | 比传统方法加速 **2 个数量级** | 未开源 |

### 1.3 DED/WAAM 工艺优化

| 项目 | 年份 | RL 算法 | 问题 | 关键结果 | 开源 |
|------|------|---------|------|----------|------|
| DED Laser Power Planning | 2024 | **DQN** | 从 FE 模型学习激光功率控制 | 无需物理传感器实现功率规划 | 未开源 |
| DED Nickel Alloy Optimization | 2024 | Deep RL | 镍基合金 DED 均匀温度分布 | 降低计算成本保持仿真精度 | 未开源 |
| **RLPlanner** (WAAM) | 2023 | **PPO** + SLSQP | WAAM 薄壁结构路径规划 | 多种几何形状自动最优路径 | [项目页](https://www.janpetrik.com/portfolio-RLPlanner.html) |
| WAAM Optimal Control | 2023 | **DDPG** | WAAM 焊接参数调节 | 先进 RL 在 WAAM 的应用验证 | 未开源 |

### 1.4 原位缺陷修正与闭环控制

| 项目 | 年份 | RL 算法 | 问题 | 关键结果 | 开源 |
|------|------|---------|------|----------|------|
| Continual G-learning | 2022 | **Continual G-learning** | AM 在线缺陷缓解 | 整合离线+在线先验知识 | 未开源 |
| WAAM RL Monitor | 2025 | **Tabular Q-learning** | 视觉 WAAM 监控+自适应调参 | 自主从过程扰动恢复 | 未开源 |
| **Uncertainty-aware RL** | 2025 | Deep Q-learning | 挤出 AM 实时质量保证 | **零样本迁移**（sim-to-real） | 未开源 |
| Robotic WAAM Scan-n-Print | 2020 | **Model-Based RL** | 机器人 WAAM 闭环控制 | 涡轮叶片等复杂形状显著改进 | 未开源 |

### 1.5 构建方向与支撑优化

| 项目 | 年份 | RL 算法 | 问题 | 关键结果 | 开源 |
|------|------|---------|------|----------|------|
| **Learn to Rotate** | 2023 | Generalizable RL | 最小化支撑体积的构建方向 | 比随机搜索快 **2.62x ~ 229x** | 未开源 |

### 1.6 RL 算法选择总结

```
PPO ──────── LPBF 热控制、WAAM 路径规划（训练最稳定）
DQN ──────── 扫描路径生成、DED 功率规划（离散决策）
Q-learning ─ WAAM 在线控制、参数优化（简单有效）
DDPG ─────── WAAM 连续控制（连续动作空间）
AWAC ─────── SLM 多层控制（稳定性增强的 Actor-Critic）
```

### 1.7 RL 领域关键发现

1. **开源生态极薄弱**：仅 CMU BaratiLab 的 `ThermalControlLPBF-DRL` 提供完整可用代码
2. **HuggingFace 上无 RL 模型**：该领域 RL 模型完全不在 HF 生态中
3. **Sim-to-Real 是核心挑战**：多数研究依赖 FEM 仿真训练，少数（2025）实现零样本迁移
4. **微观结构控制是新前沿**：2025 年 DRL + 相场模型开始控制晶粒结构
5. **从 LPBF 向 DED/WAAM 扩展**：DED/WAAM 较低扫描速度更利于闭环控制

---

## 二、神经网络与深度学习

### 2.1 CNN/视觉模型：缺陷检测与过程监控

| 模型/架构 | 年份 | 问题 | 性能 | 开源 |
|-----------|------|------|------|------|
| **YOLOv5/v8** 缺陷检测 | 2025 | LPBF 孔隙/未熔合/飞溅实时检测 | mAP **95.7%**，精确率 94%，召回率 96% | 未公开 |
| **3D-CNN** 框架 | 2023 | 光电二极管信号→缺陷类型分类+体积分数预测 | CT 扫描验证通过 | 未公开 |
| **ResNet50/EfficientNetV2B0** | 2024 | LPBF 逐层缺陷分类 | 分类准确率 **99%+**；迁移学习 **94%** | 未公开 |
| **Vision Transformer (ViT)** + MAE | 2024 | DED 热成像熔池缺陷检测 | 准确率 **95.44% ~ 99.17%** | 未公开 |
| **U-Net** 缺陷分割 | 2023 | 原位红外/光学图像缺陷语义分割 | 广泛用于孔隙、飞溅、裂纹检测 | 未公开 |
| **PoreAnalyzer** | 2021 | LPBF 光学显微孔隙分析 | Python 框架，批量分析 | **开源** |
| metal-defect-detection | - | CNN+迁移学习金属缺陷检测 | - | [GitHub](https://github.com/maxkferg/metal-defect-detection) |

### 2.2 物理信息神经网络（PINNs）：热建模与熔池预测

| 模型 | 年份 | 架构 | 问题 | 关键创新 | 开源 |
|------|------|------|------|----------|------|
| **MeltpoolINR** | 2024-2025 | MLP + Fourier 特征编码 | 温度场、熔池几何+变化率预测 | 分辨率无关连续表征；等值面隐式表示熔池边界 | 未公开 |
| FEA-PINN | 2024 | FEA 规范化 PINN | LPBF 快速热场预测 | 稀疏数据显著提升精度 | 未公开 |
| **CNN-Transformer-GAN** | 2024 | 混合架构 | 熔池行为预测+监控图像生成 | 首次物理基础模型+深度生成模型结合 | 未公开 |
| PI Online Learning | 2024 | 物理信息在线学习框架 | 金属 AM 实时温度预测 | 首个 AM 专用物理信息在线学习 | 未公开 |
| **PINN 迁移学习** | 2025 | PINN 在线软传感器 | 多轨迹温度预测 | 预训练 PINN 快速适配新工艺 | 未公开 |

### 2.3 图神经网络（GNN）：拓扑优化与热建模

| 模型 | 年份 | 问题 | 关键创新 | 开源 |
|------|------|------|----------|------|
| GNN Topology Optimization | 2025 | AM 自支撑结构拓扑优化 | GNN 作为 FE 网格神经场 | 未公开 |
| **NVIDIA PhysicsNeMo + LGN** | 2024 | 格子结构动力学仿真 | MeshGraphNet 多尺度代理模型 | **Apache 2.0** [GitHub](https://github.com/NVIDIA/PhysicsNeMo) |
| **HP Virtual Foundry Graphnet** | 2025 | Metal Jet 金属烧结变形预测 | 体素级变形，**4h→秒级**，精度 0.3mm | **开源** via PhysicsNeMo |
| AM 知识图谱 + RED-GNN | 2024 | 激光 AM 工艺参数推荐 | 知识图谱推理 | 未公开 |
| GNN 几何无关热建模 | 2021 | 复杂几何体热响应 | 泛化到未见几何体 | 未公开 |
| Adaptnet 双 GNN | 2024 | CAD→网格生成+自适应 | Meshnet+Graphnet 双框架 | 未公开 |

### 2.4 生成模型：微观结构预测与逆设计

| 模型 | 年份 | 架构 | 问题 | 开源 |
|------|------|------|------|------|
| **Txt2Microstruct-Net** | 2024 | 双编码器 NN（CLIP 启发） | 文本→3D 材料微观结构 | [GitHub](https://github.com/xyzheng-ut/Txt2Microstruct-Net) |
| **MIND** (SIGGRAPH 2025) | 2025 | 潜在扩散 + Holoplane 混合表征 | 目标物理性能→超材料微观结构逆设计 | [GitHub](https://github.com/TimHsue/MIND) |
| DDPM 微观结构重建 | 2024 | 去噪扩散概率模型 | 2D/3D 随机复合材料重建 | 未公开 |
| HDGPN | 2023 | VAE + GAN 混合 | 金属 AM 任意工艺参数→孔隙形态预测 | 未公开 |
| GAN 多晶合金建模 | 2024 | GAN + DREAM.3D | AM 合金微观结构 SEVM | 晶粒尺寸精度 **92%** |

### 2.5 Transformer 模型：序列工艺数据

| 模型 | 年份 | 问题 | 关键创新 |
|------|------|------|----------|
| WAAM Transformer | 2025 | 基于热历史的位置相关力学性能预测 | 时空模型处理多轮廓热历史 |
| MMoTE | 2025 | 制造过程预测监控 | Transformer + 多任务学习 |
| ViT 熔池深度预测 | 2024 | 表面热图像→熔池深度等高线 | [BaratiLab HF 数据集](https://huggingface.co/baratilab/datasets) |
| AAT 异常检测 | 2024 | 智能制造异常检测 | 自适应对抗 Transformer |

### 2.6 LLM 多智能体系统

| 项目 | 年份 | 架构 | 关键结果 |
|------|------|------|----------|
| **LLM-3D Print** | 2024 | 分层多智能体 LLM | 监督 LLM 协调缺陷检测→信息收集→纠正执行；承载力提升 **1.3~5x** |

---

## 三、代理模型与数字孪生

### 3.1 神经算子代理模型（替代 FEM）

| 模型 | 年份 | 架构 | 加速比 | 精度 | 开源 |
|------|------|------|--------|------|------|
| **LP-FNO** | 2026 | Fourier Neural Operator | 比 FVM 快 **10 万倍** | 覆盖传导+键孔模式 | 未公开 |
| **DeepONet-GNN** | 2025 | DeepONet + 边缘感知双 GNN | 收敛快 **50%** | z 变形 RMSE **0.088mm** | PyTorch+PyG |
| Advanced DeepONet | 2024 | ResUNet DeepONet | 数量级加速 | 多材料多物理场 | 未公开 |
| **AM_DeepONet** (NCSA) | 2024 | Sequential DeepONet + GRU | - | 凝固+LDED 预测 | [GitHub](https://github.com/ncsa/AM_DeepONet) |
| PI-DeepONet | 2025 | DeepONet + PINN | - | 多轨迹温度 | 未公开 |
| FNO 温度演化 | 2024 | FNO | 超分辨率 | 网格无关 | 未公开 |
| **PINN 替代 FEM** | 2025 | PI-ML | 计算时间减少 **98.6%** | 超分辨率 | 未公开 |
| RNN 熔池预测 | 2025 | LSTM/Bi-LSTM/GRU | 数量级加速 | 峰温 R²=0.980 | 未公开 |
| DL 可打印性评估 | - | 深度学习代理 | **1000x** 加速 | 不损失精度 | 未公开 |

### 3.2 数字孪生框架

**核心范式演进：**
```
传统 FEM（小时级）→ PINN/FNO 代理模型（秒级）→ 边缘 AI 实时推理（毫秒级）
```

**闭环控制技术路线：**

| 技术路线 | 方法 | 响应时间 |
|---------|------|---------|
| 前馈 NN + 反馈优化 | NN 预测 + 实时参数调整 | 3 秒 |
| 多模态传感融合 | 热/光学/声学 + 深度学习 | 体积变化降低 10x |
| LSTM 熔池监控 | 时序预测 + 自适应控制 | 实时 |
| 基于图像的 ML | CNN + 计算机视觉 | 在线定位 |

**迁移学习解决领域偏移：**
- 源域→目标域精度从 86% 暴跌至 44%（无迁移学习）
- 帕累托前沿源数据选择（2024）
- **MAADM**：VAE 跨材料域适应
- PINN 迁移学习：快速适配新工艺参数

### 3.3 各技术路线成熟度

| 技术路线 | 成熟度 | 加速比 | 典型精度 | 泛化能力 |
|---------|--------|--------|---------|---------|
| PINN 温度场 | ★★★★ | 50-100x | R²>0.95 | 可迁移学习 |
| FNO 热场 | ★★★☆ | 100-10万x | 高 | 超分辨率，网格无关 |
| DeepONet | ★★★☆ | 1000x+ | RMSE~0.1mm | 可变几何 |
| GNN/MeshGraphNet | ★★★ | 1000x+ | 0.3mm (HP) | 新几何泛化 |
| LSTM/GRU | ★★★★ | 实时 | R²=0.98 | 限同类工艺 |
| U-Net 缺陷检测 | ★★★★ | 实时 | 高 Dice | 需再训练 |
| VAE 异常检测 | ★★★ | 实时 | >80% | 需域适应 |

### 3.4 开源框架

| 框架 | 机构 | 许可 | 核心能力 | 链接 |
|------|------|------|----------|------|
| **NVIDIA PhysicsNeMo** | NVIDIA | Apache 2.0 | FNO/DeepONet/MeshGraphNet/PINN 全栈 | [GitHub](https://github.com/NVIDIA/physicsnemo) |
| **AM_DeepONet** | NCSA/UIUC | - | AM 多物理场 DeepONet | [GitHub](https://github.com/ncsa/AM_DeepONet) |
| **GeomDeepONet** | NCSA/UIUC | - | 不同 3D 几何的预测 | [GitHub](https://github.com/ncsa/GeomDeepONet) |
| ml-iter-additive | Northwestern | - | 迭代 ML 预测 AM 温度场 | [GitHub](https://github.com/NU-CUCIS/ml-iter-additive) |
| Deep_Learning_for_Manufacturing | - | - | 贝叶斯 DL + DRL 制造质量控制 | [GitHub](https://github.com/sumitsinha/Deep_Learning_for_Manufacturing) |

### 3.5 工业应用

| 公司 | 产品/方案 | 技术 |
|------|----------|------|
| **HP** | Virtual Foundry Graphnet | GNN 金属烧结变形预测（**开源**） |
| **EOS** | EOSTATE / Smart Monitoring | CNN 粉床缺陷检测 + AI 排布优化 |
| **Nikon SLM Solutions** | + Interspectral 集成质量保证 | 可视化分析 + 质量控制 |
| **Velo3D** | Assure + Flow + Sapphire | 集成计量、软件、过程控制 |
| **Sigma Additive** | PrintRite3D IPQA | 熔池过程控制、异常检测 |
| **Materialise** | QPC + Layer Image Analysis | AI 秒级逐层错误定位 |
| **Additive Assurance** | AMiRIS | 无需改打印机的质量控制 |

---

## 四、HuggingFace 开源模型目录

### 4.1 3D 生成模型

| 模型 | 机构 | 参数 | 许可证 | 月下载 | 功能 | 与 AM 关联 |
|------|------|------|--------|--------|------|-----------|
| [TRELLIS-image-large](https://huggingface.co/microsoft/TRELLIS-image-large) | Microsoft | 2-4B | MIT | 2.6M | 图→3D 纹理网格 + PBR | ★★★★ 尖锐特征/非流形 |
| [Hunyuan3D-2](https://huggingface.co/tencent/Hunyuan3D-2) | Tencent | 大规模 DiT | Community | 75K | 形状生成+纹理合成 | ★★★ 概念模型 |
| [TripoSR](https://huggingface.co/stabilityai/TripoSR) | Stability AI | 1.68GB | MIT | 62K | 单图快速 3D 重建 | ★★★ 快速原型 |
| [SPAR3D](https://huggingface.co/stabilityai/stable-point-aware-3d) | Stability AI | 2B | Community(<$1M 免费商用) | 1.2K | <1s 纹理 UV mesh | ★★★☆ |
| [Make-A-Shape](https://huggingface.co/ADSKAILab/Make-A-Shape-single-view-20m) | Autodesk | - | Non-Commercial | - | 训练含 ABC+Fusion360 | ★★★★ 工程数据 |
| [CraftsMan3D](https://huggingface.co/craftsman3d/craftsman) | - | - | Apache 2.0 | - | 照片→GLB + remesh | ★★★ |

### 4.2 Mesh 处理模型

| 模型 | 参数 | 许可证 | 功能 | 与 AM 关联 |
|------|------|--------|------|-----------|
| [MeshAnythingV2](https://huggingface.co/Yiwen-ntu/MeshAnythingV2) | 500M | MIT | 稠密 mesh→低面数 Artist mesh (<1600面) | ★★★★ mesh 修复管线 |
| [LLaMA-Mesh](https://huggingface.co/Zhengyi/LLaMA-Mesh) | 8B | NSCLv1(非商业) | 文本对话式 3D mesh 生成 | ★★ 面数限制 |
| [MeshGPT](https://huggingface.co/MarcusLoren/MeshGPT-preview) | 234M | 研究用途 | 文本→三角 mesh | ★★ 精度不足 |

### 4.3 CAD 生成模型（极高关联度）

| 模型 | 机构 | 参数 | 许可证 | 功能 | 与 CADPilot 关联 |
|------|------|------|--------|------|-----------------|
| [**CADFusion**](https://huggingface.co/microsoft/CADFusion) | Microsoft | 8B (Llama-3 LoRA) | **MIT** | 文本→参数化 CAD 序列 + VLM 反馈 | ★★★★★ |
| [**CAD-Editor**](https://huggingface.co/microsoft/CAD-Editor) | Microsoft | 8B (LLaMA-3 LoRA) | **MIT** | 自然语言编辑 CAD 模型（有效率 95.6%） | ★★★★★ |
| [CAD-Recode](https://huggingface.co/filapro/cad-recode) | - | 2B (Qwen2-1.5B) | CC-BY-NC 4.0 | 点云→Python CAD 代码 | ★★★★ |
| [Text-to-CadQuery](https://huggingface.co/papers/2505.06507) | - | 多模型微调 | - | 文本→CadQuery Python 代码（top-1 EM **69.3%**） | ★★★★★ 直接对标 |
| [CAD-MLLM](https://huggingface.co/papers/2411.04954) | - | - | - | 多模态→参数化 CAD | ★★★★ |
| [Text2CAD](https://huggingface.co/papers/2409.17106) | - | - | NeurIPS 2024 Spotlight | 首个 text-to-parametric-CAD | ★★★★ |
| [Img2CAD](https://huggingface.co/papers/2410.03417) | - | - | - | 2D 图像→可编辑参数 CAD | ★★★★ |
| [CAD2Program](https://huggingface.co/papers/2412.11892) | - | - | - | 2D CAD 图纸→3D 参数模型 | ★★★★ |

---

## 五、HuggingFace 开源数据集目录

### 5.1 增材制造/缺陷检测专用

| 数据集 | 规模 | 许可证 | 月下载 | 内容 | 关联度 |
|--------|------|--------|--------|------|--------|
| [**3D-ADAM**](https://huggingface.co/datasets/pmchard/3D-ADAM) | 9K 图像 / 4.9GB | CC-BY-NC-SA | 15.4K | AM 3D 异常检测（真实工业环境） | ★★★★★ |
| [VISION-Datasets](https://huggingface.co/datasets/VISION-Workshop/VISION-Datasets) | 18K+ 图像 / 14 数据集 | CC-BY-NC 4.0 | 66 | Casting/Cylinder 等工业缺陷 | ★★★★ |
| [Defect Spectrum](https://huggingface.co/datasets/DefectSpectrum/Defect_Spectrum) | 13K 条 / 1.95GB | MIT | 7.9K | 通用工业缺陷 + VLM 字幕 | ★★★☆ |
| [failures-3D-print](https://huggingface.co/datasets/Javiai/failures-3D-print) | 73 张 / 3.5MB | - | - | FDM 3D 打印故障 | ★★★ (小规模) |
| [Thermal-Image-Pretraining](https://huggingface.co/datasets/baratilab/Thermal-Image-Pretraining) | - | - | 3 | AM 热成像预训练 | ★★★★★ 金属 AM |

### 5.2 CAD/3D 模型数据集

| 数据集 | 规模 | 许可证 | 月下载 | 内容 | 关联度 |
|--------|------|--------|--------|------|--------|
| [**ThomasTheMaker/cadquery**](https://huggingface.co/datasets/ThomasTheMaker/cadquery) | **147K** 图像+CadQuery 代码 | - | - | 图像→CadQuery Python 代码对 | ★★★★★ 直接可用 |
| [**Text2CAD**](https://huggingface.co/datasets/SadilKhan/Text2CAD) | 605GB | CC-BY-NC-SA | 285 | 多级文本标注+CAD 序列+RGB 渲染 | ★★★★★ |
| [**Omni-CAD**](https://huggingface.co/datasets/jingwei-xu-00/Omni-CAD) | ~450K 实例 | MIT | 57 | 文本+图像+点云+CAD 命令序列 | ★★★★★ |
| [**ablam/gcode**](https://huggingface.co/datasets/ablam/gcode) | **442M 行** / 11GB | - | - | 400 模型 / 740 切片的 G-code | ★★★★★ 唯一大规模 |
| [**Thingi10K**](https://huggingface.co/datasets/Thingi10K/Thingi10K) | 10K STL / 72 类 | 混合 CC | 1.3K | 3D 打印模型（50% 非实体，45% 自相交） | ★★★★★ mesh 修复 |
| [Objaverse](https://huggingface.co/datasets/allenai/objaverse) | 800K+ 3D | ODC-By | 525K | 通用 3D 对象 | ★★★ |
| [Objaverse-XL](https://huggingface.co/datasets/allenai/objaverse-xl) | 10M+ 3D | ODC-By | - | 超大规模 3D | ★★★ |
| [ShapeNetCore](https://huggingface.co/datasets/ShapeNet/ShapeNetCore) | 51K / 55 类 | 非商业 | 595 | 日常物体 3D 模型 | ★★ |
| [thingiverse-openscad](https://huggingface.co/datasets/redcathode/thingiverse-openscad) | 7.4K | CC-BY-NC-SA | - | OpenSCAD 代码+合成提示 | ★★★ |
| [openscad-vision](https://huggingface.co/datasets/adrlau/openscad-vision) | 2K | - | - | 提示+OpenSCAD+多角度渲染 | ★★★ |
| [MeshCoderDataset](https://huggingface.co/datasets/InternRobotics/MeshCoderDataset) | 10万-100万 | CC-BY-NC-SA | - | 点云+Blender 脚本 | ★★★ |

### 5.3 材料/微观结构

| 数据集 | 规模 | 内容 | 关联度 |
|--------|------|------|--------|
| [porous-microstructure-strain-fields](https://huggingface.co/datasets/cmudrc/porous-microstructure-strain-fields) | - | 孔隙缺陷+应变场 | ★★★★ AM 孔隙建模 |
| [Materials](https://huggingface.co/datasets/Allanatrix/Materials) | 87K | DFT 材料属性 | ★★★ 材料选择 |
| [Cap3D](https://huggingface.co/datasets/tiange/Cap3D) | - | 3D 对象文本描述 | ★★★ 预训练 |

### 5.4 非 HuggingFace 关键数据源

| 数据集 | 来源 | 内容 | 获取方式 |
|--------|------|------|----------|
| **ORNL Peregrine** | 橡树岭国家实验室 | LPBF 原位监控：可见光/热成像/XCT（316L, IN718） | [Globus](https://doi.ccs.ornl.gov) |
| **NIST AM-Bench** | NIST | AM 基准测试：IN718 LPBF、IN625 力学性能/微观结构 | [NIST](https://www.nist.gov/ambench) |
| **Slice-100K** | NeurIPS 2024 | 100K+ G-code + CAD + 渲染图 | [GitHub](https://github.com/idealab-isu/Slice-100K) |
| [Txt2Microstruct-Net 数据集](https://mdr.nims.go.jp/datasets/15bfc8f2-a582-4bcf-a1b5-6871e31e414e) | NIMS | 2000 个 3D 微观结构+文本描述 | NIMS MDR |

---

## 六、与 CADPilot 的关联分析

### 6.1 管线节点→技术映射

```
┌─────────────────────────────────────────────────────────────────┐
│  CADPilot V3 Pipeline Node        推荐 AI 技术                    │
├─────────────────────────────────────────────────────────────────┤
│  analyze_intent / analyze_vision  CADFusion / CAD-MLLM (HF)     │
│  generate_cadquery                Text-to-CadQuery + 147K 数据集  │
│  generate_raw_mesh                TRELLIS + MeshAnythingV2 (HF)  │
│  mesh_healer                      Neural-Pull (MIT) + MeshLib    │
│  boolean_assemble                 manifold3d (确定性算法优先)      │
│  orientation_optimizer            Learn to Rotate (RL) 参考       │
│  generate_supports                RL 支撑优化 (Learn to Rotate)   │
│  thermal_simulation → 降级        PINN/FNO 代理模型 (PhysicsNeMo)  │
│  slice_to_gcode                   CuraEngine CLI + LLM 参数调优   │
│  (新) 可打印性检查                 GNN 变形预测 (HP Graphnet 架构)   │
│  (新) 过程监控                     YOLOv5/ViT + 3D-ADAM 数据集     │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 HuggingFace 资源的直接可用性

**第一梯队：直接可用/强参考**

1. **Text-to-CadQuery** — 与 CADPilot V3 的 text→CadQuery→STEP 目标完全一致，170K 标注
2. **ThomasTheMaker/cadquery** — 147K 条图像-CadQuery 代码对，可直接微调 Code Generator
3. **CADFusion** (Microsoft, MIT) — 文本→CAD + VLM 反馈，可参考架构
4. **CAD-Editor** (Microsoft, MIT) — 自然语言编辑 CAD，SmartRefiner 参考
5. **Text2CAD / Omni-CAD 数据集** — 大规模多模态 CAD 训练数据

**第二梯队：管线辅助**

6. **3D-ADAM** — AM 异常检测数据集（如果做过程监控）
7. **Thingi10K** — 10K 3D 打印模型，50% 非实体 → mesh 修复研究
8. **ablam/gcode** — 唯一大规模 G-code 数据集，切片分析
9. **MeshAnythingV2** (MIT) — mesh 重拓扑/简化
10. **TRELLIS** (Microsoft, MIT) — 高保真 3D 生成

### 6.3 关键发现

1. **CadQuery 数据集已存在**：147K 条（ThomasTheMaker）+ 170K 标注（Text-to-CadQuery），可评估用于微调
2. **CAD 代码生成优于 mesh 生成**：对于工业级零件，参数化代码路线（Text-to-CadQuery）精度远超 mesh 生成路线
3. **Mesh 修复模型缺位**：HuggingFace 上无专门 mesh repair 模型，MeshAnythingV2 可部分替代
4. **金属 AM 专用资源稀缺**：HuggingFace 上仅 3D-ADAM 和 BaratiLab 热成像数据直接面向 AM
5. **NVIDIA PhysicsNeMo 是关键框架**：Apache 2.0，提供 FNO/DeepONet/MeshGraphNet 全栈

---

## 七、关键趋势与战略建议

### 7.1 六大技术趋势（2024-2026）

1. **物理-数据混合驱动** → PINN/PI-ML 成为主流，替代纯数据驱动
2. **算子学习崛起** → FNO/DeepONet 实现函数到函数映射，10 万倍加速
3. **GNN 普及** → 解决网格依赖问题，支持任意几何体（HP 开源验证）
4. **多模态传感融合** → 热/光学/声学多源 + CNN/Transformer 特征提取
5. **边缘部署** → 云端推理→车间现场毫秒级响应
6. **开源生态成熟** → PhysicsNeMo 提供工业级框架，企业（HP）贡献专用模型

### 7.2 CADPilot 战略建议

**短期可落地（Phase 1-2）：**
- 评估 `ThomasTheMaker/cadquery` 和 Text-to-CadQuery 数据用于微调 Code Generator
- 参考 CADFusion/CAD-Editor 的 VLM 反馈机制优化 SmartRefiner
- 集成 MeshAnythingV2 (MIT) 到 mesh_healer 管线

**中期布局（Phase 3）：**
- 基于 NVIDIA PhysicsNeMo 探索可打印性检查的 GNN 代理模型
- 参考 Learn to Rotate (RL) 的方法优化 orientation_optimizer
- 评估 PINN 代理模型替代简单的几何检测（thermal_simulation 降级节点）

**长期储备（Phase 4+）：**
- 跟踪 DRL 扫描路径优化的开源化进展（当前仅论文无代码）
- 关注微观结构控制的 DRL+相场模型（等轴晶粒控制）
- 评估 LLM 多智能体系统（LLM-3D Print）在过程监控中的可行性

---

## 参考来源

### 论文与项目
- [ThermalControlLPBF-DRL - GitHub](https://github.com/BaratiLab/ThermalControlLPBF-DRL)
- [DRL Toolpath Generation for LPBF - arXiv:2404.07209](https://arxiv.org/abs/2404.07209)
- [Reinforced Scan - Springer 2025](https://link.springer.com/article/10.1007/s00170-025-17144-9)
- [Learn to Rotate - IEEE TII 2023](https://ieeexplore.ieee.org/document/10054468/)
- [MeltpoolINR - arXiv:2411.18048](https://arxiv.org/abs/2411.18048)
- [LP-FNO - arXiv:2602.06241](https://arxiv.org/abs/2602.06241)
- [Graph Neural Operator for AM - Additive Manufacturing 2025](https://www.sciencedirect.com/science/article/abs/pii/S2214860425004282)
- [LLM-3D Print - arXiv:2408.14307](https://arxiv.org/abs/2408.14307)
- [MIND (SIGGRAPH 2025) - GitHub](https://github.com/TimHsue/MIND)
- [Txt2Microstruct-Net - GitHub](https://github.com/xyzheng-ut/Txt2Microstruct-Net)
- [NVIDIA PhysicsNeMo - GitHub](https://github.com/NVIDIA/physicsnemo)
- [AM_DeepONet - GitHub](https://github.com/ncsa/AM_DeepONet)
- [HP Virtual Foundry Graphnet - NVIDIA Blog](https://developer.nvidia.com/blog/spotlight-hp-3d-printing-and-nvidia-physicsnemo-collaborate-on-open-source-manufacturing-digital-twin/)
- [Slice-100K (NeurIPS 2024) - GitHub](https://github.com/idealab-isu/Slice-100K)
- [Text-to-CadQuery - arXiv:2505.06507](https://huggingface.co/papers/2505.06507)

### 数据集
- [3D-ADAM - HuggingFace](https://huggingface.co/datasets/pmchard/3D-ADAM)
- [ThomasTheMaker/cadquery - HuggingFace](https://huggingface.co/datasets/ThomasTheMaker/cadquery)
- [Text2CAD Dataset - HuggingFace](https://huggingface.co/datasets/SadilKhan/Text2CAD)
- [Omni-CAD - HuggingFace](https://huggingface.co/datasets/jingwei-xu-00/Omni-CAD)
- [ablam/gcode - HuggingFace](https://huggingface.co/datasets/ablam/gcode)
- [Thingi10K - HuggingFace](https://huggingface.co/datasets/Thingi10K/Thingi10K)
- [ORNL Peregrine Dataset](https://www.ornl.gov/organization-news/peregrine-releases-new-dataset-smarter-3d-printing)
- [NIST AM-Bench](https://www.nist.gov/ambench)
