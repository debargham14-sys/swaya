"""
Measure body circumferences from a 3D body mesh (e.g. SMPL/SMPL-X).

Core idea (same as HumanBodyShape / the farazBhatti repo): slice the mesh with a
horizontal plane at the chest/underbust/waist/hip height and sum the perimeter of
the resulting cross-section contour -> true circumference. Scale the whole mesh by
the subject's HEIGHT so results come out in real cm.

This works on ANY watertight-ish humanoid mesh, independent of how it was produced
(SMPL recovery, a scan, or a CAD body), so it is the metric backend shared by the
markerless estimator and the 3D try-on avatar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

try:
    import trimesh
except Exception:  # noqa: BLE001
    trimesh = None

# Measurement-line heights as fraction of stature, measured FROM THE FLOOR (up).
LEVEL_FROM_FLOOR = {
    "bust": 0.720,
    "underbust": 0.685,
    "waist": 0.620,
    "hip": 0.530,
}


@dataclass
class MeshMeasurement:
    height_cm: float
    girths_cm: dict[str, float] = field(default_factory=dict)
    widths_cm: dict[str, float] = field(default_factory=dict)
    depths_cm: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _require_trimesh():
    if trimesh is None:
        raise RuntimeError("trimesh not installed. `pip install trimesh`")


def load_mesh(path: str | Path):
    _require_trimesh()
    m = trimesh.load(str(path), process=True)
    if isinstance(m, trimesh.Scene):
        m = trimesh.util.concatenate(tuple(m.geometry.values()))
    return m


def scale_mesh_to_height(mesh, height_cm: float, up_axis: int = 1):
    """Uniformly scale mesh so stature along `up_axis` (SMPL Y-up) equals height_cm."""
    ext = mesh.bounds[1] - mesh.bounds[0]
    cur = ext[up_axis]
    if cur <= 1e-6:
        raise ValueError("degenerate mesh extent")
    s = height_cm / cur
    mesh = mesh.copy()
    mesh.apply_scale(s)
    return mesh, up_axis


def cross_section_perimeter(mesh, y: float, up_axis: int = 1) -> tuple[float, float, float] | None:
    """
    Slice mesh at coordinate `y` along `up_axis`; return (perimeter, width, depth) cm.
    Picks the largest closed loop (the torso ring), ignoring stray arm loops.
    """
    normal = [0, 0, 0]
    normal[up_axis] = 1
    origin = mesh.bounds.mean(axis=0).copy()
    origin[up_axis] = y
    section = mesh.section(plane_origin=origin, plane_normal=normal)
    if section is None:
        return None
    to_planar = getattr(section, "to_2D", None) or section.to_planar
    planar, _ = to_planar()
    if planar is None or len(planar.polygons_full) == 0:
        # fall back to entities length
        return None
    # largest polygon = torso ring
    poly = max(planar.polygons_full, key=lambda p: p.area)
    perim = float(poly.length)
    minx, miny, maxx, maxy = poly.bounds
    return perim, float(maxx - minx), float(maxy - miny)


def measure_mesh(mesh, height_cm: float) -> MeshMeasurement:
    """Scale mesh to height and measure girths at anatomical levels."""
    _require_trimesh()
    m, up = scale_mesh_to_height(mesh, height_cm)
    lo, hi = m.bounds[0][up], m.bounds[1][up]
    stature = hi - lo
    res = MeshMeasurement(height_cm=height_cm)
    for name, floor_frac in LEVEL_FROM_FLOOR.items():
        y = lo + floor_frac * stature
        out = cross_section_perimeter(m, y, up)
        if out is None:
            res.warnings.append(f"{name}_no_section")
            continue
        perim, w, d = out
        res.girths_cm[name] = round(perim, 1)
        res.widths_cm[name] = round(w, 1)
        res.depths_cm[name] = round(d, 1)
    return res


def measure_obj(obj_path: str | Path, height_cm: float) -> MeshMeasurement:
    return measure_mesh(load_mesh(obj_path), height_cm)


# ---- self-test: known ellipsoid -------------------------------------------------

def _selftest() -> None:
    """Validate slicing on an ellipsoid with an analytically-known circumference."""
    _require_trimesh()
    # ellipsoid radii (in mesh units): rx=0.18, ry(up)=0.85, rz=0.12  (a torso-ish shape)
    sphere = trimesh.creation.icosphere(subdivisions=4, radius=1.0)
    rx, ry, rz = 0.18, 0.85, 0.12
    sphere.vertices *= np.array([rx, ry, rz])
    # scale to height 170 cm (up axis = Y)
    res = measure_mesh(sphere, height_cm=170.0)
    # At mid-height the cross-section is an ellipse with semi-axes scaled by
    # (height/ (2*ry)). Expected perimeter via Ramanujan:
    s = 170.0 / (2 * ry)
    a, b = rx * s, rz * s
    expected = np.pi * (3 * (a + b) - np.sqrt((3 * a + b) * (a + 3 * b)))
    got = res.girths_cm.get("waist")
    print(f"[selftest] waist girth: got {got} cm, expected ~{expected:.1f} cm")
    if got:
        err = abs(got - expected) / expected * 100
        print(f"[selftest] relative error {err:.1f}%  -> {'OK' if err < 3 else 'CHECK'}")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Measure girths from a body mesh (.obj/.ply)")
    p.add_argument("mesh", nargs="?", help="path to body mesh; omit to run self-test")
    p.add_argument("--height", type=float, default=170.0)
    args = p.parse_args()
    if args.mesh:
        r = measure_obj(args.mesh, args.height)
        print(f"Height {r.height_cm} cm")
        for k in ("bust", "underbust", "waist", "hip"):
            if k in r.girths_cm:
                print(f"  {k:10} {r.girths_cm[k]:6.1f} cm  ({r.girths_cm[k]/2.54:5.1f} in)")
        if r.warnings:
            print("  warnings:", r.warnings)
    else:
        _selftest()
