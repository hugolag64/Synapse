"""sparkline.py — mini SVG sparkline, shared by QCM and Progression pages."""
from __future__ import annotations


def sparkline_svg(values: list[float], color: str, width: int = 60, height: int = 28) -> str:
    """Mini sparkline SVG (polyline) — valeurs en ordre chronologique."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    step = width / (len(values) - 1)
    pts = []
    for i, v in enumerate(values):
        x = i * step
        y = height - ((v - lo) / rng) * (height - 6) - 3
        pts.append(f"{x:.1f},{y:.1f}")
    points = " ".join(pts)
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )
