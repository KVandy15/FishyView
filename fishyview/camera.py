"""Look direction for a circular fisheye, for three ways of mounting the camera."""

from __future__ import annotations

import math

LOOK = 0.0025
START_PAN = -math.pi / 2
START_TILT = math.radians(70)
LENS = math.pi
FOV_MIN = math.radians(20)
FOV_MAX = math.radians(110)
FOV_START = math.radians(50)

MODES = ("down", "out", "up")
LABELS = {
    "down": "Looking down",
    "out": "Looking out",
    "up": "Looking up",
}


def start_pose(mode: str) -> tuple[float, float]:
    if mode == "out":
        return 0.0, 0.0
    return START_PAN, START_TILT


def turn(mode: str, pan: float, tilt: float, dx: float, dy: float) -> tuple[float, float]:
    """dx/dy are pointer pixels. Right and down are positive."""
    if mode == "out":
        pan += dx * LOOK
        limit = math.pi / 2 - 0.02
        tilt = min(limit, max(-limit, tilt - dy * LOOK))
        return pan, tilt
    if mode == "up":
        pan += dx * LOOK
        limit = LENS / 2 - 0.02
        tilt = min(limit, max(0.0, tilt + dy * LOOK))
        return pan, tilt
    pan -= dx * LOOK
    limit = LENS / 2 - 0.02
    tilt = min(limit, max(0.0, tilt - dy * LOOK))
    return pan, tilt


def zoom(fov: float, notches: float) -> float:
    """Positive notches zoom in."""
    return min(FOV_MAX, max(FOV_MIN, fov - notches * math.radians(4)))


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2) or 1.0
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def basis(mode: str, pan: float, tilt: float) -> tuple[float, ...]:
    """Column-major camera basis: right, up, forward, in fisheye image space.

    +Z is the center of the lens. +X is image right. +Y is image up.
    """
    if mode == "out":
        cy, sy = math.cos(pan), math.sin(pan)
        cp, sp = math.cos(tilt), math.sin(tilt)
        forward = (sy * cp, sp, cy * cp)
        up = (-sy * sp, cp, -cy * sp)
    else:
        cp, sp = math.cos(pan), math.sin(pan)
        ct, st = math.cos(tilt), math.sin(tilt)
        forward = (cp * st, sp * st, ct)
        up = (cp * ct, sp * ct, -st)
        if mode == "up":
            up = (-up[0], -up[1], -up[2])
    forward = _normalize(forward)
    up = _normalize(up)
    right = _normalize(_cross(up, forward))
    up = _normalize(_cross(forward, right))
    return (
        right[0], right[1], right[2],
        up[0], up[1], up[2],
        forward[0], forward[1], forward[2],
    )
