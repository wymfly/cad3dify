---
title: Web 3D 编辑技术全景调研
date: 2026-03-03
status: 研究完成
tags:
  - research
  - technology
  - web-cad
  - webgpu
  - wasm
  - ai-cad
parent: "[[README]]"
---

# Web 3D 编辑技术全景调研

> [!info] 导航
> ← [[README|研究首页]] · ← [[feasibility-report|可行性报告]] · → [[architecture-design|架构设计]]

---

## 1. 开源 Web 3D 编辑器与 CAD 内核

### 1.1 OpenCascade WebAssembly 生态

> [!example]- opencascade.js — 最成熟的 OCCT WASM 方案
> **仓库**：[github.com/donalffons/opencascade.js](https://github.com/donalffons/opencascade.js/)
>
> | 维度 | 详情 |
> |------|------|
> | 原理 | Emscripten 将完整 OCCT 编译为 WASM |
> | 性能 | 接近原生，支持多线程 (SharedArrayBuffer) |
> | 分发 | NPM `opencascade.js`，TypeScript 类型 |
> | 自定义构建 | 按需裁剪模块，优化体积 |
> | 局限 | C++ 异常模拟有额外开销 |
>
> > [!tip] 与 CADPilot 的关系
> > 后端 CadQuery 基于 OCCT，使用 opencascade.js 可保持 ==前后端 CAD 内核一致性==。

> [!example]- occt-import-js — 轻量级导入方案
> **仓库**：[github.com/kovacsv/occt-import-js](https://github.com/kovacsv/occt-import-js)
>
> - 仅支持文件导入（BREP、STEP、IGES），非完整 CAD 内核
> - 体积极小：仅 `.js` + `.wasm` 两个文件
> - 适合只需读取不需编辑的场景

> [!example]- CascadeStudio — 浏览器端脚本化 CAD IDE
> **仓库**：[github.com/zalo/CascadeStudio](https://github.com/zalo/CascadeStudio)
>
> - 基于 opencascade.js，代码即 CAD
> - 支持基元/CSG 到旋转体、扫掠、圆角等完整操作
> - 导出 .step/.stl/.obj，URL 自动保存代码

### 1.2 Three.js 系 CAD 编辑器

> [!example]- JSketcher — 功能最全的开源浏览器 CAD ⭐
> **仓库**：[github.com/xibyte/jsketcher](https://github.com/xibyte/jsketcher)
>
> - 2016 年起，2019 年起使用 OpenCASCADE
> - 工业标准 ==Sketch → Feature → History== 范式
> - Extrude、Revolve、Loft、Sweep、Mirror
> - 内置 2D 约束求解器
> - 导出 STL（3D）、DWG/SVG（2D）
> - 纯客户端，代码较老但功能最全面

> [!example]- BREP.io — 2025 新锐，三角网格上的 BREP ⭐
> **仓库**：[github.com/mmiscool/BREP.io](https://github.com/mmiscool/BREP.io)
>
> ==核心创新==：在三角网格之上实现 BREP 风格的参数化工作流
>
> | 技术 | 方案 |
> |------|------|
> | CSG 操作 | [Manifold](https://github.com/elalish/manifold) WASM |
> | 拓扑表示 | 轻量级面/边表示 |
> | 历史管线 | 完整 Feature History Pipeline |
> | 可视化 | Three.js |
> | 分发 | `brep-io-kernel` NPM 包（内联 WASM） |
>
> 布尔运算、圆角、倒角、扫掠、放样、多体操作全部客户端执行。
>
> > [!tip] 对 CADPilot 的启发
> > 证明了三角网格上也能实现类 BREP 参数化体验，==对有机形态路径启发很大==。

> [!example]- 其他 Three.js CAD 项目
> - **Chili3D** ([GitHub](https://github.com/xiangechen/chili3d)) — 基本形状、2D 草图、布尔运算
> - **Three.cad** ([GitHub](https://github.com/twpride/three.cad)) — Three.js + React + WASM，参数化草图 + CSG
> - **Chokoku CAD** ([GitHub](https://github.com/itta611/ChokokuCAD)) — 投影切割交互，移动端友好

### 1.3 Rust/WASM 新兴 CAD 内核

> [!example]- Truck — Rust CAD 内核
> **仓库**：[github.com/ricosjp/truck](https://github.com/ricosjp/truck)
>
> - ParametricCurve、ParametricSurface、B-Spline、NURBS、拓扑结构
> - 被 CADmium 用作底层引擎，可编译为 WASM

> [!example]- CADmium — Local-First 浏览器 CAD
> **仓库**：[github.com/CADmium-Co/CADmium](https://github.com/CADmium-Co/CADmium)
>
> - Truck 内核 + SvelteKit + Tailwind + Threlte
> - JSON 数据格式（Operation Log = JSON Lines）
> - Alpha 阶段，积极招募 Rust + SvelteKit 开发者

> [!example]- Fornjot — Rust B-Rep 内核
> [fornjot.app](https://www.fornjot.app/) — 早期阶段，已到 v0.49.0

### 1.4 FreeCAD / Ondsel

> [!warning] Ondsel（FreeCAD 商业化云平台）已于 2025 年 3 月关闭
> - 向 FreeCAD 项目协会捐赠 40,000 欧元
> - FreeCAD 专注桌面端，暂无浏览器版计划
> - BRL-CAD 同样无明确 Web 版计划

---

## 2. 商业 Web 3D CAD 平台

> [!example]- Onshape (PTC) — 服务端内核标杆 ⭐
> | 维度 | 详情 |
> |------|------|
> | 架构 | 完全云原生，Parasolid v38.0 运行在服务端 |
> | 浏览器端 | 仅轻量前端 + WebGL，所有计算云端完成 |
> | 协作 | 实时多用户同时编辑，内置版本控制和分支 |
> | AI | 2025 年推出 AI Advisor |
> | Mixed Modeling | Parasolid 支持融合网格与精确几何 |
>
> > [!warning] 对 CADPilot 的启示
> > Onshape 依赖商业 Parasolid 内核和强大服务端，CADPilot **不应走这条路**，
> > 但「轻量前端 + 重型后端」思路值得参考。

> [!example]- 其他商业平台
> - **Shapr3D** — Parasolid 本地运行，iPad 触控为主，浏览器仅 Review Link
> - **xDesign (Dassault)** — 3DEXPERIENCE 浏览器端，2025 推出 xDraftSight
> - **Tinkercad (Autodesk)** — 免费在线 CSG 建模，教育市场定位
> - **Clara.io** — 云端多边形建模/动画/渲染，多用户编辑，非工业 CAD

---

## 3. 渲染与基础技术

### 3.1 WebGPU 全面就绪

> [!success] 里程碑：2025 年 9 月 Safari 26 后，WebGPU ==所有主流浏览器== 均可用

| 特性 | WebGL | WebGPU |
|------|:-----:|:------:|
| Draw Call 性能 | 瓶颈 | ==2-10x 提升== |
| 通用 GPU 计算 | ❌ | ✅ Compute Shader |
| 内存管理 | 隐式 | 显式控制 |
| 着色器语言 | GLSL | WGSL / TSL |

### 3.2 Three.js 2026 生态

> [!tip] 关键变化
> - **r171**：WebGPU 零配置支持，自动回退 WebGL 2
> - **TSL**：JavaScript 风格着色器，同时编译为 WGSL + GLSL
> - 迁移成本：简单项目 1-2 小时，自定义着色器 1-2 天

> [!warning] CADPilot 影响
> `DfamShader.ts` 中的自定义 ShaderMaterial 需要迁移到 TSL（WebGPURenderer 不支持 ShaderMaterial）。

### 3.3 WebAssembly 性能

- 预编译二进制格式，消除 JS 运行时解释开销
- C++/Rust CAD 内核可编译为 WASM，==接近原生性能==
- 多线程 (SharedArrayBuffer + Web Workers) 已全浏览器可用
- Figma 已验证 C++ → WASM (Emscripten) 大规模生产可行性

### 3.4 CSG 布尔运算库

| 库 | 语言 | WASM | 性能 | 说明 |
|----|:----:|:----:|:----:|------|
| [Manifold](https://github.com/elalish/manifold) | C++ | ✅ | ★★★★★ | ==CADPilot 已在用== |
| [three-bvh-csg](https://github.com/gkjohnson/three-bvh-csg) | JS | ❌ | ★★★☆☆ | Three.js 原生集成 |
| @jscad/modeling | JS | 部分 | ★★★☆☆ | OpenJSCAD 生态 |

---

## 4. AI + 3D 编辑集成

### 4.1 行业领先者

> [!example]- Zoo (原 KittyCAD) — 最前沿 AI CAD ⭐⭐
> - **Text-to-CAD**：文本→完整可编辑 B-Rep（非网格），1000 字 prompt
> - **ML-ephant API**：第三方可集成的 CAD 生成 ML API
> - **Zookeeper (2026.01)**：对话式 CAD Agent，类似 Claude Code 的 CAD 版
> - B-Rep 操作全覆盖：基元、草图约束、阵列、壳体、螺旋、圆角/倒角、放样、扫掠
> - ==自研 GPU 原生几何引擎==（非 OCCT）

> [!example]- Autodesk Assistant (Fusion 360) ⭐
> - **Text to 3D Native Geometry**：输入描述→Fusion 画布中原生可编辑 3D 几何
> - **Text to Command**：自然语言→CAD 操作（"add a 0.5mm chamfer to all edges"）
> - AI 模型学习分解和合成面/边/拓扑，可重现 Fusion 命令序列
> - 状态：预览阶段（AU2025 展示）

> [!example]- 其他 AI CAD 工具
> - **AdamCAD** — YC W2025，$4.1M 融资，NL→参数化 CAD
> - **MecAgent** — 集成 SolidWorks/CATIA/Inventor/Fusion/Creo 的 AI Copilot
> - **Siemens Design Copilot** — Solid Edge / NX 集成
> - **Dassault Aura** — SOLIDWORKS 系列 AI 助手

### 4.2 行业趋势

> [!important] 2026 年「混合工作流」正在成为标准

```mermaid
graph LR
    A["1️⃣ AI 生成初版<br/>Text/Image → 3D"] --> B["2️⃣ 人工精调<br/>传统 CAD 编辑"]
    B --> C["3️⃣ AI 辅助验证<br/>标准合规 + 可制造性"]
    C --> D["4️⃣ 导出交付<br/>STEP, 3MF"]
    C -.->|不满意| B

    style A fill:#4a9eff,color:#fff
    style B fill:#ff6b6b,color:#fff
    style C fill:#ffd93d,color:#000
    style D fill:#6bcb77,color:#fff
```

据报告，AI 可将 2D 制造图纸生成时间缩短高达 ==90%==。

---

## 5. B-Rep vs 网格编辑权衡

| 维度 | B-Rep（精确表示） | 网格（三角面片） |
|------|:--:|:--:|
| 精度 | 曲面精确表达 | 近似，取决于细分密度 |
| 编辑性 | 参数修改直观 | 操作顶点，复杂易出错 |
| 适用场景 | 工业 CAD（涡轮、光学） | 游戏资产、有机形态 |
| 浏览器性能 | 依赖 OCCT WASM (~10MB+) | WebGL 原生友好 |
| 文件格式 | STEP、IGES、BREP | STL、OBJ、glTF |
| 浏览器成熟度 | ★★★☆☆ | ★★★★★ |

> [!tip] CADPilot 双路径策略
> - **参数化管道**（text/drawing 输入）→ 保持 ==B-Rep (STEP)==，编辑走后端 CadQuery
> - **有机形态管道**（organic 输入）→ ==网格编辑==走前端 Manifold WASM

---

## 6. 关键技术决策矩阵

| 决策点 | 推荐 | 备选 | 理由 |
|--------|------|------|------|
| CAD 内核 | ==opencascade.js== | Truck (Rust) | 与后端 CadQuery/OCCT 一致 |
| CSG 库 | ==Manifold WASM== | three-bvh-csg | 已在用，性能最优 |
| 渲染器 | ==Three.js WebGPU== | 自定义 WebGPU | 已在用，生态成熟 |
| 架构 | ==混合客户端+服务端== | 纯客户端 | 复用现有后端 CadQuery |
| 草图编辑器 | 视 Phase 进度 | 自研 / 集成 JSketcher | Phase C+ 再决定 |
| 操作历史 | ==自研 Command Pattern== | 集成现有库 | 简单可控 |

---

## 参考链接

> [!quote]- 开源项目
> - [opencascade.js](https://github.com/donalffons/opencascade.js/) · [occt-import-js](https://github.com/kovacsv/occt-import-js) · [CascadeStudio](https://github.com/zalo/CascadeStudio)
> - [JSketcher](https://github.com/xibyte/jsketcher) · [BREP.io](https://github.com/mmiscool/BREP.io) · [Chili3D](https://github.com/xiangechen/chili3d)
> - [Three.cad](https://github.com/twpride/three.cad) · [Chokoku CAD](https://github.com/itta611/ChokokuCAD)
> - [CADmium](https://github.com/CADmium-Co/CADmium) · [Truck](https://github.com/ricosjp/truck) · [Fornjot](https://www.fornjot.app/)
> - [Manifold](https://github.com/elalish/manifold) · [three-bvh-csg](https://github.com/gkjohnson/three-bvh-csg)

> [!quote]- 商业平台与 AI CAD
> - [Onshape](https://www.ptc.com/en/products/onshape) · [Shapr3D](https://www.shapr3d.com/) · [Tinkercad](https://www.tinkercad.com/) · [Clara.io](https://clara.io/)
> - [Zoo Text-to-CAD](https://zoo.dev/blog/introducing-text-to-cad) · [Zoo Zookeeper](https://zoo.dev/blog/zoo-design-studio-v1)
> - [Autodesk Assistant AI](https://www.autodesk.com/products/fusion-360/blog/autodesk-assistant-ai/)
> - [AdamCAD](https://techcrunch.com/2025/10/31/yc-alum-adam-raises-4-1m-to-turn-viral-text-to-3d-tool-into-ai-copilot/) · [MecAgent](https://mecagent.com/)

> [!quote]- 技术文章
> - [WebAssembly for CAD](https://altersquare.medium.com/webassembly-for-cad-applications-when-javascript-isnt-fast-enough-56fcdc892004)
> - [Three.js 2026 WebGPU](https://www.utsubo.com/blog/threejs-2026-what-changed) · [迁移指南](https://www.utsubo.com/blog/webgpu-threejs-migration-guide)
> - [TSL 与 WebGPU](https://blog.maximeheckel.com/posts/field-guide-to-tsl-and-webgpu/) · [Figma WebGPU](https://www.figma.com/blog/figma-rendering-powered-by-webgpu/)
> - [Onshape Mixed Modeling](https://www.onshape.com/en/blog/mixed-modeling-brep-geometry-mesh-data)

---

> [!info] 继续阅读
> → [[architecture-design|混合分层架构设计]] · → [[implementation-roadmap|分阶段实施路线图]]
