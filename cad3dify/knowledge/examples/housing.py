"""Few-shot examples for housing/enclosure parts."""

from ._base import TaggedExample

HOUSING_EXAMPLES: list[TaggedExample] = [
    TaggedExample(
        description="矩形箱体：120x80x60，壁厚3，顶面开口，四角安装凸台",
        code="""\
import cadquery as cq

length, width, height = 120, 80, 60
wall_t = 3
boss_d, boss_h = 12, 5

# 箱体 + 抽壳
result = (cq.Workplane("XY")
    .box(length, width, height)
    .faces(">Z").shell(-wall_t))

# 底部安装凸台
result = (result.faces("<Z").workplane(invert=True)
    .rect(length - 15, width - 15, forConstruction=True)
    .vertices()
    .circle(boss_d/2).extrude(boss_h)
    .faces("<Z").workplane(invert=True)
    .rect(length - 15, width - 15, forConstruction=True)
    .vertices()
    .hole(5))

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "shell", "boss", "hole_pattern"}),
    ),
    TaggedExample(
        description="圆柱壳体：外径φ100，高80，壁厚4，顶面开口，底部4个安装凸台",
        code="""\
import cadquery as cq

d_outer, height = 100, 80
wall_t = 4
boss_d, boss_h = 14, 5
n_boss, pcd = 4, 70  # 凸台分布圆径
boss_hole_d = 8

# 圆柱 + 抽壳（顶面开口）
result = cq.Workplane("XY").circle(d_outer / 2).extrude(height)
result = result.faces(">Z").shell(-wall_t)

# 底部安装凸台
result = (result.faces("<Z").workplane(invert=True)
    .polarArray(pcd / 2, 0, 360, n_boss)
    .circle(boss_d / 2).extrude(boss_h))

# 安装螺孔
result = (result.faces("<Z").workplane(invert=True)
    .polarArray(pcd / 2, 0, 360, n_boss)
    .hole(boss_hole_d))

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"revolve", "shell", "boss", "hole_pattern"}),
    ),
    TaggedExample(
        description="控制器外壳：120x80x40，壁厚2，顶面开口，底部4个M3内侧安装柱",
        code="""\
import cadquery as cq

length, width, height = 120, 80, 40
wall_t = 2
standoff_h, standoff_od = 6, 6
standoff_hole_d = 3.2  # M3 过孔
margin = 8

# 开口箱体
result = (cq.Workplane("XY")
    .box(length, width, height)
    .faces(">Z").shell(-wall_t))

# 内侧安装柱（从内底面向上生长）
inner_z = -height / 2 + wall_t  # 内底面 Z 坐标
for sx, sy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
    cx = sx * (length / 2 - margin)
    cy = sy * (width / 2 - margin)
    boss = (cq.Workplane("XY")
        .workplane(offset=inner_z)
        .center(cx, cy)
        .circle(standoff_od / 2)
        .extrude(standoff_h))
    result = result.union(boss)
    # 安装螺孔（从外底面穿入）
    hole = (cq.Workplane("XY")
        .workplane(offset=-height / 2)
        .center(cx, cy)
        .circle(standoff_hole_d / 2)
        .extrude(wall_t + standoff_h + 1))
    result = result.cut(hole)

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "shell", "boss", "hole_pattern"}),
    ),
    TaggedExample(
        description="带安装耳的壳体：主体100x60x50壁厚3，顶面开口，两侧安装耳30x20x5各带1×φ8孔",
        code="""\
import cadquery as cq

# 主体参数
body_l, body_w, body_h = 100, 60, 50
wall_t = 3
# 安装耳参数
lug_l, lug_w, lug_t = 30, 20, 5
lug_hole_d = 8

# 1. 主体箱体 + 抽壳
result = (cq.Workplane("XY")
    .box(body_l, body_w, body_h)
    .faces(">Z").shell(-wall_t))

# 2. 两侧安装耳
for side in [-1, 1]:
    lug = (cq.Workplane("XY")
        .workplane(offset=-body_h / 2)
        .center(side * (body_l / 2 + lug_l / 2), 0)
        .box(lug_l, lug_w, lug_t))
    result = result.union(lug)

    # 安装耳上的孔
    lug_hole = (cq.Workplane("XY")
        .workplane(offset=-body_h / 2)
        .center(side * (body_l / 2 + lug_l / 2), 0)
        .circle(lug_hole_d / 2)
        .extrude(lug_t + 1))
    result = result.cut(lug_hole)

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "shell", "union", "hole_pattern"}),
    ),
    TaggedExample(
        description="圆柱壳体带法兰：外径φ80高60壁厚3，底部法兰φ110厚8，4×φ10螺栓孔PCD95，顶面开口",
        code="""\
import cadquery as cq
import math

# 参数
d_shell, h_shell = 80, 60
wall_t = 3
d_flange, h_flange = 110, 8
n_bolts, d_bolt, pcd = 4, 10, 95

r_shell = d_shell / 2
r_flange = d_flange / 2

# 1. 法兰底盘
result = cq.Workplane("XY").circle(r_flange).extrude(h_flange)

# 2. 圆柱壳体（从法兰顶面向上生长）
shell_body = (cq.Workplane("XY")
    .workplane(offset=h_flange)
    .circle(r_shell)
    .extrude(h_shell))
result = result.union(shell_body)

# 3. 抽壳（顶面开口）
result = result.faces(">Z").shell(-wall_t)

# 4. 法兰螺栓孔
for i in range(n_bolts):
    angle = math.radians(i * 360 / n_bolts)
    x, y = (pcd / 2) * math.cos(angle), (pcd / 2) * math.sin(angle)
    hole = cq.Workplane("XY").center(x, y).circle(d_bolt / 2).extrude(h_flange + 1)
    result = result.cut(hole)

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "shell", "union", "hole_pattern"}),
    ),
    TaggedExample(
        description="分体式壳体下盖：140x90x30，壁厚2.5，底面封闭顶面开口，四角安装柱φ8高5带M4孔，R2外缘圆角",
        code="""\
import cadquery as cq

# 参数
body_l, body_w, body_h = 140, 90, 30
wall_t = 2.5
post_d, post_h = 8, 5
post_hole_d = 4  # M4
margin = 8
fillet_r = 2

# 1. 箱体 + 抽壳（顶面开口）
result = (cq.Workplane("XY")
    .box(body_l, body_w, body_h)
    .faces(">Z").shell(-wall_t))

# 2. 外缘圆角
try:
    result = result.edges("|Z").fillet(fillet_r)
except Exception:
    pass

# 3. 内侧安装柱（从内底面向上生长）
inner_z = -body_h / 2 + wall_t
for sx, sy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
    cx = sx * (body_l / 2 - margin)
    cy = sy * (body_w / 2 - margin)
    post = (cq.Workplane("XY")
        .workplane(offset=inner_z)
        .center(cx, cy)
        .circle(post_d / 2)
        .extrude(post_h))
    result = result.union(post)

    # 安装螺孔
    hole = (cq.Workplane("XY")
        .workplane(offset=-body_h / 2)
        .center(cx, cy)
        .circle(post_hole_d / 2)
        .extrude(wall_t + post_h + 1))
    result = result.cut(hole)

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"extrude", "shell", "boss", "hole_pattern", "fillet"}),
    ),
]
