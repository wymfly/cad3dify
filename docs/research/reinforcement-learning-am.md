---
title: 强化学习工艺控制
tags:
  - research
  - reinforcement-learning
  - process-control
  - scan-strategy
  - deep-analysis
status: active
created: 2026-03-03
last_updated: 2026-03-03
pipeline_nodes:
  - orientation_optimizer
  - generate_supports
maturity: ★★☆
---

# 强化学习工艺控制

> [!abstract] 核心价值
> RL 通过"试错-奖励"机制学习最优控制策略，适合 AM 中的自适应调参、扫描路径优化和原位缺陷修正。2025-2026 年 zero-shot sim-to-real 和 GPU 数字孪生取得突破，但==开源生态仍薄弱==。

> [!warning] 成熟度警告
> HuggingFace 上无 RL 模型。多数研究停留在论文+仿真阶段。关键突破：2025 年首次实现零样本仿真到真实设备迁移。

---

## RL 算法在 AM 中的适用性

| RL 算法 | 适用场景 | 动作空间 | 代表项目 | CADPilot 相关 |
|:--------|:--------|:---------|:---------|:-------------|
| **PPO** | 连续控制（热控制、挤出调节） | 连续 | ThermalControlLPBF-DRL | 中 |
| **DQN** | 离散决策（扫描路径、方向优化） | 离散 | Toolpath Gen, CPR-DQN | ==高== |
| **AWAC** | 离线→在线迁移（多层控制） | 连续 | SLM 多层控制 | 中 |
| **SAC** | 数字孪生闭环（机器人AM） | 连续 | Digital Twin Sync | 中 |
| **Q-learning** | 简单在线控制 | 离散 | WAAM Monitor | 低 |

---

## 关键项目（深入分析）

### ThermalControlLPBF-DRL (CMU BaratiLab) ⭐ 质量评级: 3/5

> [!success] 唯一完整开源 RL-AM 项目

