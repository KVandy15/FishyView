"""Look direction for a camera aimed straight down through a circular fisheye."""

from __future__ import annotations

import math

LOOK = 0.0025
START_PAN = -math.pi / 2
START_TILT = math.radians(70)
LENS = math.pi
FOV_MIN = math.radians(20)
FOV_MAX = math.radians(110)
FOV_START = math.radians(50)


def turn(pan: float, tilt: float, dx: float, dy: float) -> tuple[float, float]:
    """dx/dy are pointer pixels. Right and down are positive."""
    pan -= dx * LOOK
    limit = LENS / 2 - 0.02
    tilt = min(limit, max(0.0, tilt - dy * LOOK))
    return pan, tilt


def zoom(fov: float, notches: float) -> float:
    """Positive notches zoom in."""
    return min(FOV_MAX, max(FOV_MIN, fov - notches * math.radians(4)))
