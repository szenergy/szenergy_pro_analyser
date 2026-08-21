"""
Unit tests for Session and Lap data models.
"""

import unittest
import numpy as np
from core.data_models import Session, Lap


class TestDataModels(unittest.TestCase):

    def test_lap_creation_and_channel_access(self):
        data = {
            "time": np.array([0.0, 0.1, 0.2]),
            "speed": np.array([20.0, 25.0, 30.0])
        }
        lap = Lap(
            session_id="session_1",
            lap_number=1,
            duration=65.4,
            distance=1200.0,
            data=data
        )

        self.assertEqual(lap.session_id, "session_1")
        self.assertEqual(lap.lap_number, 1)
        self.assertEqual(lap.duration, 65.4)
        self.assertEqual(lap.distance, 1200.0)
        np.testing.assert_array_equal(lap.get_channel("speed"), np.array([20.0, 25.0, 30.0]))
        np.testing.assert_array_equal(lap.get_channel("time"), np.array([0.0, 0.1, 0.2]))
        self.assertIsNone(lap.get_channel("nonexistent"))

    def test_session_lap_lookup(self):
        lap1 = Lap(session_id="s1", lap_number=1, duration=60.0)
        lap2 = Lap(session_id="s1", lap_number=2, duration=58.5)
        
        session = Session(
            id="s1",
            name="test_log.csv",
            file_path="/tmp/test_log.csv",
            laps=[lap1, lap2],
            channels=["speed", "rpm"]
        )

        self.assertEqual(len(session.laps), 2)
        self.assertEqual(session.get_lap(1), lap1)
        self.assertEqual(session.get_lap(2), lap2)
        self.assertIsNone(session.get_lap(3))


if __name__ == "__main__":
    unittest.main()
