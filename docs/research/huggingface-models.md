---
title: HuggingFace 模型目录
tags:
  - research
  - huggingface
  - model-catalog
status: active
created: 2026-03-03
last_updated: 2026-03-03
---

# HuggingFace 模型目录

> [!abstract] 说明
> 本页汇总 HuggingFace Hub 上与 3D 打印/CAD/增材制造相关的所有模型。按用途分类，标注许可和商用可行性。

---

## 3D/CAD 生成模型

### 可商用（MIT / Apache 2.0）

| 模型 | 机构 | 参数 | 许可 | 月下载 | 功能 |
|:-----|:-----|:-----|:-----|:-------|:-----|
| [TRELLIS-image-large](https://huggingface.co/microsoft/TRELLIS-image-large) | Microsoft | 2-4B | ==MIT== | 2.6M | 图→3D mesh + PBR |
| [CADFusion](https://huggingface.co/microsoft/CADFusion) | Microsoft | 8B | ==MIT== | - | 文本→参数化 CAD |
| [CAD-Editor](https://huggingface.co/microsoft/CAD-Editor) | Microsoft | 8B | ==MIT== | - | NL 编辑 CAD |
| [TripoSR](https://huggingface.co/stabilityai/TripoSR) | Stability AI | 1.68GB | ==MIT== | 62K | 快速 3D 重建 |
| [CraftsMan3D](https://huggingface.co/craftsman3d/craftsman) | - | - | ==Apache 2.0== | - | 照片→GLB + remesh |

### 有限商用

| 模型 | 许可 | 限制 | 月下载 | 功能 |
|:-----|:-----|:-----|:-------|:-----|
| [SPAR3D](https://huggingface.co/stabilityai/stable-point-aware-3d) | Community | 年收入<$1M 免费 | 1.2K | <1s 单图→3D |
| [Hunyuan3D-2](https://huggingface.co/tencent/Hunyuan3D-2) | Community | 腾讯社区协议 | 75K | DiT 形状+纹理 |

### 非商业/研究用

| 模型 | 许可 | 月下载 | 功能 |
|:-----|:-----|:-------|:-----|
| [CAD-Recode](https://huggingface.co/filapro/cad-recode) | CC-BY-NC 4.0 | 10 | 点云→CAD 代码 |
| [LLaMA-Mesh](https://huggingface.co/Zhengyi/LLaMA-Mesh) | NSCLv1 (非商业) | 550 | 文本对话式 mesh |
| [MeshGPT-preview](https://huggingface.co/MarcusLoren/MeshGPT-preview) | 研究 | - | 文本→三角 mesh |
| [Make-A-Shape](https://huggingface.co/ADSKAILab/Make-A-Shape-single-view-20m) | Autodesk NC | - | 多模态→3D（含 ABC 数据） |
| Hi3DGen | 研究 | - | 法线桥接高保真几何 |

---

## Mesh 处理模型

| 模型 | 参数 | 许可 | 功能 | 详情 |
|:-----|:-----|:-----|:-----|:-----|
| [MeshAnythingV2](https://huggingface.co/Yiwen-ntu/MeshAnythingV2) | 500M | ==MIT== | 稠密→低面数 artist mesh | [[mesh-processing-repair#MeshAnythingV2]] |

> [!warning] 缺口
> HuggingFace 上==没有==专门的 mesh repair/healing 模型。Neural-Pull 和 DeepSDF 仅在 GitHub 上。

---

## CAD 相关论文（HF Paper Pages）

| 论文 | 类型 | 链接 |
|:-----|:-----|:-----|
| Text-to-CadQuery | text→CadQuery 代码 | [Paper](https://huggingface.co/papers/2505.06507) |
| CAD-MLLM | 多模态→CAD | [Paper](https://huggingface.co/papers/2411.04954) |
| CAD-Llama | 层次化 CAD 生成 | [Paper](https://huggingface.co/papers/2505.04481) |
| Text2CAD | NeurIPS 2024 Spotlight | [Paper](https://huggingface.co/papers/2409.17106) |
| GenCAD | 图像→CAD 命令 | [Paper](https://huggingface.co/papers/2409.16294) |
| Img2CAD | 2D 图像→参数 CAD | [Paper](https://huggingface.co/papers/2410.03417) |
| CAD2Program | 2D 图纸→3D 参数模型 | [Paper](https://huggingface.co/papers/2412.11892) |
| MeshCoder | 点云→Blender 脚本 | [Paper](https://huggingface.co/papers/2508.14879) |
| LLM-3D Print | LLM 多智能体 3D 打印 | [Paper](https://huggingface.co/papers/2408.14307) |

---

## 材料科学相关

| 模型 | 功能 | 链接 |
|:-----|:-----|:-----|
| lamm-mit/Cephalo 系列 | 材料科学视觉语言模型 | [HF](https://huggingface.co/lamm-mit) |
| lamm-mit/SD2x-leaf-inspired | 仿生设计 AM 图像生成 | [HF](https://huggingface.co/lamm-mit/SD2x-leaf-inspired) |

---

## 按 CADPilot 关联度排序

> [!success] 第一梯队：直接可用

| 模型 | 许可 | 关联节点 | 理由 |
|:-----|:-----|:---------|:-----|
| **CADFusion** | MIT | generate_cadquery | text→CAD + VLM 反馈 |
| **CAD-Editor** | MIT | SmartRefiner | NL 编辑 CAD |
| **MeshAnythingV2** | MIT | mesh_healer | mesh 重拓扑 |
| **TRELLIS** | MIT | generate_raw_mesh | 高保真 3D 生成 |
| **TripoSR** | MIT | generate_raw_mesh | 快速原型 |

> [!info] 第二梯队：有限制但有参考价值

| 模型 | 限制 | 参考价值 |
|:-----|:-----|:---------|
| SPAR3D | <$1M 免费 | 极致速度 API |
| Make-A-Shape | 非商业 | Autodesk 工程数据训练 |
| CAD-Recode | CC-BY-NC | 点云逆向方法 |
