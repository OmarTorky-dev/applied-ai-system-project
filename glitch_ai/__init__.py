"""Glitch Investigator AI: a RAG-grounded, test-verified debugging agent."""

import logging
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def setup_logging(level: int = logging.INFO) -> None:
    """Write a human-readable log to logs/glitch_ai.log (runs.jsonl holds structured traces)."""
    LOG_DIR.mkdir(exist_ok=True)
    root = logging.getLogger("glitch_ai")
    if root.handlers:
        return
    root.setLevel(level)
    handler = logging.FileHandler(LOG_DIR / "glitch_ai.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
