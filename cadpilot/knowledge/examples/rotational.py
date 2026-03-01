"""Few-shot examples for rotational and rotational-stepped parts."""

from ._base import TaggedExample

ROTATIONAL_EXAMPLES: list[TaggedExample] = [
    TaggedExample(
        description="三层阶梯法兰盘：φ100/φ40/φ24，中心通孔φ10，6×φ10螺栓孔PCD70，R3圆角",
        code="""\
import cadquery as cq
import math

# 尺寸参数
d_base, d_mid, d_top, d_bore = 100, 40, 24, 10
h_base, h_mid, h_top = 10, 10, 10
n_bolts, d_bolt, pcd = 6, 10, 70
r_fillet = 3

r_base, r_mid, r_top, r_bore = d_base/2, d_mid/2, d_top/2, d_bore/2

# 1. revolve profile 一次成型
profile_pts = [
    (r_bore, 0),
    (r_base, 0),
    (r_base, h_base),
    (r_mid, h_base),
    (r_mid, h_base + h_mid),
    (r_top, h_base + h_mid),
    (r_top, h_base + h_mid + h_top),
    (r_bore, h_base + h_mid + h_top),
]
result = cq.Workplane("XZ").polyline(profile_pts).close().revolve(360, (0,0,0), (0,1,0))

# 2. 阶梯过渡圆角
for pt in [(r_base, 0, h_base), (r_mid, 0, h_base), (r_mid, 0, h_base+h_mid)]:
    try:
        result = result.edges(cq.selectors.NearestToPointSelector(pt)).fillet(r_fillet)
    except Exception:
        pass

# 3. 螺栓孔
for i in range(n_bolts):
    angle = math.radians(i * 360 / n_bolts)
    x, y = (pcd/2) * math.cos(angle), (pcd/2) * math.sin(angle)
    hole = cq.Workplane("XY").center(x, y).circle(d_bolt/2).extrude(h_base + 1)
    result = result.cut(hole)

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"revolve", "stepped", "hole_pattern", "bore", "fillet"}),
    ),
    TaggedExample(
        description="简单轴：总长120，两端φ30轴颈各长25，中间φ50轴身长70，键槽",
        code="""\
import cadquery as cq

# 尺寸参数
d_journal, d_body = 30, 50
l_journal, l_body = 25, 70
total_length = l_journal * 2 + l_body
key_width, key_depth, key_length = 8, 4, 30

r_journal, r_body = d_journal/2, d_body/2

# 1. revolve profile
profile_pts = [
    (0, 0),
    (r_journal, 0),
    (r_journal, l_journal),
    (r_body, l_journal),
    (r_body, l_journal + l_body),
    (r_journal, l_journal + l_body),
    (r_journal, total_length),
    (0, total_length),
]
result = cq.Workplane("XZ").polyline(profile_pts).close().revolve(360, (0,0,0), (0,1,0))

# 2. 过渡圆角
for z in [l_journal, l_journal + l_body]:
    try:
        result = result.edges(cq.selectors.NearestToPointSelector((r_body, 0, z))).fillet(2)
    except Exception:
        pass

# 3. 键槽
key_slot = (cq.Workplane("XZ")
    .center(r_body - key_depth/2, total_length/2)
    .rect(key_depth, key_length)
    .extrude(key_width/2, both=True))
result = result.cut(key_slot)

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"revolve", "stepped", "keyway", "fillet"}),
    ),
    TaggedExample(
        description="单台阶轴：φ60轴身长80，φ40轴颈长40，两端倒角C1",
        code="""\
import cadquery as cq

# 尺寸参数
d_body, d_neck = 60, 40
l_body, l_neck = 80, 40
chamfer = 1

r_body, r_neck = d_body / 2, d_neck / 2

# revolve 一次成型
profile_pts = [
    (0, 0),
    (r_neck, 0),
    (r_neck, l_neck),
    (r_body, l_neck),
    (r_body, l_neck + l_body),
    (0, l_neck + l_body),
]
result = cq.Workplane("XZ").polyline(profile_pts).close().revolve(360, (0, 0, 0), (0, 1, 0))

# 两端倒角
try:
    result = result.edges("<Y").chamfer(chamfer)
    result = result.edges(">Y").chamfer(chamfer)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"revolve", "stepped", "chamfer"}),
    ),
    TaggedExample(
        description="空心轴套：外径φ80，内径φ60，长50，两端面倒角C1",
        code="""\
import cadquery as cq

# 尺寸参数
d_outer, d_inner = 80, 60
length = 50
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
        description="带键槽的法兰盘：φ120法兰厚15，φ50轮毂高30，中心孔φ20，6×φ10螺栓孔PCD90，键槽6×3.5×25，R2圆角",
        code="""\
import cadquery as cq
import math

# 尺寸参数
d_flange, h_flange = 120, 15
d_hub, h_hub = 50, 30
d_bore = 20
n_bolts, d_bolt, pcd = 6, 10, 90
key_w, key_d, key_l = 6, 3.5, 25
r_fillet = 2

r_flange, r_hub, r_bore = d_flange / 2, d_hub / 2, d_bore / 2

# 1. revolve profile 一次成型（法兰 + 轮毂 + 中心孔）
profile_pts = [
    (r_bore, 0),
    (r_flange, 0),
    (r_flange, h_flange),
    (r_hub, h_flange),
    (r_hub, h_flange + h_hub),
    (r_bore, h_flange + h_hub),
]
result = cq.Workplane("XZ").polyline(profile_pts).close().revolve(360, (0, 0, 0), (0, 1, 0))

# 2. 法兰-轮毂过渡圆角
try:
    result = result.edges(
        cq.selectors.NearestToPointSelector((r_hub, 0, h_flange))
    ).fillet(r_fillet)
except Exception:
    pass

# 3. 螺栓孔（穿过法兰）
for i in range(n_bolts):
    angle = math.radians(i * 360 / n_bolts)
    x, y = (pcd / 2) * math.cos(angle), (pcd / 2) * math.sin(angle)
    hole = cq.Workplane("XY").center(x, y).circle(d_bolt / 2).extrude(h_flange + 1)
    result = result.cut(hole)

# 4. 键槽（内孔壁向外切）
key_slot = (cq.Workplane("XY")
    .center(0, r_bore + key_d / 2)
    .rect(key_w, key_d)
    .extrude(key_l))
result = result.cut(key_slot)

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"revolve", "bore", "keyway", "hole_pattern", "fillet"}),
    ),
    TaggedExample(
        description="薄壁法兰：外径φ150，内径φ142，法兰厚8，管段长40壁厚4，R1.5圆角",
        code="""\
import cadquery as cq

# 尺寸参数
d_flange = 150
d_pipe_outer = 142
wall_t = 4
d_pipe_inner = d_pipe_outer - 2 * wall_t  # φ134
h_flange = 8
h_pipe = 40
r_fillet = 1.5

r_flange = d_flange / 2
r_pipe_o = d_pipe_outer / 2
r_pipe_i = d_pipe_inner / 2

# revolve 薄壁截面
profile_pts = [
    (r_pipe_i, 0),
    (r_flange, 0),
    (r_flange, h_flange),
    (r_pipe_o, h_flange),
    (r_pipe_o, h_flange + h_pipe),
    (r_pipe_i, h_flange + h_pipe),
]
result = cq.Workplane("XZ").polyline(profile_pts).close().revolve(360, (0, 0, 0), (0, 1, 0))

# 法兰-管段过渡圆角
try:
    result = result.edges(
        cq.selectors.NearestToPointSelector((r_pipe_o, 0, h_flange))
    ).fillet(r_fillet)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"revolve", "bore", "fillet"}),
    ),
    TaggedExample(
        description="圆柱滚子：外径φ30，长40，两端倒角C0.5",
        code="""\
import cadquery as cq

# 尺寸参数
diameter = 30
length = 40
chamfer = 0.5

radius = diameter / 2

# revolve 实心圆柱
profile_pts = [
    (0, 0),
    (radius, 0),
    (radius, length),
    (0, length),
]
result = cq.Workplane("XZ").polyline(profile_pts).close().revolve(360, (0, 0, 0), (0, 1, 0))

# 两端倒角
try:
    result = result.edges("<Y").chamfer(chamfer)
    result = result.edges(">Y").chamfer(chamfer)
except Exception:
    pass

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"revolve", "chamfer"}),
    ),
    TaggedExample(
        description="带螺纹孔的端盖：φ100法兰厚12，中心凸台φ50高8，中心孔φ16，4×M8螺纹孔PCD75深10，外缘C1倒角",
        code="""\
import cadquery as cq
import math

# 尺寸参数
d_flange, h_flange = 100, 12
d_boss, h_boss = 50, 8
d_bore = 16
n_holes, d_thread, pcd = 4, 8, 75
thread_depth = 10
chamfer = 1

r_flange, r_boss, r_bore = d_flange / 2, d_boss / 2, d_bore / 2

# 1. revolve profile（法兰 + 凸台 + 中心孔）
profile_pts = [
    (r_bore, 0),
    (r_flange, 0),
    (r_flange, h_flange),
    (r_boss, h_flange),
    (r_boss, h_flange + h_boss),
    (r_bore, h_flange + h_boss),
]
result = cq.Workplane("XZ").polyline(profile_pts).close().revolve(360, (0, 0, 0), (0, 1, 0))

# 2. 外缘倒角
try:
    result = result.edges(
        cq.selectors.NearestToPointSelector((r_flange, 0, 0))
    ).chamfer(chamfer)
except Exception:
    pass

# 3. 螺纹孔（盲孔，从法兰底面打入）
for i in range(n_holes):
    angle = math.radians(i * 360 / n_holes)
    x, y = (pcd / 2) * math.cos(angle), (pcd / 2) * math.sin(angle)
    hole = cq.Workplane("XY").center(x, y).circle(d_thread / 2).extrude(thread_depth)
    result = result.cut(hole)

cq.exporters.export(result, "${output_filename}")
""",
        features=frozenset({"revolve", "bore", "hole_pattern", "chamfer"}),
    ),
]