| 属性 | 详情 |
|:-----|:-----|
| **GitHub** | [BaratiLab/ThermalControlLPBF-DRL](https://github.com/BaratiLab/ThermalControlLPBF-DRL)（40★） |
| **论文** | [arXiv:2102.03355](https://arxiv.org/abs/2102.03355)（Additive Manufacturing 2021） |
| **算法** | ==PPO==（stable-baselines3 v0.7.0） |
| **许可** | ==未声明== |

#### PPO 配置

| 参数 | 值 |
|:-----|:---|
| 算法 | PPO (Proximal Policy Optimization) |
| 库 | stable-baselines3 v0.7.0 |
| 网络 | sb3 默认 MLP（推测 2 层 64 节点） |
| 典型超参 | lr ~3e-4, gamma ~0.99, clip_range ~0.2 |
| 监控 | TensorBoard |

#### RUSLS 温度模拟

**Repeated Usage of Stored Line Solutions**（Wolfer et al., 2019）：
- 预计算单条扫描线的解析热传导解，存储为线解模板
- 任意扫描路径通过叠加已存储线解重构温度场
- 基于 Eagar-Tsai 解析热源模型（高斯热源 + 半无限体瞬态热传导）
- 代码实现：`EagarTsaiModel.py` → `EagarTsai()` 类
- 比 FEM 快数个量级，保留足够物理精度

#### 四个 Gym 环境

| 环境 | 控制参数 | 扫描路径 |
|:-----|:---------|:---------|
| `power_square_gym.py` | 激光功率 | 水平交叉影线 |
| `velocity_square_gym.py` | 扫描速度 | 水平交叉影线 |
| `power_triangle_gym.py` | 激光功率 | 同心三角 |
| `velocity_triangle_gym.py` | 扫描速度 | 同心三角 |

- **状态空间**：粉末床温度分布（RUSLS 模拟）
- **动作空间**：连续——调整激光功率或扫描速度
- **奖励函数**：最大化熔池深度一致性（minimize melt pool depth variation）

#### 代码质量评估

| 维度 | 评分 | 说明 |
|:-----|:-----|:-----|
| 文档 | ==4/5== | README 详尽，含训练/测试/TensorBoard/域配置教程 |
| 可读性 | 3/5 | 结构清晰（模型/环境/训练分离） |
| 测试覆盖 | 1/5 | 无单元测试 |
| 维护 | 2/5 | 22 commits，最后更新 2025-12-09 |

#### 部署指南

```bash
# 推荐 conda 环境
conda create -n lpbf-drl python=3.8 && conda activate lpbf-drl

# 安装依赖
pip install -r requirements.txt
# 核心：gym==0.17.3, torch==1.5.0, stable_baselines3==0.7.0

# 训练
python RL_learn_<env_type>.py

# 评估
python evaluate_learned_policy.py

# 监控
tensorboard --logdir tensorboard_logs/
```

> [!warning] 依赖兼容性问题
> - `gym==0.17.3` 已过时（现为 Gymnasium），需迁移 API
> - `torch==1.5.0` 与现代 CUDA 不兼容
> - `stable_baselines3==0.7.0` 为早期版本（当前 2.x）
> - 实际运行需降级 Python 3.8/3.9 或升级全部依赖

---

### DRL Toolpath Generation (DQN) 质量评级: 3.5/5

| 属性 | 详情 |
|:-----|:-----|
| **论文** | [arXiv:2404.07209](https://arxiv.org/abs/2404.07209)（Additive Manufacturing 2024） |
| **算法** | ==DQN==（epsilon-greedy） |
| **核心创新** | 用扫描路径转角近似热效应，大幅加速训练 |
| **结果** | 最大变形比 zigzag 减少 ==47%==，比棋盘格减少 ==29%== |
| **开源** | ❌ |

#### 状态/动作/奖励设计

**状态表示**：2D 网格环境，包含当前温度场 + 已/未访问点状态

**动作空间**（3 个离散选项）：
1. 最低温度方向——移向温度最低的相邻点（避免热积累）
2. 最平滑路径——转角最小方向（减少应力集中）
3. 次平滑路径——第二小转角方向

**奖励**：f(能量密度均匀性, 路径完整性)，惩罚未访问区域和碰撞

**FEM 耦合**：非直接耦合，用扫描路径转角作为热效应代理指标，避免每步运行完整热仿真。验证通过完整数值模拟 + 四组薄板 LPBF 实验。

---

### Learn to Rotate ⭐ 质量评级: 3.5/5

> [!success] 泛化 RL——在未见几何体上直接应用学到的旋转策略

| 属性 | 详情 |
|:-----|:-----|
| **论文** | [IEEE TII 2023](https://ieeexplore.ieee.org/document/10054468/) |
| **机构** | University of Huddersfield / Manchester / Bristol |
| **算法** | Generalizable RL (GRL) |
| **加速** | ==2.62x-229x==（vs 随机搜索） |
| **开源** | GPU 加速 benchmark 平台 |

#### GRL 泛化机制

**RotNet 框架**：
- **体素化统一表示**：将 3D 模型体素化为统一分辨率网格
- **多几何体训练**：训练集包含多种形状，学习通用旋转策略
- **泛化能力**：在未见几何体上直接应用策略（无需重新训练）

**状态编码**：体素表示 + 射线追踪计算支撑可达性 → 当前方向下的支撑体积特征向量

**动作空间**：预定义旋转角度增量（绕多轴），每步选择一个旋转动作

**奖励函数**：支撑体积越小奖励越高，区分可移除/不可移除支撑

#### CADPilot 集成路径

可参考其方法优化 `orientation_optimizer` 节点：
- 体素化 + 射线追踪 → 支撑体积评估
- GRL 学习通用旋转策略 → 避免在线搜索
- GPU 加速 benchmark 可直接参考

---

### Phase-Field + DRL 微观结构控制 质量评级: 3/5

| 属性 | 详情 |
|:-----|:-----|
| **论文** | [arXiv:2506.21815](https://arxiv.org/abs/2506.21815)（2025） |
| **机构** | UT El Paso + Arizona State University |
| **架构** | Phase-Field Model → 3D U-Net Surrogate → DQN Agent |
| **加速** | 比传统方法快 ==2-3 个数量级== |

#### 三层耦合架构

```
Phase-Field Model (PFM): n=20 晶粒取向, 域 1mm×0.3mm×0.1mm
  ↓ 训练数据生成
3D U-Net Surrogate: 3通道输入(取向+当前温度+未来温度) → 20通道输出
  ↓ 实时预测（2-3 量级加速）
DQN Agent: 5×5/11×11 网格, 4 方向动作
  ↓ 优化决策
Optimized Scan Path → Target Equiaxed Grains
```

**等轴晶粒控制奖励**：

| Case | 公式 | 目标 |
|:-----|:-----|:-----|
| Case 1 | R = 1/平均长径比 | 最小化晶粒拉长度 |
| Case 2 | R = 1/平均晶粒体积 | 最小化晶粒尺寸 |
| Case 3 | R = 0.5/AR + 0.9/V | 综合优化 |

---

### AWAC 多层 SLM 控制 ⭐ 质量评级: 3.5/5

> [!success] 首次在完整 3D 零件上展示 RL 过程控制

| 属性 | 详情 |
|:-----|:-----|
| **论文** | [J. Intelligent Manufacturing 2024](https://link.springer.com/article/10.1007/s10845-024-02548-3) |
| **算法** | ==AWAC==（Adaptive Weighted Actor-Critic） |
| **问题** | SLM 多层（35层）平均层温度控制 |
| **创新** | 首次展示完整 3D 零件的 RL 过程控制框架 |

#### AWAC vs SAC vs PID vs PPO

| 维度 | AWAC | SAC | PPO | PID |
|:-----|:-----|:-----|:-----|:-----|
| 训练稳定性 | ==高== | 中 | 中 | N/A |
| 超参调优 | ==免调== | 需手动 | 需调 | 需整定 |
| 预收敛期奖励 | ==高== | 低且波动 | 中 | N/A |
| 数据效率 | ==高==（离线+在线） | 中 | 较低(on-policy) | N/A |
| 离线→在线迁移 | ==原生支持== | 需适配 | 需额外适配 | N/A |
| 工业适用性 | ==高==（历史数据冷启动） | 中 | 中 | 中 |

**多层热积累 RL 方案**：每层=一个时间步，35 层=一个 episode。代理根据当前层热状态（含前序层热积累）调整激光功率，学会在后续层自动降功率补偿热积累。

---

## 2025-2026 最新进展

### Digital Twin + Zero-Shot Sim-to-Real（2025）⭐

| 属性 | 详情 |
|:-----|:-----|
| **论文** | [arXiv:2501.18016](https://arxiv.org/abs/2501.18016)（IEEE ERAS 2025） |
| **算法** | SAC + Unity ML-Agents |
| **通信** | ROS2 + Unity ROS-TCP-Connector |
| **同步延迟** | ==~20ms==（近实时） |
| **突破** | 首次 Unity+ROS2 数字孪生实时同步 RL 控制 |

**分层奖励结构 (HRS)** + 迁移学习：Case 1 训练权重迁移至 Case 2，60K 步收敛（无迁移需 150K 步）。

### GPU 加速多物理场数字孪生 + PPO（2025-2026）

| 属性 | 详情 |
|:-----|:-----|
| **论文** | [Virtual and Physical Prototyping 2025](https://www.tandfonline.com/doi/full/10.1080/17452759.2025.2610146) |
| **仿真引擎** | Merlin（GPU 原生：SPH + PBD + 显式方法耦合） |
| **RL** | PPO，控制 FFF 挤出流率 |
| **意义** | 证明 GPU 原生仿真可提供可靠合成数据 |

### 不确定性感知 RL + Zero-Shot 部署（2025）⭐

| 属性 | 详情 |
|:-----|:-----|
| **论文** | [Additive Manufacturing 2025](https://www.sciencedirect.com/science/article/pii/S2214860425002763) |
| **算法** | Deep Q-Learning + 视觉概率分布模块 |
| **创新** | ==零样本 sim-to-real==（标定仿真训练，直接部署） |
| **能力** | 纠正轻微和严重的欠/过挤出，无需额外训练 |

### CPR-DQN 路径优化（2025）

| 属性 | 详情 |
|:-----|:-----|
| **论文** | [ScienceDirect 2025](https://www.sciencedirect.com/science/article/pii/S2215098625002605) |
| **算法** | CPR-DQN (Count-Prioritized Replay DQN) + 课程学习 |
| **对比** | 超越 DQN / Rainbow DQN / BTR |

### WAAM 视觉 + Q-Learning（2025）

| 属性 | 详情 |
|:-----|:-----|
| **论文** | [MDPI J. Manuf. Mater. Process. 2025](https://www.mdpi.com/2504-4494/9/10/340) |
| **架构** | 表格 Q-learning + 定制光学（俯视+侧视同时采集） |
| **控制** | 电压 17-23V + 送丝速率 280-316 mm/min |

---

## 扫描路径优化

### Reinforced Scan

| 属性 | 详情 |
|:-----|:-----|
| **年份** | 2025 |
| **方法** | 分层 RL + 新型奖励函数（温度方差+空间均匀性） |
| **验证** | Ti-6Al-4V 薄板模拟+实验 |
| **结果** | 平均残余应力 ==309 MPa==（vs 顺序法 327 MPa），最大 ==603 MPa==（vs 717 MPa） |
| **论文** | [Springer 2025](https://link.springer.com/article/10.1007/s00170-025-17144-9) |

---

## DED/WAAM 工艺优化

| 项目 | 年份 | 算法 | 问题 | 开源 |
|:-----|:-----|:-----|:-----|:-----|
| DED Laser Power | 2024 | DQN | FE 模型学习激光功率控制 | ❌ |
| DED Nickel Alloy | 2024 | Deep RL | 镍基合金均匀温度分布 | ❌ |
| **RLPlanner** | 2023 | PPO + SLSQP | WAAM 薄壁路径规划 | ⚠️ |
| WAAM DDPG | 2023 | DDPG | 焊接参数调节 | ❌ |

---

## 开源代码深入评估

### PySLM ⭐ 质量评级: 4/5（推荐集成）

| 属性 | 详情 |
|:-----|:-----|
| **GitHub** | [drlukeparry/pyslm](https://github.com/drlukeparry/pyslm)（==160★==） |
| **许可** | ==LGPL-2.1==（允许商用） |
| **PyPI** | `pip install PythonSLM` |
| **文档** | [pyslm.readthedocs.io](https://pyslm.readthedocs.io) |
| **状态** | ==活跃维护==（2026-03-03 最后更新） |

**核心功能**：

| 模块 | 功能 | 技术 |
|:-----|:-----|:-----|
| Slicing | 3D 模型切片 | Trimesh v4.0 |
| Hatching | 扫描策略生成 | Meander/Island/Stripe |
| Support Generation | 支撑生成 | GPU GLSL 射线追踪 + Manifold CSG |
| Overhang Analysis | 悬垂分析 | 网格连通性 + 投影法 |
| Build-time Estimation | 构建时间估算 | 参数化模型 |

**与 RL 集成潜力**：hatching 输出可作为 DRL toolpath 优化初始状态；支撑体积计算可作为 Learn to Rotate 类奖励函数。

### Deep_Learning_for_Manufacturing 质量评级: 3/5

| 属性 | 详情 |
|:-----|:-----|
| **GitHub** | [sumitsinha/Deep_Learning_for_Manufacturing](https://github.com/sumitsinha/Deep_Learning_for_Manufacturing)（46★） |
| **许可** | ==MIT== |
| **功能** | Bayesian 3D CNN + 3D U-Net + ==DDPG 制造环境== + 持续学习 + 主动学习 |
| **借鉴** | DDPG 制造环境 + MATLAB-Python 连接 + Bayesian 不确定性量化 |

### DeepBuilder 质量评级: 2/5

| 属性 | 详情 |
|:-----|:-----|
| **GitHub** | [HeinzBenjamin/deepbuilder](https://github.com/HeinzBenjamin/deepbuilder)（11★） |
| **许可** | GPL-3.0（==限制商用==） |
| **算法** | TD3 + SAC |
| **评估** | 面向建筑级机器人 AM，非金属 3D 打印，借鉴价值有限 |

---

## 关键技术趋势

1. **Surrogate Model 加速 RL 训练**：3D U-Net/CNN 替代物理仿真，加速 100-1000x
2. **Zero-shot Sim-to-Real** ⭐：仿真训练直接部署真实设备，2025 年首次成功
3. **数字孪生闭环**：Unity/GPU 仿真 + ROS2 + 物理设备完整链路
4. **不确定性量化**：Bayesian 方法 + 概率分布保障 OOD 鲁棒性
5. **离线→在线迁移**：AWAC 利用历史数据冷启动，减少在线探索风险

---

## 综合对比表

| 项目 | 算法 | 应用 | 加速/效果 | 开源 | CADPilot 相关 |
|:-----|:-----|:-----|:---------|:-----|:-------------|
| ThermalControlLPBF-DRL | PPO | LPBF 热控制 | 优于 PID | ✅（40★） | 中 |
| DRL Toolpath Gen | DQN | 扫描路径 | 变形减少 ==47%== | ❌ | ==高== |
| **Learn to Rotate** | GRL | 构建方向 | ==2.62-229x== | ⚠️ benchmark | ==高== |
| Phase-Field+DRL | DQN+Surrogate | 微观结构 | ==100-1000x== | ❌ | 低 |
| **AWAC SLM** | AWAC | 多层控制 | 首次完整 3D 件 | ❌ | 中 |
| Digital Twin Sync | SAC | 机器人 AM | 20ms 同步 | ❌ | 中 |
| Uncertainty-aware RL | Deep Q | 挤出控制 | ==零样本迁移== | ❌ | 中 |
| CPR-DQN | CPR-DQN | 路径优化 | 超越 Rainbow | ❌ | 高 |
| **PySLM** | 无 RL | 切片/hatching | 完整工具链 | ==✅（160★）== | ==高== |

---

## 成熟度评估

| 方向 | 成熟度 | 开源 | 推荐 |
|:-----|:------|:-----|:-----|
| LPBF 热控制 | ★★★ | ✅ 1 个（依赖过时） | ⚠️ 学术参考 |
| 扫描路径优化 | ★★★ | ❌（仅论文） | ⚠️ 中期探索 |
| **构建方向优化** | ★★★ | ⚠️ benchmark | ✅ 中期集成 |
| 微观结构控制 | ★★ | ❌ | ❌ 长期跟踪 |
| **数字孪生闭环** | ★★☆ | ❌ | ⚠️ 概念参考 |
| **切片/扫描工具** | ★★★★ | ==✅ PySLM== | ==✅ 推荐集成== |

---

## CADPilot 集成战略建议

> [!success] 推荐优先级

1. **短期（P1）**：集成 PySLM 到 V3 管线
   - `pip install PythonSLM` 一行安装，LGPL-2.1 可商用
   - 切片 + hatching + 支撑生成 + 构建时间估算
   - 为 `slice_to_gcode` 和 `generate_supports` 节点提供基础能力

2. **中期（P2）**：参考 Learn to Rotate 方法优化 `orientation_optimizer`
   - 体素化 + 射线追踪 → 支撑体积评估
   - GRL 学习通用旋转策略→避免在线搜索
   - PySLM 支撑体积计算可直接作为奖励函数

3. **中期（P2）**：参考 AWAC 离线→在线迁移范式
   - 利用历史仿真数据冷启动 RL 代理
   - 免超参调优，适合工业场景

4. **长期**：跟踪 DRL 扫描路径优化（变形减少 47%）+ CPR-DQN 的开源化
5. **长期**：关注 zero-shot sim-to-real 突破在金属 AM 中的应用

---

## 更新日志

| 日期 | 变更 |
|:-----|:-----|
| 2026-03-03 | 深入研究更新：ThermalControlLPBF-DRL PPO 配置 + RUSLS 模拟 + 4 个 Gym 环境 + 代码质量评估 + 部署指南 + 依赖兼容性问题；DRL Toolpath 3 离散动作设计 + 奖励函数 + FEM 耦合方式；Learn to Rotate GRL 泛化机制 + 体素化状态编码 + 射线追踪；Phase-Field+DRL 三层耦合架构 + 3D U-Net Surrogate + 等轴晶粒奖励；AWAC vs SAC/PPO/PID 定量对比 + 多层热积累 RL 方案；PySLM 深入评估（160★, 活跃维护, LGPL-2.1）；2025-2026 新进展（Digital Twin Sim-to-Real / GPU 数字孪生 / 零样本迁移 / CPR-DQN / WAAM 视觉控制） |
| 2026-03-03 | 初始版本 |
