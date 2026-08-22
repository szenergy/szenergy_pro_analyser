"""
Unit tests for SplashScreen startup loading screen component.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure Qt runs in headless offscreen mode during unit tests
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QMainWindow
from ui.splash_screen import SplashScreen, get_resource_path
from utils.constants import APP_NAME, APP_VERSION

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestSplashScreen(unittest.TestCase):

    def setUp(self):
        self.splash_dark = SplashScreen(is_dark=True)
        self.splash_light = SplashScreen(is_dark=False)

    def tearDown(self):
        if hasattr(self, "splash_dark"):
            self.splash_dark.close()
        if hasattr(self, "splash_light"):
            self.splash_light.close()
        app.sendPostedEvents()
        app.processEvents()

    def test_splash_screen_initialization_dark(self):
        """Validates that SplashScreen initializes correctly with dark theme styling."""
        self.assertTrue(self.splash_dark.is_dark)
        self.assertEqual(self.splash_dark.progress_bar.value(), 0)
        self.assertEqual(self.splash_dark.status_label.text(), "Starting application...")
        self.assertIn("#1E2125", self.splash_dark.root_frame.styleSheet())
        self.assertIn("#00E676", self.splash_dark.root_frame.styleSheet())

    def test_splash_screen_initialization_light(self):
        """Validates that SplashScreen initializes correctly with light theme styling."""
        self.assertFalse(self.splash_light.is_dark)
        self.assertEqual(self.splash_light.progress_bar.value(), 0)
        self.assertIn("#F8F9FA", self.splash_light.root_frame.styleSheet())
        self.assertIn("#00C853", self.splash_light.root_frame.styleSheet())

    def test_set_progress_and_clamping(self):
        """Validates that set_progress updates progress value, status text, and clamps out-of-range numbers."""
        # 1. Normal update
        self.splash_dark.set_progress(45, "Loading configuration...")
        self.assertEqual(self.splash_dark.progress_bar.value(), 45)
        self.assertEqual(self.splash_dark.status_label.text(), "Loading configuration...")

        # 2. Clamping below 0
        self.splash_dark.set_progress(-10, "Negative test")
        self.assertEqual(self.splash_dark.progress_bar.value(), 0)

        # 3. Clamping above 100
        self.splash_dark.set_progress(150, "Overflow test")
        self.assertEqual(self.splash_dark.progress_bar.value(), 100)

    def test_set_status(self):
        """Validates that set_status updates the status text independently."""
        self.splash_dark.set_status("Custom Status Message")
        self.assertEqual(self.splash_dark.status_label.text(), "Custom Status Message")

    def test_finish_hides_splash(self):
        """Validates that finish() smoothly closes the splash screen when main window appears."""
        win = QMainWindow()
        self.splash_dark.show()
        app.processEvents()

        self.splash_dark.finish(win)
        app.processEvents()
        self.assertFalse(self.splash_dark.isVisible())
        win.close()

    def test_get_resource_path(self):
        """Validates resource path resolution both under PyInstaller _MEIPASS and normal execution."""
        # Normal dev path
        path = get_resource_path("szenergy_logo.png")
        self.assertTrue(os.path.isabs(path))

        # PyInstaller _MEIPASS path
        with patch.object(sys, "_MEIPASS", "/tmp/_mock_meipass", create=True):
            bundled_path = get_resource_path("szenergy_logo.png")
            self.assertEqual(bundled_path, "/tmp/_mock_meipass/szenergy_logo.png")


if __name__ == "__main__":
    unittest.main()
