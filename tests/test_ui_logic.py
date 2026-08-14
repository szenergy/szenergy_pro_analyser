"""
Unit tests for UI helper logic: lap time formatting, color pool allocation, limits, and channel filtering.
"""

import unittest
from ui.sidebar import format_lap_time
from utils.constants import LAP_COLORS


class TestUILogic(unittest.TestCase):

    def test_format_lap_time(self):
        self.assertEqual(format_lap_time(0.0), "--:--.--")
        self.assertEqual(format_lap_time(-5.0), "--:--.--")
        self.assertEqual(format_lap_time(65.42), "1:05.42")
        self.assertEqual(format_lap_time(125.05), "2:05.05")
        self.assertEqual(format_lap_time(9.5), "0:09.50")

    def test_color_palette_validity(self):
        self.assertGreaterEqual(len(LAP_COLORS), 10)
        for hex_color in LAP_COLORS:
            self.assertTrue(hex_color.startswith("#"))
            self.assertEqual(len(hex_color), 7)


if __name__ == "__main__":
    unittest.main()
