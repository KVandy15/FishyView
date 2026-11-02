import math
import unittest

from fishyview.camera import FOV_MAX, FOV_MIN, START_PAN, START_TILT, turn, zoom
from fishyview.layout import dropdown_item, hit, menu_bar, place_popup, transport


class CameraTests(unittest.TestCase):
    def test_turn_right_changes_pan_only(self):
        pan, tilt = turn(START_PAN, START_TILT, 100, 0)
        self.assertLess(pan, START_PAN)
        self.assertEqual(tilt, START_TILT)

    def test_turn_down_moves_toward_the_center(self):
        pan, tilt = turn(START_PAN, START_TILT, 0, 80)
        self.assertEqual(pan, START_PAN)
        self.assertLess(tilt, START_TILT)

    def test_tilt_stops_at_the_center(self):
        _pan, tilt = turn(0.0, 0.01, 0, 10_000)
        self.assertEqual(tilt, 0.0)

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
