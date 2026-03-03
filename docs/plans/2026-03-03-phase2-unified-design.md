# Phase 2 统一设计：boolean_assemble + slice_to_gcode + generate_raw_mesh

> 基于 `docs/plans/end-to-end-architecture/2026-03-02-dual-channel-pipeline-design.md` 的提案 3/4/5 合并设计。
> 经头脑风暴确认三项架构决策后产出。

---

## 架构决策记录

| # | 决策 | 结论 | 理由 |
|---|------|------|------|
| ADR-1 | generate_raw_mesh 与现有 generate_organic_mesh 的关系 | 重构现有节点，策略=模型选择（Hunyuan3D/Tripo3D/SPAR3D/TRELLIS），部署=配置驱动（SaaS/本地） | 节点按目的区分，同一模型的 SaaS/本地是部署配置而非架构区分 |
| ADR-2 | export_formats 节点定位 | 从管线移除，格式转换下沉为基础设施工具函数 + API 端点 | 格式转换不改变数据本身，不是管线目的；管线应以节点为导出时机，任意节点后可导出产物 |
| ADR-3 | mesh_scale 定位 | 保留为简单节点，不需要策略模式 | 均匀缩放是独立目的，但复杂度不足以需要多策略 |

---

## 目标管线拓扑

Phase 2 完成后的 organic 管线：

```
create_job → analyze_organic → confirm_with_user
  → generate_raw_mesh        # 提案5: 策略化多模型生成
    → mesh_healer            # ✅ Phase 1 已完成
      → mesh_scale           # 简单节点，均匀缩放
        → boolean_assemble   # 提案3: manifold3d 布尔运算
          → [slice_to_gcode] # 提案4: 可选，PrusaSlicer CLI
            → finalize

基础设施层（不在图中）：
  convert_mesh(asset_key, format) → 任意节点产物的格式转换
  GET /api/jobs/{id}/assets/{key}?format=stl → 导出下载
```

### 变更摘要

| 变更 | 说明 |
|------|------|
| `generate_organic_mesh` → `generate_raw_mesh` | 重构为策略化节点 |
| `boolean_cuts` → `boolean_assemble` | stub → manifold3d 实现 |
| `export_formats` | 删除，格式转换下沉为基础设施 |
| `slice_to_gcode` | 新增可选节点 |
| `postprocess_organic_node` | 废弃（功能已拆到独立节点） |

---

## 三层架构模型

```
Layer 1: LangGraph 节点 = 目的（做什么）
  └─ Layer 2: 策略 = 功能（怎么做）— 可顺序/fallback
       └─ Layer 3: 部署方式 = SaaS API / 本地模型 — 由配置决定
```

每一层的变更只影响该层：

| 变更类型 | 影响范围 | 操作 |
|---------|---------|------|
| 新增节点（新目的） | 图层 | 注册新节点 + 连接 requires/produces |
| 新增工具（新功能） | 策略层 | 在节点的 strategies 中添加一项 |
| 新增部署方式 | 配置层 | 在策略内部添加 provider 适配器 |
| 切换工具/部署 | pipeline_config | 改配置文件，零代码改动 |

---

## 提案 5：generate_raw_mesh — 策略化多模型生成

### 节点注册

```python
@register_node(
    name="generate_raw_mesh",
    display_name="网格生成",
    requires=["confirmed_params"],
    produces=["raw_mesh"],
    input_types=["organic"],
    config_model=GenerateRawMeshConfig,
    strategies={
        "hunyuan3d": Hunyuan3DGenerateStrategy,
        "tripo3d":   Tripo3DGenerateStrategy,
        "spar3d":    SPAR3DGenerateStrategy,
        "trellis":   TRELLISGenerateStrategy,
    },
    fallback_chain=["hunyuan3d", "tripo3d", "spar3d", "trellis"],
    default_strategy="hunyuan3d",
)
async def generate_raw_mesh_node(ctx: NodeContext) -> None:
    strategy = ctx.get_strategy()
    await strategy.execute(ctx)
```

### 策略内部：双部署适配

每个策略内部按配置选择 SaaS 或本地部署：

```python
class Hunyuan3DGenerateStrategy(NodeStrategy):
    async def execute(self, ctx):
        config = ctx.config
        if config.hunyuan3d_endpoint:
            # 本地部署：统一 /v1/generate 接口
            result = await self._call_local(config.hunyuan3d_endpoint, ctx)
        elif config.hunyuan3d_api_key:
            # SaaS 部署：复用现有 HunyuanProvider
            provider = HunyuanProvider(api_key=config.hunyuan3d_api_key, ...)
            result = await provider.generate(spec, reference_image, on_progress)
        else:
            raise ValueError("Hunyuan3D: 未配置 endpoint 或 api_key")

        ctx.put_asset("raw_mesh", str(result), "glb")

    def check_available(self) -> bool:
        config = self.config
        has_local = bool(getattr(config, "hunyuan3d_endpoint", None))
        has_saas = bool(getattr(config, "hunyuan3d_api_key", None))
        if has_local:
            return self._health_check(config.hunyuan3d_endpoint)
        return has_saas
```

