"""Tests for estimate_volume() — theoretical volume from DrawingSpec."""

from __future__ import annotations

import math

from backend.core.validators import estimate_volume
from backend.knowledge.part_types import (
    BaseBodySpec,
    BoreSpec,
    DimensionLayer,
    DrawingSpec,
    PartType,
)


def test_cylinder_volume():
    """圆柱体: π * r² * h"""
    spec = DrawingSpec(
        part_type=PartType.ROTATIONAL,
        description="圆柱",
        base_body=BaseBodySpec(
            method="revolve",
            profile=[DimensionLayer(diameter=100, height=50)],
        ),
    )
    vol = estimate_volume(spec)
    expected = math.pi * 50**2 * 50  # π * r² * h
    assert abs(vol - expected) / expected < 0.05


def test_stepped_shaft_volume():
    """阶梯轴: 各段圆柱体积之和"""
    spec = DrawingSpec(
        part_type=PartType.ROTATIONAL_STEPPED,
        description="阶梯轴",
        base_body=BaseBodySpec(
            method="revolve",
            profile=[
                DimensionLayer(diameter=60, height=30),
                DimensionLayer(diameter=40, height=50),
            ],
        ),
    )
    vol = estimate_volume(spec)
    expected = math.pi * 30**2 * 30 + math.pi * 20**2 * 50
    assert abs(vol - expected) / expected < 0.05


def test_plate_volume():
    """板件: length * width * height"""
    spec = DrawingSpec(
        part_type=PartType.PLATE,
        description="矩形板",
        base_body=BaseBodySpec(
            method="extrude",
            length=200,
            width=100,
            height=10,
        ),
    )
    vol = estimate_volume(spec)
    expected = 200 * 100 * 10
    assert abs(vol - expected) / expected < 0.05


def test_with_bore():
    """带中心孔的圆柱体（减去孔体积）"""
    spec = DrawingSpec(
        part_type=PartType.ROTATIONAL,
        description="带孔圆柱",
        base_body=BaseBodySpec(
            method="revolve",
            profile=[DimensionLayer(diameter=100, height=50)],
            bore=BoreSpec(diameter=30, through=True),
        ),
    )
    vol = estimate_volume(spec)
    outer = math.pi * 50**2 * 50
    bore = math.pi * 15**2 * 50
    expected = outer - bore
    assert abs(vol - expected) / expected < 0.05


def test_bracket_volume():
    """支架: length * width * height"""
    spec = DrawingSpec(
        part_type=PartType.BRACKET,
        description="L 型支架",
        base_body=BaseBodySpec(
            method="extrude",
            length=150,
            width=80,
            height=5,
        ),
    )
    vol = estimate_volume(spec)
    expected = 150 * 80 * 5
    assert abs(vol - expected) / expected < 0.05


def test_zero_volume_returns_zero():
    """无尺寸信息时返回 0"""
    spec = DrawingSpec(
        part_type=PartType.GENERAL,
        description="未知零件",
        base_body=BaseBodySpec(method="extrude"),
    )
    vol = estimate_volume(spec)
    assert vol == 0.0
