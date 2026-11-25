"""Guardrails: static checks on code before it is ever executed.

Both the user's input and every AI-generated fix pass through `check_code`. The test
sandbox refuses to run anything that fails these checks.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

MAX_SOURCE_BYTES = 20_000

# The game logic is pure computation, so it never needs these modules.
BLOCKED_MODULES = {
    "os", "sys", "subprocess", "shutil", "socket", "pathlib", "importlib", "ctypes",
    "requests", "urllib", "http", "pickle", "marshal", "builtins", "multiprocessing",
    "threading", "signal", "glob", "tempfile", "io",
}
BLOCKED_CALLS = {"eval", "exec", "compile", "open", "__import__", "input", "globals",
                 "locals", "getattr", "setattr", "delattr", "breakpoint"}

# The public API that app.py and the tests rely on (see KB08).
REQUIRED_FUNCTIONS = {
    "get_range_for_difficulty": 1,
    "parse_guess": 1,
    "check_guess": 2,
    "update_score": 3,
}


@dataclass
class GuardrailResult:
    ok: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def check_code(source: str) -> GuardrailResult:
    """Check size, syntax, dangerous imports/calls and the required function contract."""
    errors: list[str] = []

    if not source or not source.strip():
        return GuardrailResult(False, ["Input is empty."])
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        return GuardrailResult(False, [f"Input is larger than {MAX_SOURCE_BYTES} bytes."])

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return GuardrailResult(False, [f"Syntax error on line {exc.lineno}: {exc.msg}"])

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in BLOCKED_MODULES:
                    errors.append(f"Blocked import '{alias.name}' (line {node.lineno}).")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in BLOCKED_MODULES:
                errors.append(f"Blocked import from '{node.module}' (line {node.lineno}).")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in BLOCKED_CALLS:
                errors.append(f"Blocked call '{node.func.id}()' (line {node.lineno}).")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            errors.append(f"Blocked dunder attribute access '.{node.attr}' (line {node.lineno}).")

    defined = {
        n.name: len(n.args.args)
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
    }
    for name, n_args in REQUIRED_FUNCTIONS.items():
        if name not in defined:
            errors.append(f"Required function '{name}' is missing.")
        elif defined[name] != n_args:
            errors.append(
                f"'{name}' must take {n_args} argument(s), found {defined[name]}."
            )

    return GuardrailResult(not errors, errors)


def _function_bodies(source: str) -> dict[str, str]:
    """Top-level function name -> normalized AST dump (ignores comments and formatting)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    bodies = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            body = node.body
            # Ignore docstring edits; they never change behaviour.
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                body = body[1:]
            bodies[node.name] = ast.dump(ast.Module(body=body, type_ignores=[]))
    return bodies


def changed_functions(before: str, after: str) -> set[str]:
    """Names of top-level functions whose behaviour-relevant code differs."""
    old, new = _function_bodies(before), _function_bodies(after)
    return {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}


def implicated_functions(failing_test_code: str) -> set[str]:
    """Which public functions the failing tests actually call."""
    return {name for name in REQUIRED_FUNCTIONS if f"{name}(" in failing_test_code}