SPAR3D/TRELLIS 只有本地部署（无 SaaS），Tripo3D 只有 SaaS（无开源权重）。策略内部自然处理。

### Config 模型

```python
class GenerateRawMeshConfig(BaseNodeConfig):
    strategy: str = "hunyuan3d"

    # Hunyuan3D（SaaS + 本地）
    hunyuan3d_api_key: str | None = None
    hunyuan3d_endpoint: str | None = None

    # Tripo3D（SaaS only）
    tripo3d_api_key: str | None = None

    # SPAR3D（本地 only）
    spar3d_endpoint: str | None = None

    # TRELLIS（本地 only）
    trellis_endpoint: str | None = None

    # 通用
    timeout: int = 120
    output_format: str = "glb"
```

### 现有代码复用

| 现有代码 | 复用方式 |
|---------|---------|
| `MeshProvider` ABC | 保留，作为 SaaS 适配器的接口 |
| `TripoProvider` | 被 Tripo3DGenerateStrategy 内部调用 |
| `HunyuanProvider` | 被 Hunyuan3DGenerateStrategy 内部调用 |
| `AutoProvider` | 删除，被 `fallback_chain` 替代 |
| 节点内 SSE 进度 | 改用 `ctx.dispatch_progress()` |

### Legacy 兼容

`generate_organic_mesh_node` 保留为别名，内部委托给 `generate_raw_mesh_node`，确保 `builder_legacy.py` 不中断。完整迁移后再移除。

---

## 提案 3：boolean_assemble — 布尔装配

### 节点注册

```python
@register_node(
    name="boolean_assemble",
    display_name="布尔装配",
    requires=["scaled_mesh"],
    produces=["final_mesh"],
    input_types=["organic"],
    config_model=BooleanAssembleConfig,
    strategies={
        "manifold3d": Manifold3DStrategy,
    },
    default_strategy="manifold3d",
)
async def boolean_assemble_node(ctx: NodeContext) -> None:
    if not ctx.has_asset("scaled_mesh"):
        ctx.put_data("boolean_assemble_status", "skipped_no_input")
        return
    strategy = ctx.get_strategy()
    await strategy.execute(ctx)
```

### 流形校验门

`Manifold3DStrategy.execute()` 内部流程：

```
输入网格 → is_manifold_check()
  ├─ 通过 → 直接执行布尔运算
  └─ 未通过 → force_voxelize()（MeshLib 体素化重采样）
                └─ 再次 is_manifold_check()
                     ├─ 通过 → 执行布尔运算
                     └─ 未通过 → 跳过布尔，警告传递原网格
```

### 现有代码复用

| 现有代码 | 处理 |
|---------|------|
| `MeshPostProcessor.apply_boolean_cuts()` | 核心逻辑提取到 `Manifold3DStrategy` |
| `boolean_cuts` stub 节点 | 删除，被 `boolean_assemble` 替代 |
| `EngineeringCut` 模型（FlatBottom/Hole/Slot） | 保留不变 |

### Config 模型

```python
class BooleanAssembleConfig(BaseNodeConfig):
    strategy: str = "manifold3d"
    voxel_resolution: int = 128
    skip_on_non_manifold: bool = False
```

---

## 提案 4：slice_to_gcode + 导出基础设施

### 格式转换基础设施（不是节点）

**工具函数**：

```python
# backend/core/mesh_converter.py
def convert_mesh(input_path: Path, output_format: str, output_dir: Path) -> Path:
    """网格格式转换：OBJ/GLB/STL/3MF 互转。"""
    mesh = trimesh.load(input_path, force="mesh")
    output_path = output_dir / f"model.{output_format}"
    mesh.export(str(output_path), file_type=output_format)
    return output_path
```

**API 端点**：

```python
# backend/api/routes/export.py
@router.get("/api/jobs/{job_id}/assets/{asset_key}")
async def export_asset(job_id: str, asset_key: str, format: str = "glb"):
    """任意节点产物的按需格式转换下载。"""
    asset = get_asset_from_registry(job_id, asset_key)
    if asset.format == format:
        return FileResponse(asset.path)
    converted = convert_mesh(Path(asset.path), format, tmp_dir)
    return FileResponse(converted)
```

