import math
import unittest

from fishyview.camera import (
    FOV_MAX,
    FOV_MIN,
    MODES,
    START_PAN,
    START_TILT,
    basis,
    start_pose,
    turn,
    zoom,
)
from fishyview.layout import dropdown_item, hit, menu_bar, place_popup, transport


def _columns(flat):
    return flat[0:3], flat[3:6], flat[6:9]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


class CameraTests(unittest.TestCase):
    def test_turn_right_changes_pan_only(self):
        pan, tilt = turn("down", START_PAN, START_TILT, 100, 0)
        self.assertLess(pan, START_PAN)
        self.assertEqual(tilt, START_TILT)

    def test_turn_down_moves_toward_the_center(self):
        pan, tilt = turn("down", START_PAN, START_TILT, 0, 80)
        self.assertEqual(pan, START_PAN)
        self.assertLess(tilt, START_TILT)

    def test_tilt_stops_at_the_center(self):
        _pan, tilt = turn("down", 0.0, 0.01, 0, 10_000)
        self.assertEqual(tilt, 0.0)

    def test_drag_right_looks_toward_screen_right(self):
        for mode in MODES:
            pan, tilt = start_pose(mode)
            right, _up, forward = _columns(basis(mode, pan, tilt))
            pan, tilt = turn(mode, pan, tilt, 50, 0)
            _right, _up, moved = _columns(basis(mode, pan, tilt))
            delta = tuple(moved[i] - forward[i] for i in range(3))
            self.assertGreater(_dot(delta, right), 0, mode)

    def test_drag_up_raises_the_view(self):
        _pan, lower = turn("down", *start_pose("down"), 0, -40)
        self.assertGreater(lower, START_TILT)
        _pan, higher = turn("up", *start_pose("up"), 0, -40)
        self.assertLess(higher, START_TILT)
        _pan, pitched = turn("out", *start_pose("out"), 0, -40)
        self.assertGreater(pitched, 0)

    def test_out_mode_starts_looking_out_the_lens(self):
        right, up, forward = _columns(basis("out", 0, 0))
        self.assertAlmostEqual(forward[2], 1, places=5)
        self.assertAlmostEqual(up[1], 1, places=5)
        self.assertAlmostEqual(right[0], 1, places=5)

    def test_up_mode_puts_the_sky_at_the_top(self):
        _right, up, _forward = _columns(basis("up", START_PAN, START_TILT))
        self.assertGreater(up[2], 0.2)

    def test_bases_stay_right_handed(self):
        for mode in MODES:
            right, up, forward = _columns(basis(mode, *start_pose(mode)))
            self.assertGreater(_dot(right, _cross(up, forward)), 0.9, mode)

    def test_zoom_stays_in_range(self):
        self.assertEqual(zoom(FOV_MIN, 5), FOV_MIN)
        self.assertEqual(zoom(FOV_MAX, -5), FOV_MAX)
        self.assertLess(zoom(math.radians(50), 1), math.radians(50))


class LayoutTests(unittest.TestCase):
    def test_menu_hit(self):
        bar = menu_bar([("File", 24), ("Playback", 60)])
        name, rect = bar[0]
        self.assertEqual(name, "File")
        self.assertTrue(hit(rect, rect[0] + 2, 10))
        self.assertFalse(hit(rect, rect[0] + rect[2] + 2, 10))

    def test_popup_moves_up_near_the_bottom(self):
        rect = place_popup(10, 500, 160, 4, (800, 520))
        self.assertLessEqual(rect[1] + rect[3], 520)

    def test_seek_is_on_the_transport_bar(self):
        boxes = transport(800, 600)
        self.assertTrue(hit(boxes["bar"], 400, 560))
        item = dropdown_item((10, 40, 180, 90), 1)
        self.assertTrue(hit(item, 20, 40 + 30 + 2))


if __name__ == "__main__":
    unittest.main()
