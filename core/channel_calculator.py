"""
Channel Calculator module for SZenergy Pro Analyser.
Handles formula validation (via AST analysis) and safe vectorized evaluation
of calculated channels across NumPy telemetry data arrays.
"""

import ast
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# Safe mathematical and array functions exposed to formulas
# Safe mathematical and array functions exposed to formulas
SAFE_MATH_FUNCTIONS: Dict[str, Any] = {
    # Basic math functions
    "abs": np.abs,
    "sqrt": np.sqrt,
    "cbrt": np.cbrt,
    "exp": np.exp,
    "log": np.log,
    "log10": np.log10,
    "log2": np.log2,
    "power": np.power,
    "hypot": np.hypot,
    "round": np.round,
    "floor": np.floor,
    "ceil": np.ceil,
    "sign": np.sign,
    # Trigonometry & conversions
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "arcsin": np.arcsin,
    "arccos": np.arccos,
    "arctan": np.arctan,
    "arctan2": np.arctan2,
    "deg2rad": np.deg2rad,
    "rad2deg": np.rad2deg,
    # Array helpers & clamps
    "maximum": np.maximum,
    "minimum": np.minimum,
    "clip": np.clip,
    "max": np.maximum,
    "min": np.minimum,
    # Constants
    "pi": np.pi,
    "e": np.e,
    "nan": np.nan,
    "inf": np.inf,
    # Direct access to numpy if preferred
    "np": np,
}

def _blocked_import(*args, **kwargs):
    raise ImportError("Imports are not permitted in formulas.")


# Restricted builtins dictionary (strictly numeric)
SAFE_BUILTINS: Dict[str, Any] = {
    "__import__": _blocked_import,
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "pow": pow,
    "float": float,
    "int": int,
    "bool": bool,
}

# Disallowed AST node types for security and strict schema validation
DISALLOWED_AST_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Delete,
    ast.Global,
    ast.Nonlocal,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Raise,
    ast.Assert,
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Yield,
    ast.YieldFrom,
    ast.Lambda,
    # Block data structures and formatting
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Set,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.JoinedStr,
    ast.FormattedValue,
)


def extract_formula_variables(formula: str) -> Set[str]:
    """
    Parses a formula string and extracts all variable names that are not
    known safe mathematical functions or constants.
    """
    formula = formula.strip()
    if not formula:
        return set()

    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError:
        return set()

    variables: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in SAFE_MATH_FUNCTIONS and node.id not in SAFE_BUILTINS:
                variables.add(node.id)
    return variables


def validate_formula(formula: str, expected_vars: Optional[Set[str]] = None) -> Tuple[bool, str]:
    """
    Validates a formula expression:
    1. Checks Python syntax validity in 'eval' mode.
    2. Enforces safety by forbidding imports, assignments, statements, and dunder attribute access.
    3. Forbids non-numeric constructs like lists, tuples, dicts, sets, and string literals.
    4. If expected_vars is provided, ensures all variable names referenced in the formula
       are present in expected_vars or the safe math symbol table.
    5. Checks that the output evaluates to a single numeric value/array.

    Returns:
        (is_valid, message)
    """
    formula = formula.strip()
    if not formula:
        return False, "Formula cannot be empty."

    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as e:
        return False, f"Syntax Error: {e.msg}"

    # Traverse AST and check node safety & types
    for node in ast.walk(tree):
        if isinstance(node, DISALLOWED_AST_NODES):
            return False, f"Forbidden statement or data structure: {type(node).__name__}"

        # Prevent string, bytes, or non-numeric constant literals
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (str, bytes, bytearray)):
                return False, "String and byte literals are not permitted in mathematical formulas."
            if not isinstance(node.value, (int, float, complex, bool)) and node.value is not None:
                return False, f"Literal of type '{type(node.value).__name__}' is not permitted."

        # Prevent access to private/dunder attributes like __class__, __globals__
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                return False, f"Access to private attribute '{node.attr}' is not permitted."

        # Check variable names
        if isinstance(node, ast.Name):
            var_name = node.id
            if var_name.startswith("_"):
                return False, f"Variable name '{var_name}' starting with underscore is not permitted."
            if expected_vars is not None:
                if (
                    var_name not in expected_vars
                    and var_name not in SAFE_MATH_FUNCTIONS
                    and var_name not in SAFE_BUILTINS
                ):
                    return False, f"Unknown variable '{var_name}'. Only defined input letters {sorted(list(expected_vars))} and standard math functions are allowed."

    # Test evaluation with dummy numeric inputs
    if expected_vars is not None:
        dummy_inputs = {var: 1.0 for var in expected_vars}
        eval_globals = {"__builtins__": SAFE_BUILTINS}
        eval_locals = dict(SAFE_MATH_FUNCTIONS)
        eval_locals.update(dummy_inputs)
        try:
            test_res = eval(formula, eval_globals, eval_locals)
            if not isinstance(test_res, (int, float, np.number, np.ndarray, bool)):
                return False, f"Formula output must be numeric, not '{type(test_res).__name__}'."
            if isinstance(test_res, np.ndarray) and not np.issubdtype(test_res.dtype, np.number):
                return False, f"Formula output must be numeric, not '{test_res.dtype}'."
        except ZeroDivisionError:
            pass
        except Exception as e:
            # If evaluating with dummy 1.0 raises an unhandled error other than ZeroDivisionError
            logger.debug("Dummy test evaluation for '%s' raised: %s", formula, e)

    return True, "Formula is valid."


