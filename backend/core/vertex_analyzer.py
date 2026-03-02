"""Vertex-level DfAM analysis — wall thickness + overhang angle."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

logger = logging.getLogger(__name__)


@dataclass
class VertexAnalysisResult:
    """Per-vertex analysis results."""

    wall_thickness: np.ndarray  # float64, mm, shape=(n_vertices,)
    overhang_angle: np.ndarray  # float64, degrees, shape=(n_vertices,)
    risk_wall: np.ndarray  # float64, [0,1], 0=danger 1=safe
    risk_overhang: np.ndarray  # float64, [0,1], 0=danger 1=safe
    stats: dict[str, Any] = field(default_factory=dict)


class VertexAnalyzer:
    """Analyze mesh vertices for DfAM metrics.

    Parameters:
        build_direction: Build direction vector, default +Z.
        build_plate_tolerance: Z threshold below which bottom faces
            are considered resting on the build plate (mm).
    """

    SENTINEL_THICKNESS = 999.0  # mm — no opposing surface found

    def __init__(
        self,
        build_direction: tuple[float, float, float] = (0, 0, 1),
        build_plate_tolerance: float = 0.5,
    ) -> None:
        self.build_direction = np.array(build_direction, dtype=np.float64)
        self.build_plate_tolerance = build_plate_tolerance

    def analyze(
        self,
        mesh_path: str,
        min_wall_threshold: float = 1.0,
        max_overhang_threshold: float = 45.0,
        safe_multiple: float = 3.0,
        max_vertices: int = 50_000,
    ) -> VertexAnalysisResult:
        """Run vertex-level wall thickness + overhang analysis."""
        import trimesh

        mesh = trimesh.load(mesh_path, force="mesh")
        original_vertices = np.array(mesh.vertices)
        n_original = len(original_vertices)
        decimation_applied = False

        # 大网格降采样
        if len(mesh.vertices) > max_vertices:
            logger.info(
                "网格顶点数 %d 超过阈值 %d，执行降采样",
                len(mesh.vertices),
                max_vertices,
            )
            mesh = mesh.simplify_quadric_decimation(max_vertices)
            decimation_applied = True

        vertices = np.array(mesh.vertices)
        normals = np.array(mesh.vertex_normals)

        # 计算壁厚和悬垂角
        wall_thickness = self._compute_wall_thickness(mesh, vertices, normals)
        overhang_angle = self._compute_overhang_angle(vertices, normals)

        # 降采样后回映到原始网格
        if decimation_applied:
            logger.info("使用 cKDTree 最近邻回映到原始网格 (%d 顶点)", n_original)
            tree = cKDTree(vertices)
            _, indices = tree.query(original_vertices)
            wall_thickness = wall_thickness[indices]
            overhang_angle = overhang_angle[indices]
            vertices = original_vertices

        # 风险归一化
        risk_wall = self._normalize_risk(
            wall_thickness, min_wall_threshold, safe_multiple, invert=False
        )
        risk_overhang = self._normalize_risk(
            overhang_angle, max_overhang_threshold, safe_multiple, invert=True
        )

        return VertexAnalysisResult(
            wall_thickness=wall_thickness,
            overhang_angle=overhang_angle,
            risk_wall=risk_wall,
            risk_overhang=risk_overhang,
            stats={
                "vertices_analyzed": len(vertices),
                "decimation_applied": decimation_applied,
                "wall_min": float(np.min(wall_thickness)),
                "wall_max": float(
                    np.max(
                        wall_thickness[wall_thickness < self.SENTINEL_THICKNESS]
                    )
                )
                if np.any(wall_thickness < self.SENTINEL_THICKNESS)
                else 0.0,
                "overhang_max": float(np.max(overhang_angle)),
            },
        )

    def _compute_wall_thickness(
        self,
        mesh: Any,
        vertices: np.ndarray,
        normals: np.ndarray,
    ) -> np.ndarray:
        """逐顶点沿反向法线 ray-cast 计算壁厚。"""
        epsilon = 1e-4
        ray_origins = vertices - normals * epsilon
        ray_directions = -normals

        thickness = np.full(len(vertices), self.SENTINEL_THICKNESS, dtype=np.float64)

        hit_locations, hit_ray_indices, _ = mesh.ray.intersects_location(
            ray_origins, ray_directions, multiple_hits=False
        )

        if len(hit_ray_indices) > 0:
            distances = np.linalg.norm(
                hit_locations - ray_origins[hit_ray_indices], axis=1
            )
            thickness[hit_ray_indices] = distances

        logger.info(
            "壁厚分析完成: %d/%d 顶点有命中",
            len(hit_ray_indices),
            len(vertices),
        )
        return thickness

    def _compute_overhang_angle(
        self,
        vertices: np.ndarray,
        normals: np.ndarray,
    ) -> np.ndarray:
        """计算法线与构建方向的悬垂角（度）。"""
        build_dir = self.build_direction / np.linalg.norm(self.build_direction)

        cos_angles = np.dot(normals, build_dir)
        cos_angles = np.clip(cos_angles, -1.0, 1.0)
        angles = np.degrees(np.arccos(cos_angles))

        # 构建平台排除：z ≤ tolerance 且法线朝下的顶点设为 0°
        on_plate = vertices[:, 2] <= self.build_plate_tolerance
        facing_down = cos_angles < 0
        plate_mask = on_plate & facing_down
        angles[plate_mask] = 0.0

        logger.info(
            "悬垂角分析完成: 最大 %.1f°, 构建平台排除 %d 顶点",
            float(np.max(angles)),
            int(np.sum(plate_mask)),
        )
        return angles

    @staticmethod
    def _normalize_risk(
        values: np.ndarray,
        threshold: float,
        safe_multiple: float,
        invert: bool,
    ) -> np.ndarray:
        """归一化风险值到 [0, 1]，0=危险 1=安全。

        Wall thickness (invert=False):
            >= safe_multiple * threshold → 1.0 (safe)
            <= threshold → 0.0 (danger)
        Overhang (invert=True):
            0° → 1.0 (safe)
            >= threshold → 0.0 (danger)
        Sentinel 值 (999.0) 视为 safe (1.0)。
        """
        sentinel_mask = values >= VertexAnalyzer.SENTINEL_THICKNESS

        if invert:
            # overhang: 0° = safe, >= threshold = danger
            risk = 1.0 - np.clip(values / threshold, 0.0, 1.0)
        else:
            # wall thickness: <= threshold = danger, >= safe_multiple*threshold = safe
            safe_val = safe_multiple * threshold
            risk = np.clip((values - threshold) / (safe_val - threshold), 0.0, 1.0)

        risk[sentinel_mask] = 1.0
        return risk