前端 GLB 预览：每个节点完成的 `node.completed` SSE 事件中已携带 asset 信息，前端可用 asset_key 请求 GLB 预览。

### slice_to_gcode 节点

```python
@register_node(
    name="slice_to_gcode",
    display_name="切片出码",
    requires=[["final_mesh", "scaled_mesh", "watertight_mesh"]],  # OR 依赖
    produces=["gcode_bundle"],
    input_types=["organic"],
    config_model=SliceToGcodeConfig,
    strategies={
        "prusaslicer": PrusaSlicerStrategy,
        "orcaslicer":  OrcaSlicerStrategy,
    },
    default_strategy="prusaslicer",
    fallback_chain=["prusaslicer", "orcaslicer"],
)
async def slice_to_gcode_node(ctx: NodeContext) -> None:
    mesh_key = _pick_best_mesh(ctx)
    if not mesh_key:
        ctx.put_data("slice_status", "skipped_no_mesh")
        return
    strategy = ctx.get_strategy()
    await strategy.execute(ctx)
```

### PrusaSlicerStrategy 核心

```python
class PrusaSlicerStrategy(NodeStrategy):
    def check_available(self) -> bool:
        return shutil.which("prusa-slicer") is not None

    async def execute(self, ctx):
        mesh_path = self._get_mesh_path(ctx)
        config = ctx.config
        cmd = [
            "prusa-slicer", "--export-gcode",
            "--layer-height", str(config.layer_height),
            "--fill-density", f"{config.fill_density}%",
            "--output", str(output_path),
            str(mesh_path),
        ]
        if config.support_material:
            cmd.extend(["--support-material"])

        proc = await asyncio.create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=config.timeout)

        gcode_meta = parse_gcode_metadata(output_path)
        ctx.put_asset("gcode_bundle", str(output_path), "gcode", metadata=gcode_meta)
```

### Config 模型

```python
class SliceToGcodeConfig(BaseNodeConfig):
    strategy: str = "prusaslicer"
    layer_height: float = 0.2
    fill_density: int = 20
    support_material: bool = False
    nozzle_diameter: float = 0.4
    filament_type: str = "PLA"
    timeout: int = 30
```

---

## 实施顺序（方案 A 串行）

```
Step 1: 导出基础设施                    ~4 tasks
  ├─ convert_mesh() 工具函数
  ├─ /api/jobs/{id}/assets/{key} 端点
  ├─ 删除 export_formats 节点
  └─ 更新 resolver + 测试

Step 2: boolean_assemble               ~6 tasks
  ├─ Manifold3DStrategy（提取现有逻辑）
  ├─ 流形校验门 + 体素化修复
  ├─ Config 模型
  ├─ 删除 boolean_cuts stub
  └─ 测试

Step 3: generate_raw_mesh              ~12 tasks
  ├─ GenerateRawMeshConfig
  ├─ 策略适配器（包装现有 SaaS providers）
  ├─ 本地部署适配器（/v1/generate）
  ├─ 节点迁移 CadJobState → NodeContext
  ├─ SSE 事件 + HITL 兼容
  ├─ Legacy 别名兼容层
  └─ 测试

Step 4: slice_to_gcode                 ~8 tasks
  ├─ PrusaSlicerStrategy（CLI 调用）
  ├─ OrcaSlicerStrategy（CLI 调用）
  ├─ G-code 元数据解析
  ├─ Config 模型
  └─ 测试

Step 5: 集成验证 + Legacy 废弃         ~4 tasks
  ├─ 端到端集成测试（完整管线跑通）
  ├─ 废弃 postprocess_organic_node
  ├─ 清理 AutoProvider
  └─ 更新文档
```

总计约 ~34 tasks。

---

## Legacy 废弃策略

Phase 2 期间（共存期）：

```
builder_legacy.py → 仍用旧路径
   analyze_organic → generate_organic_mesh → postprocess_organic

builder_new.py → 用新路径
   analyze_organic → generate_raw_mesh → mesh_healer → mesh_scale
     → boolean_assemble → [slice_to_gcode] → finalize
```

Step 3 完成后：`generate_organic_mesh_node` = `generate_raw_mesh_node` 的别名。

Step 5 完成后：`postprocess_organic_node` 标记 `@deprecated`，builder_legacy 切换到新路径或删除。

---

## 不在 Phase 2 范围内

| 项 | 原因 |
|---|------|
| SPAR3D/TRELLIS 模型部署文档 | 运维侧，非管线代码 |
| 前端导出 UI 改造 | 前端单独迭代 |
| mesh_scale 复杂策略 | YAGNI，均匀缩放够用 |
| Phase 3 节点（lattice/orientation/thermal/supports） | 后续提案 |