def evaluate_channel_formula(
    formula: str,
    input_arrays: Dict[str, Any]
) -> Optional[np.ndarray]:
    """
    Evaluates a formula safely with a dictionary of input arrays (e.g. {'A': np.ndarray, 'B': np.ndarray}).
    Returns a float NumPy array result, or None if evaluation fails or produces non-numeric output.
    """
    formula = formula.strip()
    if not formula:
        return None

    # Validate syntax first
    is_valid, err_msg = validate_formula(formula, set(input_arrays.keys()))
    if not is_valid:
        logger.warning("Formula validation failed for '%s': %s", formula, err_msg)
        return None

    # Prepare execution scope
    eval_globals = {"__builtins__": SAFE_BUILTINS}
    eval_locals = dict(SAFE_MATH_FUNCTIONS)
    eval_locals.update(input_arrays)

    try:
        result = eval(formula, eval_globals, eval_locals)
    except ZeroDivisionError:
        logger.warning("Zero division in formula '%s'", formula)
        # Handle zero division by returning array of NaNs if length known
        if input_arrays:
            first_arr = next(iter(input_arrays.values()))
            if isinstance(first_arr, np.ndarray):
                return np.full_like(first_arr, np.nan, dtype=np.float64)
        return None
    except Exception as e:
        logger.warning("Error evaluating formula '%s': %s", formula, e)
        return None

    # Enforce strictly numeric single number or numeric array output
    if isinstance(result, (int, float, np.number, bool)):
        # Scalar number result -> broadcast to array if inputs were arrays
        if input_arrays:
            first_arr = next(iter(input_arrays.values()))
            if isinstance(first_arr, np.ndarray):
                return np.full_like(first_arr, float(result), dtype=np.float64)
        return np.array([float(result)], dtype=np.float64)
    elif isinstance(result, np.ndarray):
        if not np.issubdtype(result.dtype, np.number):
            logger.warning("Formula '%s' evaluated to non-numeric array dtype '%s'", formula, result.dtype)
            return None
        return result.astype(np.float64, copy=False)

    logger.warning("Formula '%s' evaluated to invalid non-numeric output type '%s'", formula, type(result).__name__)
    return None


def calculate_lap_channel(
    lap: Any,
    calc_def: Dict[str, Any],
    all_channel_defs_by_slug: Dict[str, Dict[str, Any]],
    visited_slugs: Optional[Set[str]] = None
) -> Optional[np.ndarray]:
    """
    Resolves inputs and evaluates a calculated channel definition for a given Lap object.
    Supports cascading calculated channels (a calculated channel depending on another).
    Protects against circular dependencies using visited_slugs.
    """
    if visited_slugs is None:
        visited_slugs = set()

    slug = calc_def.get("slug", "")
    if slug in visited_slugs:
        logger.error("Circular dependency detected for calculated channel '%s'", slug)
        return None

    visited_slugs.add(slug)

    formula = calc_def.get("formula", "").strip()
    inputs_map = calc_def.get("inputs", {})  # e.g. {"A": "voltage", "B": "current"}
    if not formula or not inputs_map:
        return None

    # Gather input arrays from the lap
    input_arrays: Dict[str, np.ndarray] = {}
    target_length: Optional[int] = None

    for var_letter, input_slug in inputs_map.items():
        if not input_slug:
            return None

        # Check if lap already has this channel
        arr = lap.get_channel(input_slug)
        if arr is None:
            # Check if input is another calculated channel
            if input_slug in all_channel_defs_by_slug:
                other_def = all_channel_defs_by_slug[input_slug]
                if other_def.get("type") == "calculated":
                    arr = calculate_lap_channel(
                        lap, other_def, all_channel_defs_by_slug, set(visited_slugs)
                    )
                    if arr is not None:
                        # Cache intermediate calculated channel on the lap
                        lap.data[input_slug] = arr

        if arr is None or not isinstance(arr, np.ndarray) or len(arr) == 0:
            # Required input not available for this lap
            return None

        if target_length is None:
            target_length = len(arr)
        elif len(arr) != target_length:
            # Mismatched array lengths in telemetry lap
            logger.warning(
                "Mismatched array length for variable '%s' (channel '%s') in lap %d: expected %d, got %d",
                var_letter, input_slug, getattr(lap, "lap_number", 0), target_length, len(arr)
            )
            # Clip or pad to target_length if needed
            if len(arr) > target_length:
                arr = arr[:target_length]
            else:
                arr = np.pad(arr, (0, target_length - len(arr)), mode="edge")

        input_arrays[var_letter] = arr

    return evaluate_channel_formula(formula, input_arrays)
