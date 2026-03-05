---
tags: [deep-analysis, 3d-generation, metal-3d-printing, geometry-first]
date: 2026-03-05
scope: organic-pipeline model selection for metal 3D printing
---

# 几何优先 3D 生成模型深度调研

> 目标：为 CADPilot 有机管道的金属 3D 打印场景，寻找几何质量优于或可替代 TripoSG 的开源模型。

---

## 一、调研范围与筛选标准

**硬性要求（金属 3D 打印管线）：**

| 要求 | 原因 |
|------|------|
| 开源 + 可自部署 | GPU 服务器本地运行，不依赖第三方 API |
| 图片输入 → 3D mesh 输出 | 管线入口是 FLUX.1 生成的参考图 |
| 几何精度优先 | 金属打印不用纹理，几何是唯一变量 |
| 水密/流形输出或易修复 | 金属打印切片器强制要求 |
| RTX 5090 32GB 可运行 | 当前硬件约束 |

**排除条件：**
- 闭源 / 仅 API 访问
- 仅开源 VAE 而无完整图→3D 推理管线
- 纹理优先、几何为辅的模型

---

## 二、候选模型全景

### 2.1 第一梯队：完整图→3D 管线 + 开源 + 可自部署

| 模型 | 开发方 | 3D 表示 | 开源 | 完整管线 | VRAM | 几何精度 |
|------|--------|---------|------|---------|------|---------|
| **TripoSG** | VAST/Stability | SDF → MC | MIT | 完整 | ~6GB | 极高 |
| **Hi3DGen** | ByteDance/CUHK | Normal→Latent Diffusion→Mesh | MIT | 完整 | ~16-24GB | 极高 |
| **CraftsMan3D** | HKUST | 3D Native DiT + Refiner | MIT | 完整 | ~12-16GB | 高 |

### 2.2 第二梯队：部分开源 / 即将开源

| 模型 | 开发方 | 3D 表示 | 状态 | 备注 |
|------|--------|---------|------|------|
| **TripoSF** | VAST | SparseFlex | 仅 VAE 开源 | 完整管线待 Tripo 3.0 发布 |
| **Sparc3D** | Sensory Universe | Sparcubes | 代码开源，权重未开放 | 已转向商业化 (Hitem3D) |

### 2.3 排除项

| 模型 | 排除原因 |
|------|---------|
| **Seed3D 1.0** (ByteDance) | 闭源，仅 API 访问，权重未开放 |
| **Hunyuan3D-2.1** (Tencent) | 几何精度不如 TripoSG（40K 固定面数） |
| **TRELLIS.2** (Microsoft) | SLat 几何精度上限受限于纹理共享 latent |
| **Rodin Gen-2** | 闭源商业 API |
| **Neural4D / Direct3D-S2** | 闭源商业平台 |
| **Imagen3D** | 闭源商业 API |
| **LLaMA-Mesh** | 文本→mesh，几何精度远不够 |
| **Unique3D** | 2024 年模型，已被后续 SOTA 超越 |

---

## 三、重点模型深度分析

### 3.1 TripoSG（当前基线）

**技术架构：** 1.5B Rectified Flow MoE Transformer + SDF VAE

- SDF 隐式表示 + Marching Cubes 提取等值面
- 天然闭合流形（watertight by design）
- 面数 60万–210万，几何细节保留极好

**金属打印管线适配度：**
- 水密性：天然满足 → mesh_healer 基本免费
- 降面：百万级降到目标面数，细节保留可控
- 速度：14s/模型，迭代效率最高
- VRAM：推理峰值 ~6GB，与其他模型共存无压力

**已知局限：**
- SDF 只能表示闭合表面（对金属打印反而是优点）
- 无纹理（金属打印不需要）
- 薄壁和对称性表现中等

**综合评分：9/10**（金属打印场景）

---

### 3.2 Hi3DGen（最强挑战者）

**技术架构：** Image → Normal Map → Normal-regularized Latent Diffusion → Mesh

