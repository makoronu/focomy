"""FormulaEngine - safe formula evaluation for calculated fields."""

import math
import re
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any


class FormulaError(Exception):
    """Error evaluating formula."""

    pass


class FormulaEngine:
    """
    Safe formula evaluation engine for calculated fields.

    Supports basic arithmetic, functions, and field references.
    Uses a whitelist approach to prevent code injection.
    """

    # Allowed functions
    FUNCTIONS: dict[str, Callable] = {
        # Math functions
        "round": round,
        "floor": math.floor,
        "ceil": math.ceil,
        "abs": abs,
        "min": min,
        "max": max,
        "pow": pow,
        "sqrt": math.sqrt,
        # Aggregations
        "sum": sum,
        "avg": lambda *args: sum(args) / len(args) if args else 0,
        "count": len,
        # Conditionals
        "if": lambda cond, t, f: t if cond else f,
        "coalesce": lambda *args: next((a for a in args if a is not None), None),
        # String functions
        "concat": lambda *args: "".join(str(a) for a in args if a is not None),
        "upper": lambda s: str(s).upper() if s else "",
        "lower": lambda s: str(s).lower() if s else "",
        "len": lambda s: len(str(s)) if s else 0,
        "trim": lambda s: str(s).strip() if s else "",
        "left": lambda s, n: str(s)[:n] if s else "",
        "right": lambda s, n: str(s)[-n:] if s else "",
        "substr": lambda s, start, length=None: (
            str(s)[start : start + length] if length else str(s)[start:]
        ),
        "replace": lambda s, old, new: str(s).replace(old, new) if s else "",
        # Date functions
        "now": datetime.utcnow,
        "today": date.today,
        "year": lambda d: d.year if isinstance(d, (date, datetime)) else None,
        "month": lambda d: d.month if isinstance(d, (date, datetime)) else None,
        "day": lambda d: d.day if isinstance(d, (date, datetime)) else None,
        "hour": lambda d: d.hour if isinstance(d, datetime) else None,
        "minute": lambda d: d.minute if isinstance(d, datetime) else None,
        "date_diff": lambda d1, d2: (
            (d2 - d1).days
            if isinstance(d1, (date, datetime)) and isinstance(d2, (date, datetime))
            else None
        ),
        # Type conversion
        "int": lambda x: int(float(x)) if x else 0,
        "float": lambda x: float(x) if x else 0.0,
        "str": lambda x: str(x) if x is not None else "",
        "bool": lambda x: bool(x),
        "decimal": lambda x, places=2: round(Decimal(str(x)), places) if x else Decimal("0"),
    }

    # Blocked patterns for security
    BLOCKED_PATTERNS = [
        r"__\w+__",  # Dunder attributes
        r"import\s+",
        r"exec\s*\(",
        r"eval\s*\(",
        r"compile\s*\(",
        r"open\s*\(",
        r"globals\s*\(",
        r"locals\s*\(",
        r"getattr\s*\(",
        r"setattr\s*\(",
        r"delattr\s*\(",
        r"hasattr\s*\(",
        r"input\s*\(",
        r"print\s*\(",
        r"os\.",
        r"sys\.",
        r"subprocess\.",
    ]

    def __init__(self):
        self._compiled_blocked = [re.compile(p, re.IGNORECASE) for p in self.BLOCKED_PATTERNS]

    def evaluate(self, formula: str, context: dict[str, Any]) -> Any:
        """
        Evaluate a formula with the given context.

        Args:
            formula: The formula string (e.g., "price * quantity")
            context: Dictionary of field values

        Returns:
            The computed result

        Raises:
            FormulaError: If the formula is invalid or unsafe
        """
        if not formula or not isinstance(formula, str):
            return None

        formula = formula.strip()

        # Security check
        self._check_security(formula)

        try:
            # Build evaluation environment
            env = self._build_environment(context)

            # Parse and evaluate
            result = eval(formula, {"__builtins__": {}}, env)

            return result

        except ZeroDivisionError:
            return None
        except Exception as e:
            raise FormulaError(f"Formula evaluation failed: {e}")

    def validate(self, formula: str) -> tuple[bool, str]:
        """
        Validate a formula without executing it.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not formula or not isinstance(formula, str):
            return True, ""

        formula = formula.strip()

        # Security check
        for pattern in self._compiled_blocked:
            if pattern.search(formula):
                return False, f"Formula contains blocked pattern: {pattern.pattern}"

        # Syntax check with empty context
        try:
            compile(formula, "<formula>", "eval")
            return True, ""
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

    def get_referenced_fields(self, formula: str) -> set[str]:
        """
        Extract field names referenced in the formula.

        Returns:
            Set of field names
        """
        if not formula:
            return set()

        # Find all identifiers
        identifiers = set(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", formula))

        # Remove function names
        identifiers -= set(self.FUNCTIONS.keys())

        # Remove Python keywords
        keywords = {"and", "or", "not", "True", "False", "None", "if", "else", "in", "is"}
        identifiers -= keywords

        return identifiers

    def _check_security(self, formula: str) -> None:
        """Check formula for security issues."""
        for pattern in self._compiled_blocked:
            if pattern.search(formula):
                raise FormulaError(f"Formula contains blocked pattern: {pattern.pattern}")

    def _build_environment(self, context: dict[str, Any]) -> dict[str, Any]:
        """Build the evaluation environment."""
        env = {}

        # Add functions
        env.update(self.FUNCTIONS)

        # Add context values (field values)
        for name, value in context.items():
            # Convert to appropriate type for math
            if isinstance(value, str):
                try:
                    # Try to convert numeric strings
                    if "." in value:
                        env[name] = float(value)
                    else:
                        env[name] = int(value)
                except ValueError:
                    env[name] = value
            else:
                env[name] = value

        # Add True/False/None
        env["True"] = True
        env["False"] = False
        env["None"] = None

        return env


# Format functions for displaying calculated values
class FormulaFormatter:
    """Format calculated values for display."""

    @staticmethod
    def format_value(value: Any, format_type: str, options: dict = None) -> str:
        """
        Format a value according to the specified format.

        Args:
            value: The value to format
            format_type: Format type (currency, percent, number, date, etc.)
            options: Additional formatting options

        Returns:
            Formatted string
        """
        if value is None:
            return ""

        options = options or {}

        formatters = {
            "currency": FormulaFormatter._format_currency,
            "percent": FormulaFormatter._format_percent,
            "number": FormulaFormatter._format_number,
            "date": FormulaFormatter._format_date,
            "datetime": FormulaFormatter._format_datetime,
            "boolean": FormulaFormatter._format_boolean,
        }

        formatter = formatters.get(format_type)
        if formatter:
            return formatter(value, options)

        return str(value)

    @staticmethod
    def _format_currency(value: Any, options: dict) -> str:
        """Format as currency."""
        try:
            num = float(value)
            currency = options.get("currency", "¥")
            decimals = options.get("decimals", 0)
            return f"{currency}{num:,.{decimals}f}"
        except (ValueError, TypeError):
            return str(value)

    @staticmethod
    def _format_percent(value: Any, options: dict) -> str:
        """Format as percentage."""
        try:
            num = float(value)
            decimals = options.get("decimals", 1)
            return f"{num:.{decimals}f}%"
        except (ValueError, TypeError):
            return str(value)

    @staticmethod
    def _format_number(value: Any, options: dict) -> str:
        """Format as number with thousands separators."""
        try:
            num = float(value)
            decimals = options.get("decimals", 0)
            return f"{num:,.{decimals}f}"
        except (ValueError, TypeError):
            return str(value)

    @staticmethod
    def _format_date(value: Any, options: dict) -> str:
        """Format as date."""
        if isinstance(value, datetime):
            fmt = options.get("format", "%Y-%m-%d")
            return value.strftime(fmt)
        if isinstance(value, date):
            fmt = options.get("format", "%Y-%m-%d")
            return value.strftime(fmt)
        return str(value)

    @staticmethod
    def _format_datetime(value: Any, options: dict) -> str:
        """Format as datetime."""
        if isinstance(value, datetime):
            fmt = options.get("format", "%Y-%m-%d %H:%M")
            return value.strftime(fmt)
        return str(value)

    @staticmethod
    def _format_boolean(value: Any, options: dict) -> str:
        """Format as boolean."""
        true_label = options.get("true", "Yes")
        false_label = options.get("false", "No")
        return true_label if value else false_label


# Singleton instance
formula_engine = FormulaEngine()
