"""Rigid transforms: T_A_B maps B coordinates into A coordinates."""

from __future__ import annotations

import math

from .course_map import MarkerPose, PlanarPose


def angle(value: float) -> float:
    return math.atan2(math.sin(value), math.cos(value))


def compose(a: PlanarPose, b: PlanarPose) -> PlanarPose:
    c, s = math.cos(a.yawRad), math.sin(a.yawRad)
    return PlanarPose(
        xM=a.xM + c * b.xM - s * b.yM,
        yM=a.yM + s * b.xM + c * b.yM,
        yawRad=angle(a.yawRad + b.yawRad),
    )


def inverse(p: PlanarPose) -> PlanarPose:
    c, s = math.cos(p.yawRad), math.sin(p.yawRad)
    return PlanarPose(xM=-c * p.xM - s * p.yM, yM=s * p.xM - c * p.yM, yawRad=angle(-p.yawRad))


def interpolate(a: PlanarPose, b: PlanarPose, fraction: float) -> PlanarPose:
    return PlanarPose(
        xM=a.xM + fraction * (b.xM - a.xM),
        yM=a.yM + fraction * (b.yM - a.yM),
        yawRad=angle(a.yawRad + fraction * angle(b.yawRad - a.yawRad)),
    )


def rotation(p: MarkerPose) -> tuple[tuple[float, ...], ...]:
    cr, sr = math.cos(p.rollRad), math.sin(p.rollRad)
    cp, sp = math.cos(p.pitchRad), math.sin(p.pitchRad)
    cy, sy = math.cos(p.yawRad), math.sin(p.yawRad)
    return (
        (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
        (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
        (-sp, cp * sr, cp * cr),
    )


def marker_base_pose(
    world: MarkerPose, relative: MarkerPose, *, max_tilt: float, max_height: float
) -> PlanarPose:
    # T_map_base = T_map_marker * inverse(T_base_marker), before planar projection.
    a, b = rotation(world), rotation(relative)
    r = tuple(tuple(sum(a[i][k] * b[j][k] for k in range(3)) for j in range(3)) for i in range(3))
    v = (relative.xM, relative.yM, relative.zM)
    w = (world.xM, world.yM, world.zM)
    t = tuple(w[i] - sum(r[i][j] * v[j] for j in range(3)) for i in range(3))
    tilt = math.acos(max(-1.0, min(1.0, r[2][2])))
    if tilt > max_tilt or abs(t[2]) > max_height:
        raise ValueError("nonplanar-pose")
    return PlanarPose(xM=t[0], yM=t[1], yawRad=math.atan2(r[1][0], r[0][0]))
