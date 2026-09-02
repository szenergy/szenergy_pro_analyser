"""
Unit tests for core/channel_calculator.py:
Formula AST validation, variable extraction, safe vectorized evaluation,
and Lap calculated channel resolution.
"""

import unittest
import numpy as np

from core.data_models import Lap
from core.channel_calculator import (
    extract_formula_variables,
    validate_formula,
    evaluate_channel_formula,
    calculate_lap_channel
)


class TestChannelCalculator(unittest.TestCase):

    def test_extract_formula_variables(self):
        """Validates that extract_formula_variables correctly extracts user variables while ignoring math functions."""
        self.assertEqual(extract_formula_variables("A * 3.6"), {"A"})
        self.assertEqual(extract_formula_variables("sqrt(A**2 + B**2)"), {"A", "B"})
        self.assertEqual(extract_formula_variables("clip(A, 0, 100) + abs(D) * pi"), {"A", "D"})
        self.assertEqual(extract_formula_variables(""), set())
        self.assertEqual(extract_formula_variables("100.0 + 25.0"), set())

    def test_validate_formula_syntax_and_variables(self):
        """Validates that validate_formula accepts valid expressions and rejects invalid or unknown variables."""
        # Valid formulas
        is_valid, _ = validate_formula("A * 3.6", expected_vars={"A"})
        self.assertTrue(is_valid)

        is_valid, _ = validate_formula("sqrt(A**2 + B**2)", expected_vars={"A", "B"})
        self.assertTrue(is_valid)

        is_valid, _ = validate_formula("clip(A, 0, 100)", expected_vars={"A"})
        self.assertTrue(is_valid)

        # Empty formula
        is_valid, msg = validate_formula("")
        self.assertFalse(is_valid)
        self.assertIn("cannot be empty", msg)

        # Syntax error
        is_valid, msg = validate_formula("A * +")
        self.assertFalse(is_valid)
        self.assertIn("Syntax Error", msg)

        # Unknown variable
        is_valid, msg = validate_formula("A + B + C", expected_vars={"A", "B"})
        self.assertFalse(is_valid)
        self.assertIn("Unknown variable 'C'", msg)

        # Where function is removed and should be rejected as unknown variable
        is_valid, msg = validate_formula("where(A > 0, 1, 0)", expected_vars={"A"})
        self.assertFalse(is_valid)
        self.assertIn("Unknown variable 'where'", msg)

    def test_validate_formula_rejects_non_numeric_and_structures(self):
        """Validates that strings, lists, tuples, dicts, sets, and non-numeric outputs are rejected."""
        disallowed_expressions = [
            "'hello'",
            '"speed_string"',
            'A + "km/h"',
            '[1, 2, 3]',
            '[A, B]',
            '(A, B)',
            '{"a": 1}',
            '{1, 2, 3}',
            '[x for x in A]',
            'f"val: {A}"',
        ]
        for expr in disallowed_expressions:
            is_valid, msg = validate_formula(expr, expected_vars={"A", "B"})
            self.assertFalse(is_valid, f"Expression should have been rejected: {expr} (msg: {msg})")

    def test_validate_formula_safety(self):
        """Validates that unsafe statements, imports, and private attribute accesses are strictly rejected."""
        unsafe_expressions = [
            "__import__('os').system('ls')",
            "open('/tmp/test', 'w')",
            "exec('a = 1')",
            "A.__class__.__bases__",
            "lambda x: x + 1",
            "A._private_attr",
        ]
        for expr in unsafe_expressions:
            is_valid, msg = validate_formula(expr, expected_vars={"A"})
            self.assertFalse(is_valid, f"Expression should have been rejected as unsafe: {expr} (msg: {msg})")

    def test_evaluate_channel_formula_basic_arithmetic(self):
        """Validates evaluation of basic arithmetic expressions with NumPy arrays."""
        a = np.array([10.0, 20.0, 30.0])
        b = np.array([2.0, 4.0, 5.0])

        res = evaluate_channel_formula("A + B", {"A": a, "B": b})
        np.testing.assert_allclose(res, np.array([12.0, 24.0, 35.0]))

        res = evaluate_channel_formula("A * 3.6", {"A": a})
        np.testing.assert_allclose(res, np.array([36.0, 72.0, 108.0]))

        res = evaluate_channel_formula("A / B", {"A": a, "B": b})
        np.testing.assert_allclose(res, np.array([5.0, 5.0, 6.0]))

        res = evaluate_channel_formula("A ** 2", {"A": a})
        np.testing.assert_allclose(res, np.array([100.0, 400.0, 900.0]))

    def test_evaluate_channel_formula_math_functions(self):
        """Validates evaluation with mathematical and clipping functions (sqrt, abs, clip, maximum)."""
        a = np.array([9.0, 16.0, 25.0])
        b = np.array([-5.0, 10.0, -15.0])

        res = evaluate_channel_formula("sqrt(A)", {"A": a})
        np.testing.assert_allclose(res, np.array([3.0, 4.0, 5.0]))

        res = evaluate_channel_formula("abs(B)", {"B": b})
        np.testing.assert_allclose(res, np.array([5.0, 10.0, 15.0]))

        res = evaluate_channel_formula("clip(B, 0, 8)", {"B": b})
        np.testing.assert_allclose(res, np.array([0.0, 8.0, 0.0]))

        res = evaluate_channel_formula("maximum(A, 15)", {"A": a})
        np.testing.assert_allclose(res, np.array([15.0, 16.0, 25.0]))

    def test_evaluate_channel_formula_zero_division(self):
        """Validates that zero division does not raise an unhandled exception and returns NaN array."""
        a = np.array([10.0, 20.0])
        b = np.array([0.0, 2.0])

        res = evaluate_channel_formula("A / B", {"A": a, "B": b})
        self.assertIsNotNone(res)
        self.assertTrue(np.isnan(res[0]) or np.isinf(res[0]))
        self.assertEqual(res[1], 10.0)

    def test_calculate_lap_channel_resolution(self):
        """Validates that calculate_lap_channel resolves input channels and computes calculated channel for a Lap."""
        lap = Lap(
            session_id="s1",
            lap_number=1,
            duration=10.0,
            distance=100.0,
            data={
                "voltage": np.array([400.0, 395.0, 390.0]),
                "current": np.array([50.0, 60.0, 70.0]),
            }
        )

        calc_def = {
            "label": "Power",
            "slug": "power_kw",
            "type": "calculated",
            "unit": "kW",
            "formula": "(A * B) / 1000.0",
            "inputs": {"A": "voltage", "B": "current"},
        }
        all_defs = {"power_kw": calc_def}

        result = calculate_lap_channel(lap, calc_def, all_defs)
        self.assertIsNotNone(result)
        np.testing.assert_allclose(result, np.array([20.0, 23.7, 27.3]))

    def test_calculate_lap_channel_cascading(self):
        """Validates that calculated channels can depend on other calculated channels."""
        lap = Lap(
            session_id="s1",
            lap_number=1,
            duration=10.0,
            distance=100.0,
            data={
                "v_x": np.array([3.0, 6.0]),
                "v_y": np.array([4.0, 8.0]),
            }
        )

        calc_speed_ms = {
            "label": "Speed m/s",
            "slug": "speed_ms",
            "type": "calculated",
            "unit": "m/s",
            "formula": "sqrt(A**2 + B**2)",
            "inputs": {"A": "v_x", "B": "v_y"},
        }
        calc_speed_kmh = {
            "label": "Speed km/h",
            "slug": "speed_kmh",
            "type": "calculated",
            "unit": "km/h",
            "formula": "A * 3.6",
            "inputs": {"A": "speed_ms"},
        }
        all_defs = {"speed_ms": calc_speed_ms, "speed_kmh": calc_speed_kmh}

        res = calculate_lap_channel(lap, calc_speed_kmh, all_defs)
        self.assertIsNotNone(res)
        np.testing.assert_allclose(res, np.array([18.0, 36.0]))

    def test_calculate_lap_channel_circular_dependency_protection(self):
        """Validates that circular dependencies return None and do not cause infinite recursion."""
        lap = Lap(
            session_id="s1",
            lap_number=1,
            duration=10.0,
            distance=100.0,
            data={"dummy": np.array([1.0, 2.0])}
        )

        ch_a = {
            "slug": "ch_a",
            "type": "calculated",
            "formula": "A * 2",
            "inputs": {"A": "ch_b"},
        }
        ch_b = {
            "slug": "ch_b",
            "type": "calculated",
            "formula": "A + 1",
            "inputs": {"A": "ch_a"},
        }
        all_defs = {"ch_a": ch_a, "ch_b": ch_b}

        res = calculate_lap_channel(lap, ch_a, all_defs)
        self.assertIsNone(res)

    def test_lap_get_channel_caching_and_cache_clearing(self):
        """Validates that Lap.get_channel evaluates and caches calculated channels, and clear_calculated_cache removes them."""
        lap = Lap(
            session_id="s1",
            lap_number=1,
            duration=10.0,
            distance=100.0,
            data={"speed": np.array([10.0, 20.0])}
        )

        calc_def = {
            "slug": "speed_mph",
            "label": "Speed MPH",
            "type": "calculated",
            "formula": "A * 0.621371",
            "inputs": {"A": "speed"},
        }
        all_defs = {"speed_mph": calc_def}

        # 1. First retrieval computes and caches
        mph = lap.get_channel("speed_mph", calculated_defs=all_defs)
        self.assertIsNotNone(mph)
        self.assertIn("speed_mph", lap.data)
        np.testing.assert_allclose(mph, np.array([6.21371, 12.42742]))

        # 2. Clear cache
        lap.clear_calculated_cache({"speed_mph"})
        self.assertNotIn("speed_mph", lap.data)


if __name__ == "__main__":
    unittest.main()
