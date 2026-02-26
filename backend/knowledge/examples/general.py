"""Few-shot examples for general / miscellaneous parts."""

from ._base import TaggedExample

GENERAL_EXAMPLES: list[TaggedExample] = [
    TaggedExample(
        description="空心管件：外径φ60，内径φ50，长200，两端倒角C1",
        code="""\
import cadquery as cq

# 管件参数
d_outer, d_inner = 60, 50
length = 200
chamfer = 1

r_outer, r_inner = d_outer / 2, d_inner / 2

# 薄壁轮廓
profile_pts = [
    (r_inner, 0),
    (r_outer, 0),
    (r_outer, length),
    (r_inner, length),
]
result = (cq.Workplane("XZ").polyline(profile_pts).close()
    .revolve(360, (0, 0, 0), (0, 1, 0)))

# 两端倒角
try:
    result = result.edges("<Y").chamfer(chamfer)
    result = result.edges(">Y").chamfer(chamfer)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"revolve", "bore", "chamfer"}),
    ),
    TaggedExample(
        description="矩形块体：100x80x40，顶面2×2排列4×φ8通孔，侧面2×φ6螺孔深15",
        code="""\
import cadquery as cq

length, width, height = 100, 80, 40
top_hole_d = 8
side_hole_d, side_hole_depth = 6, 15

result = cq.Workplane("XY").box(length, width, height)

# 顶面通孔（2×2均布）
result = (result.faces(">Z").workplane()
    .rect(length - 30, width - 30, forConstruction=True)
    .vertices().hole(top_hole_d))

# 侧面螺孔
result = (result.faces(">Y").workplane()
    .rect(length - 40, height - 20, forConstruction=True)
    .vertices().hole(side_hole_d, depth=side_hole_depth))

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "hole_pattern"}),
    ),
    TaggedExample(
        description="带圆角倒角实体：60x50x30，竖棱R5圆角，顶面R3圆角，底面C1倒角",
        code="""\
import cadquery as cq

length, width, height = 60, 50, 30
vertical_fillet = 5
top_fillet = 3
bottom_chamfer = 1

result = cq.Workplane("XY").box(length, width, height)

# 竖向棱（四条竖边）圆角
try:
    result = result.edges("|Z").fillet(vertical_fillet)
except Exception:
    pass

# 顶面圆角
try:
    result = result.edges(">Z").fillet(top_fillet)
except Exception:
    pass

# 底面倒角
try:
    result = result.edges("<Z").chamfer(bottom_chamfer)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "fillet", "chamfer"}),
    ),
    TaggedExample(
        description="六角螺母：对边距30（M20），高16，中心螺纹孔φ20",
        code="""\
import cadquery as cq
import math

# 六角螺母参数
across_flats = 30   # 对边距（S尺寸）
height = 16
bore_d = 20         # 螺纹公称直径
chamfer = 1

# 对角距 = 对边距 / cos(30°)
across_corners = across_flats / math.cos(math.radians(30))

# 正六边形截面 extrude
result = (cq.Workplane("XY")
    .polygon(6, across_corners)
    .extrude(height))

# 中心螺纹孔
result = result.faces(">Z").workplane().hole(bore_d)

# 上下倒角
try:
    result = result.edges(">Z").chamfer(chamfer)
    result = result.edges("<Z").chamfer(chamfer)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "polygon", "bore", "chamfer"}),
    ),
    TaggedExample(
        description="T形块：底座80x60x20，立柱30x60x40居中，顶部R3圆角，底部4×φ8安装孔",
        code="""\
import cadquery as cq

# 底座参数
base_l, base_w, base_h = 80, 60, 20
# 立柱参数
col_l, col_w, col_h = 30, 60, 40
hole_d = 8
margin = 12
fillet_r = 3

# 1. 底座
result = cq.Workplane("XY").box(base_l, base_w, base_h)

# 2. 立柱（从底座顶面居中向上生长）
column = (cq.Workplane("XY")
    .workplane(offset=base_h / 2)
    .box(col_l, col_w, col_h))
result = result.union(column)

# 3. 立柱顶部圆角
try:
    result = result.edges(">Z").fillet(fillet_r)
except Exception:
    pass

# 4. 底座安装孔（四角）
result = (result.faces("<Z").workplane()
    .rect(base_l - 2 * margin, base_w - 2 * margin, forConstruction=True)
    .vertices().hole(hole_d))

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "union", "fillet", "hole_pattern"}),
    ),
    TaggedExample(
        description="阶梯垫块：底层60x60x10，中层40x40x15居中，顶层20x20x10居中，各层过渡R2圆角",
        code="""\
import cadquery as cq

# 三层参数
layers = [
    (60, 60, 10),  # 底层 (l, w, h)
    (40, 40, 15),  # 中层
    (20, 20, 10),  # 顶层
]
fillet_r = 2

# 逐层构建并 union
result = cq.Workplane("XY").box(layers[0][0], layers[0][1], layers[0][2])
z_offset = layers[0][2] / 2
for l, w, h in layers[1:]:
    block = (cq.Workplane("XY")
        .workplane(offset=z_offset)
        .box(l, w, h))
    result = result.union(block)
    z_offset += h

# 各层过渡圆角
try:
    result = result.edges("|Z").fillet(fillet_r)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "union", "fillet"}),
    ),
]
