"""Runs the project's pytest suite against a candidate version of logic_utils.py.

The candidate is written to a fresh temporary folder next to a copy of the tests and
pytest runs in a subprocess with a timeout. The real logic_utils.py is never touched.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .guardrails import check_code

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_FILE = PROJECT_ROOT / "tests" / "test_game_logic.py"
TIMEOUT_SECONDS = 30


@dataclass
class TestFailure:
    __test__ = False  # not a pytest test class
    test_name: str
    message: str


@dataclass
class TestRun:
    __test__ = False  # not a pytest test class
    passed: int = 0
    failed: int = 0
    failures: list[TestFailure] = field(default_factory=list)
    error: str | None = None  # set when the suite could not run at all

    @property
    def total(self) -> int:
        return self.passed + self.failed

    @property
    def all_passed(self) -> bool:
        return self.error is None and self.failed == 0 and self.passed > 0

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def summary(self) -> str:
        if self.error:
            return f"could not run tests: {self.error}"
        return f"{self.passed}/{self.total} tests passed"


def run_tests(source: str, test_file: Path = TEST_FILE) -> TestRun:
    """Run `test_file` against `source` (saved as logic_utils.py). Refuses unsafe code."""
    guard = check_code(source)
    if not guard.ok:
        return TestRun(error="guardrail blocked execution: " + "; ".join(guard.errors))

    with tempfile.TemporaryDirectory(prefix="glitch_ai_") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "logic_utils.py").write_text(source, encoding="utf-8")
        shutil.copy(test_file, tmp_path / test_file.name)
        cmd = [
            sys.executable, "-m", "pytest", test_file.name, "-q", "-rf",
            "--tb=line", "-p", "no:cacheprovider", "--no-header",
        ]
        try:
            proc = subprocess.run(
                cmd, cwd=tmp_path, capture_output=True, text=True,
                timeout=TIMEOUT_SECONDS, encoding="utf-8", errors="replace",
                env={**os.environ, "COLUMNS": "400", "PYTHONIOENCODING": "utf-8"},
            )
        except subprocess.TimeoutExpired:
            return TestRun(error=f"tests timed out after {TIMEOUT_SECONDS}s (infinite loop?)")

    return parse_pytest_output(proc.stdout + proc.stderr)


def parse_pytest_output(output: str) -> TestRun:
    run = TestRun()
    m = re.search(r"(\d+) passed", output)
    run.passed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) failed", output)
    run.failed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) errors?\b", output)
    if m and run.total == 0:
        # Collection error, e.g. an ImportError in the candidate module.
        detail = re.search(r"^E\s+(.+)$", output, re.M)
        run.error = detail.group(1).strip() if detail else "pytest collection error"
        return run

    for line in output.splitlines():
        # -rf summary lines look like: "FAILED test_game_logic.py::test_name - AssertionError: ..."
        fm = re.match(r"FAILED \S+::(\w+)(?: - (.*))?", line)
        if fm:
            run.failures.append(TestFailure(fm.group(1), (fm.group(2) or "").strip()[:300]))

    if run.total == 0 and run.error is None:
        run.error = "no tests ran"
    return run


def test_sources(test_names: list[str], test_file: Path = TEST_FILE) -> dict[str, str]:
    """Source code of the named test functions: the clearest statement of expected behaviour."""
    source = test_file.read_text(encoding="utf-8")
    wanted = set(test_names)
    return {
        node.name: ast.get_source_segment(source, node) or ""
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    }
