"""Few-shot examples for plate parts."""

from ._base import TaggedExample

PLATE_EXAMPLES: list[TaggedExample] = [
    TaggedExample(
        description="矩形安装板：200x150x10，四角4×φ12安装孔，中心φ60通孔",
        code="""\
import cadquery as cq

length, width, thickness = 200, 150, 10
hole_d, center_hole_d = 12, 60
margin = 20

result = (cq.Workplane("XY")
    .box(length, width, thickness)
    .faces(">Z").workplane()
    .hole(center_hole_d)
    .faces(">Z").workplane()
    .rect(length - 2*margin, width - 2*margin, forConstruction=True)
    .vertices()
    .hole(hole_d))

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "hole_pattern", "bore"}),
    ),
    TaggedExample(
        description="圆形法兰板：φ160，厚12，中心孔φ40，6×φ12螺栓孔PCD110，外缘R3圆角",
        code="""\
import cadquery as cq
import math

d_flange, thickness = 160, 12
d_bore = 40
n_bolts, d_bolt, pcd = 6, 12, 110
fillet_r = 3

result = cq.Workplane("XY").circle(d_flange / 2).extrude(thickness)
result = result.faces(">Z").workplane().hole(d_bore)

# 均布螺栓孔
for i in range(n_bolts):
    angle = math.radians(i * 360 / n_bolts)
    x, y = (pcd / 2) * math.cos(angle), (pcd / 2) * math.sin(angle)
    hole = cq.Workplane("XY").center(x, y).circle(d_bolt / 2).extrude(thickness + 1)
    result = result.cut(hole)

# 外缘圆角
try:
    result = result.edges(">Z").fillet(fillet_r)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "hole_pattern", "bore", "fillet"}),
    ),
    TaggedExample(
        description="T形槽工作台板：300x150x25，3条纵向T形槽（槽口12×8，槽底20×12）",
        code="""\
import cadquery as cq

length, width, thickness = 300, 150, 25
slot_top_w, slot_top_d = 12, 8    # 槽口：宽×深
slot_bot_w, slot_bot_d = 20, 12   # 槽底：宽×深（继续向下）

result = cq.Workplane("XY").box(length, width, thickness)

# 3条纵向T形槽，Y方向均布
for y in [-width / 4, 0, width / 4]:
    # 上部窄槽
    result = (result.faces(">Z").workplane()
        .center(0, y)
        .rect(length + 1, slot_top_w)
        .cutBlind(slot_top_d))
    # 下部扩宽槽（从窄槽底部继续切）
    result = (result.faces(">Z").workplane(offset=-slot_top_d)
        .center(0, y)
        .rect(length + 1, slot_bot_w)
        .cutBlind(slot_bot_d))

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "slot"}),
    ),
    TaggedExample(
        description="带加强筋底板：200x150x8，3条纵向筋高20厚6，四角M10安装孔",
        code="""\
import cadquery as cq

length, width, plate_t = 200, 150, 8
rib_h, rib_t = 20, 6
hole_d, margin = 10, 15

# 底板
result = cq.Workplane("XY").box(length, width, plate_t)

# 纵向加强筋（从底板上表面向上生长）
for x in [-length / 4, 0, length / 4]:
    result = (result.faces(">Z").workplane()
        .center(x, 0)
        .rect(rib_t, width)
        .extrude(rib_h))

# 安装孔（底面四角）
result = (result.faces("<Z").workplane()
    .rect(length - 2 * margin, width - 2 * margin, forConstruction=True)
    .vertices().hole(hole_d))

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "rib", "hole_pattern"}),
    ),
    TaggedExample(
        description="带沉头孔的安装板：180x120x12，四角4×φ6.5沉头孔（沉头φ12深6），中心开槽50x20深5，R3外缘圆角",
        code="""\
import cadquery as cq

# 尺寸参数
length, width, thickness = 180, 120, 12
hole_d = 6.5
cbore_d, cbore_depth = 12, 6
slot_l, slot_w, slot_d = 50, 20, 5
margin = 15
fillet_r = 3

# 底板
result = cq.Workplane("XY").box(length, width, thickness)

# 四角沉头孔
result = (result.faces(">Z").workplane()
    .rect(length - 2 * margin, width - 2 * margin, forConstruction=True)
    .vertices()
    .cboreHole(hole_d, cbore_d, cbore_depth))

# 中心开槽
result = (result.faces(">Z").workplane()
    .rect(slot_l, slot_w)
    .cutBlind(-slot_d))

# 外缘圆角
try:
    result = result.edges("|Z").fillet(fillet_r)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "counterbore", "slot", "fillet"}),
    ),
    TaggedExample(
        description="L形切角板：外廓150x100x10，切去右上角60x40三角形，6×φ8安装孔均布",
        code="""\
import cadquery as cq

# 尺寸参数
length, width, thickness = 150, 100, 10
cut_x, cut_y = 60, 40  # 右上角切除尺寸
hole_d = 8
n_holes = 6

# L形轮廓（从左下角逆时针）
pts = [
    (0, 0),
    (length, 0),
    (length, width - cut_y),
    (length - cut_x, width),
    (0, width),
]
result = cq.Workplane("XY").polyline(pts).close().extrude(thickness)

# 沿左侧和底部均布安装孔
hole_positions = [
    (20, 20),
    (75, 20),
    (130, 20),
    (20, 80),
    (75, 60),
    (120, 50),
]
for px, py in hole_positions:
    hole = cq.Workplane("XY").center(px, py).circle(hole_d / 2).extrude(thickness + 1)
    result = result.cut(hole)

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "polyline", "hole_pattern"}),
    ),
    TaggedExample(
        description="圆环垫板：外径φ120，内径φ60，厚8，8×φ8均布螺栓孔PCD90，上下面C0.5倒角",
        code="""\
import cadquery as cq
import math

# 尺寸参数
d_outer, d_inner = 120, 60
thickness = 8
n_bolts, d_bolt, pcd = 8, 8, 90
chamfer = 0.5

# 圆环基体
result = cq.Workplane("XY").circle(d_outer / 2).circle(d_inner / 2).extrude(thickness)

# 均布螺栓孔
for i in range(n_bolts):
    angle = math.radians(i * 360 / n_bolts)
    x, y = (pcd / 2) * math.cos(angle), (pcd / 2) * math.sin(angle)
    hole = cq.Workplane("XY").center(x, y).circle(d_bolt / 2).extrude(thickness + 1)
    result = result.cut(hole)

# 上下面倒角
try:
    result = result.edges(">Z").chamfer(chamfer)
    result = result.edges("<Z").chamfer(chamfer)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "bore", "hole_pattern", "chamfer"}),
    ),
]
