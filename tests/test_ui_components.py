"""
Unit and integration tests for UI components including GraphViewWidget and SidebarWidget.
"""

import sys
import unittest
import numpy as np
from PySide6.QtWidgets import QApplication

from core.data_models import Session, Lap
from ui.graph_view import GraphViewWidget
from ui.sidebar import SidebarWidget

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestUIComponents(unittest.TestCase):

    def setUp(self):
        # Create dummy session
        self.session = Session(
            id="s_test",
            name="test_session.csv",
            file_path="/tmp/test.csv",
            channels=["Speed", "RPM"]
        )
        data1 = {
            "Time": np.array([0.0, 1.0, 2.0]),
            "Speed": np.array([10.0, 20.0, 30.0]),
            "RPM": np.array([1000.0, 2000.0, 3000.0])
        }
        lap1 = Lap("s_test", 1, 2.0, 30.0, data1)
        self.session.laps.append(lap1)

    def test_graph_view_rebuild_plots_no_crash(self):
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)

        # Select laps and channels
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"Speed", "RPM"})

        # Should rebuild plots without raising AttributeError
        self.assertEqual(len(widget.plot_widgets), 2)
        self.assertIn("Speed", widget.plot_widgets)
        self.assertIn("RPM", widget.plot_widgets)


if __name__ == "__main__":
    unittest.main()