三阶段管线：
1. **Image-to-Normal Estimator**：双流训练 + 噪声注入，生成高质量法线图
2. **Normal-to-Geometry**：基于 TRELLIS 的法线正则化潜扩散学习
3. **Mesh Extraction**：xatlas UV 展开 + mesh 提取

**核心创新——Normal Bridging：**
- 法线图是 2.5D 表示，比 RGB 提供更清晰的几何线索
- 解耦了"理解图片"和"生成几何"两个任务
- 消除了合成训练数据与真实图片之间的域差距

**Benchmark 表现：**
- ICCV 2025 接收，用户研究显示在业余和专业用户中均显著优于 Hunyuan3D-2.0、TRELLIS、Tripo-2.5
- 特别在**细粒度几何细节**（薄突出物、孔洞、文字）上表现卓越

**金属打印管线适配度：**
- 几何精度：可能优于 TripoSG（尤其细粒度细节）
- 水密性：基于 TRELLIS 解码器，不保证天然水密 → mesh_healer 需要工作
- 速度：多阶段管线，预估数分钟/模型 → 迭代效率远低于 TripoSG
- VRAM：~16-24GB → RTX 5090 可以跑但不能与其他模型共存

**已知局限：**
- 推理时间较长（normal estimation + diffusion + xatlas）
- xatlas 步骤 CPU 密集，已知较慢
- VRAM 泄漏问题有社区报告（连续生成后 OOM）
- 基于 TRELLIS，继承其几何精度上限（SLat 表示）

**综合评分：7.5/10**（金属打印场景）

---

### 3.3 CraftsMan3D（交互式几何精修）

**技术架构：** 3D Native DiT + Normal-based Geometry Refiner

两步生成：
1. 3D Native DiT 在 latent space 生成粗几何（~25s）
2. Normal-based Geometry Refiner 增强表面细节（可自动或交互式）

**核心特色：**
- **交互式几何精修**：用户可以手动指定需要精修的区域
- 支持加载 TripoSG / Hunyuan3D 权重进行训练和微调
- CVPR 2025 接收，MIT 协议

**金属打印管线适配度：**
- 几何精度：高，但不如 TripoSG 的百万级面数
- 交互精修功能在自动化管线中无法利用
- 水密性：不保证，需 mesh_healer
- 速度：~25s + 精修时间

**已知局限：**
- 粗几何阶段的分辨率有限
- 自动精修效果不如交互式
- 作为管线节点使用时，交互式优势无法发挥

**综合评分：6.5/10**（金属打印场景）

---

### 3.4 TripoSF（未来最强候选，当前不可用）

**技术架构：** SparseFlex VAE + Rectified Flow Transformer（完整管线未开源）

**SparseFlex 的关键突破：**
- 结合 Flexicubes 的可微分 mesh 提取 + 稀疏体素结构
- 支持任意拓扑（开放表面、内部结构）
- 分辨率高达 1024^3，Chamfer Distance 降低 82%，F-score 提升 88%
- 仅 12GB VRAM 即可运行

**为什么是"未来最强"：**
- TripoSG 的 SDF 只能表示闭合表面 → TripoSF 的 SparseFlex 无此限制
- 几何细节比 TripoSG 更丰富（内部结构、薄壁表面）
- ICCV 2025 接收

**当前状态：**
- 仅 VAE 开源（encode/decode mesh ↔ latent）
- 完整图→3D 推理管线待 Tripo 3.0 发布
- **无法直接用于当前管线**

**综合评分：N/A（不可用）→ 预估 9.5/10（一旦开源）**

---

## 四、关键对比矩阵（金属 3D 打印视角）

| 维度 | TripoSG | Hi3DGen | CraftsMan3D |
|------|---------|---------|-------------|
| **几何精度** | 极高（百万级面数 SDF） | 极高（Normal Bridging） | 高（DiT + Refiner） |
| **细粒度细节** | 优秀 | 最佳 | 良好 |
| **水密保证** | 天然水密（SDF） | 不保证 | 不保证 |
| **推理速度** | 14s | 数分钟 | ~25s+ |
| **VRAM** | ~6GB | ~16-24GB | ~12-16GB |
| **共存部署** | 可与其他模型共存 | 独占 GPU | 可能共存 |
| **管线兼容性** | 直接替换 | 需适配 | 需适配 |
| **成熟度** | 生产就绪 | 研究阶段（VRAM leak） | 较成熟 |
| **社区** | VAST 活跃维护 | ByteDance/Stable-X | HKUST 学术团队 |
| **协议** | MIT | MIT | MIT |

