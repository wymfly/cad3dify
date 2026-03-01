"""Few-shot examples for bracket parts."""

from ._base import TaggedExample

BRACKET_EXAMPLES: list[TaggedExample] = [
    TaggedExample(
        description="L 形支架：底板100x80x10，立板80x60x10，底板4孔，立板2孔",
        code="""\
import cadquery as cq

# 底板
base_l, base_w, base_t = 100, 80, 10
# 立板
wall_h, wall_t = 60, 10

# L 形截面 extrude
pts = [
    (0, 0), (base_l, 0), (base_l, base_t),
    (wall_t, base_t), (wall_t, base_t + wall_h), (0, base_t + wall_h),
]
result = cq.Workplane("XZ").polyline(pts).close().extrude(base_w)

# 底板安装孔
result = (result.faces("<Z").workplane()
    .rect(base_l - 20, base_w - 20, forConstruction=True)
    .vertices().hole(10))

# 立板安装孔
result = (result.faces("<X").workplane()
    .center(0, wall_h/2 + base_t/2)
    .rect(base_w - 30, wall_h - 20, forConstruction=True)
    .vertices().hole(8))

# 内角圆角
try:
    result = result.edges(cq.selectors.NearestToPointSelector((wall_t/2, base_w/2, base_t))).fillet(5)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "hole_pattern", "fillet"}),
    ),
    TaggedExample(
        description="U形槽架：总宽100，通道高60，深70，壁厚10，底部4×φ8安装孔",
        code="""\
import cadquery as cq

# U 形截面参数
outer_w, channel_h, depth = 100, 60, 70
wall_t = 10

# U 形截面（在 XZ 平面绘制：X 为宽，Z 为高）
pts = [
    (0, 0),
    (outer_w, 0),
    (outer_w, channel_h),
    (outer_w - wall_t, channel_h),
    (outer_w - wall_t, wall_t),
    (wall_t, wall_t),
    (wall_t, channel_h),
    (0, channel_h),
]
result = cq.Workplane("XZ").polyline(pts).close().extrude(depth)

# 底部安装孔（4角均布）
result = (result.faces("<Z").workplane()
    .rect(outer_w - 20, depth - 20, forConstruction=True)
    .vertices().hole(8))

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "slot", "hole_pattern"}),
    ),
    TaggedExample(
        description="T形腹板支架：底板150x60x10，中央立筋高80厚10，底板4×M10安装孔",
        code="""\
import cadquery as cq

# 底板参数
base_l, base_w, base_t = 150, 60, 10
# 立筋参数
rib_h, rib_t = 80, 10

# 底板
result = cq.Workplane("XY").box(base_l, base_w, base_t)

# 中央立筋（从底板顶面向上生长）
result = (result.faces(">Z").workplane()
    .center(0, 0)
    .rect(rib_t, base_w)
    .extrude(rib_h))

# 底板安装孔（4角）
result = (result.faces("<Z").workplane()
    .rect(base_l - 20, base_w - 20, forConstruction=True)
    .vertices().hole(10))

# 底板-立筋接合处圆角
try:
    result = result.edges(
        cq.selectors.NearestToPointSelector((0, 0, base_t / 2))
    ).fillet(5)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "hole_pattern", "fillet"}),
    ),
    TaggedExample(
        description="带加强筋的L型支架：底板120x80x10，立板80x70x10，三角筋50x50x8，底板4×φ10孔，立板2×φ8孔，R5圆角",
        code="""\
import cadquery as cq

# 底板参数
base_l, base_w, base_t = 120, 80, 10
# 立板参数
wall_h, wall_t = 70, 10
# 三角加强筋
rib_l, rib_h, rib_t = 50, 50, 8
fillet_r = 5

# L 形截面 extrude
pts = [
    (0, 0), (base_l, 0), (base_l, base_t),
    (wall_t, base_t), (wall_t, base_t + wall_h), (0, base_t + wall_h),
]
result = cq.Workplane("XZ").polyline(pts).close().extrude(base_w)

# 三角加强筋（内角三角形截面）
rib_pts = [
    (wall_t, base_t),
    (wall_t + rib_l, base_t),
    (wall_t, base_t + rib_h),
]
rib = (cq.Workplane("XZ")
    .polyline(rib_pts).close()
    .extrude(rib_t))
# 居中放置加强筋
rib = rib.translate((0, (base_w - rib_t) / 2, 0))
result = result.union(rib)

# 内角圆角
try:
    result = result.edges(
        cq.selectors.NearestToPointSelector((wall_t / 2, base_w / 2, base_t))
    ).fillet(fillet_r)
except Exception:
    pass

# 底板安装孔
result = (result.faces("<Z").workplane()
    .rect(base_l - 20, base_w - 20, forConstruction=True)
    .vertices().hole(10))

# 立板安装孔
result = (result.faces("<X").workplane()
    .center(0, wall_h / 2 + base_t / 2)
    .rect(base_w - 30, wall_h - 20, forConstruction=True)
    .vertices().hole(8))

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "union", "rib", "hole_pattern", "fillet"}),
    ),
    TaggedExample(
        description="三角支撑架：底边120，高80，厚15，直角三角形截面，底部3×φ10安装孔，斜边C2倒角",
        code="""\
import cadquery as cq

# 三角截面参数
base_len = 120
tri_height = 80
depth = 15
hole_d = 10
chamfer = 2

# 直角三角形截面（在XZ平面）
pts = [
    (0, 0),
    (base_len, 0),
    (0, tri_height),
]
result = cq.Workplane("XZ").polyline(pts).close().extrude(depth)

# 底部安装孔（沿底边均布3个）
hole_spacing = base_len / 4
for i in range(3):
    hx = hole_spacing * (i + 1)
    hole = (cq.Workplane("XY")
        .center(hx, depth / 2)
        .circle(hole_d / 2)
        .extrude(5 + 1))
    result = result.cut(hole)

# 斜边倒角
try:
    result = result.edges(
        cq.selectors.NearestToPointSelector((base_len / 2, depth / 2, tri_height / 2))
    ).chamfer(chamfer)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "polyline", "hole_pattern", "chamfer"}),
    ),
    TaggedExample(
        description="角钢支架：等边角钢L50x50x5，长200，两端各2×φ9安装孔",
        code="""\
import cadquery as cq

# 角钢参数
flange = 50       # 翼缘宽
wall_t = 5        # 壁厚
total_length = 200
hole_d = 9
hole_margin = 20  # 孔距端面

# 角钢 L 形截面（XZ 平面）
pts = [
    (0, 0),
    (flange, 0),
    (flange, wall_t),
    (wall_t, wall_t),
    (wall_t, flange),
    (0, flange),
]
result = cq.Workplane("XZ").polyline(pts).close().extrude(total_length)

# 水平翼缘安装孔（底面，两端各1个）
for y_pos in [hole_margin, total_length - hole_margin]:
    hole = (cq.Workplane("XY")
        .center(flange / 2, y_pos)
        .circle(hole_d / 2)
        .extrude(wall_t + 1))
    result = result.cut(hole)

# 垂直翼缘安装孔（侧面，两端各1个）
for y_pos in [hole_margin, total_length - hole_margin]:
    hole = (cq.Workplane("XZ")
        .center(0, flange / 2)
        .workplane(offset=y_pos)
        .center(0, 0)
        .circle(hole_d / 2)
        .extrude(wall_t + 1))
    result = result.cut(hole)

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "polyline", "hole_pattern"}),
    ),
]