---

## 五、结论与建议

### 5.1 当前最优选择：TripoSG

**理由：在金属 3D 打印管线的全链路视角下，TripoSG 仍然是最优选择。**

Hi3DGen 在几何细节精度上可能略优于 TripoSG（ICCV 2025 用户研究支持这一点），但这个优势在管线全链路中被以下因素抵消：

1. **水密性成本**：TripoSG 天然水密 → mesh_healer 基本跳过。Hi3DGen 不保证水密 → mesh_healer 需要完整修复链，可能引入几何损失。**Hi3DGen 在生成阶段赢得的细节精度，可能在修复阶段被吃掉。**

2. **迭代效率**：14s vs 数分钟 = 创意探索阶段可迭代 10+ 轮 vs 2-3 轮。对创意雕塑来说，"多试几个方案选最好的"比"每个方案多一点细节"更有价值。

3. **部署成本**：6GB vs 24GB VRAM 意味着 TripoSG 可以和其他模型（FLUX.1 参考图生成等）共存在同一张 GPU 上。Hi3DGen 基本独占 GPU。

4. **稳定性**：TripoSG 是 VAST 的成熟产品线（TripoSR → TripoSG → TripoSF），生产级稳定性。Hi3DGen 有社区报告的 VRAM 泄漏和 xatlas 慢速问题。

### 5.2 监控 TripoSF 开源进度

TripoSF 是 TripoSG 的直系进化版，架构从 SDF 升级到 SparseFlex：
- 几何精度更高（Chamfer Distance -82%）
- 支持任意拓扑（内部结构、薄壁）
- VRAM 需求适中（12GB）
- 同一团队（VAST），API 兼容性高

**建议：** 持续关注 [VAST-AI-Research/TripoSF](https://github.com/VAST-AI-Research/TripoSF) 和 Tripo 3.0 发布动态。一旦完整图→3D 管线开源，立即评估替换 TripoSG。

### 5.3 Hi3DGen 作为备选方案

如果遇到 TripoSG 几何精度不足的特定场景（如极细薄壁结构、复杂内部通道），可按需启动 Hi3DGen 作为高精度备选。建议：
- 不作为默认策略
- 作为 generate_raw_mesh 的额外策略注册（strategy="hi3dgen"）
- 用户显式选择时启用

### 5.4 推荐的管线策略架构

```
generate_raw_mesh 节点策略:
├── triposg (默认) — 14s, 生产级, 天然水密
├── hi3dgen (备选) — 高精度细节, 需完整 mesh_healer
├── trellis  (保留) — 带纹理预览需求时使用
├── hunyuan3d (保留) — 渲染展示需求时使用
└── triposf  (待开源) — TripoSG 的升级替代
```

---

## 六、数据来源

- [TripoSG 论文 (arXiv:2502.06608)](https://arxiv.org/html/2502.06608v3)
- [TripoSF / SparseFlex (GitHub)](https://github.com/VAST-AI-Research/TripoSF)
- [Hi3DGen (ICCV 2025)](https://stable-x.github.io/Hi3DGen/)
- [Hi3DGen GitHub (ByteDance)](https://github.com/bytedance/Hi3DGen)
- [Stable3DGen (Hi3DGen 部署框架)](https://github.com/Stable-X/Stable3DGen)
- [CraftsMan3D (CVPR 2025)](https://github.com/HKUST-SAIL/CraftsMan3D)
- [Sparc3D 争议](https://www.vset3d.com/the-sparc3d-controversy-from-open-source-promise-to-paid-hitem3d-platform/)
- [Seed3D 1.0 (ByteDance, 闭源)](https://seed3d.dev/)
- [VAST 开源月公告](https://www.tripo3d.ai/blog/vast-open-source-month)
