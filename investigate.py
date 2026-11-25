"""Command-line entry point for the Glitch Investigator agent.

Examples:
    python investigate.py samples/lying_hints.py
    python investigate.py samples/original_starter.py --mode live --out fixed_logic.py
    python investigate.py samples/malicious.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from glitch_ai import setup_logging
from glitch_ai.agent import GlitchInvestigator, Report
from glitch_ai.llm import LLMError, make_client

ICONS = {"GUARD": "🛡️ ", "TEST": "🧪", "RETRIEVE": "📚", "PROPOSE": "🤖", "VALIDATE": "✅",
         "VERIFY": "🔁", "REPORT": "📋", "ERROR": "💥"}


def print_report(report: Report, show_diff: bool = True) -> None:
    print(f"\n=== Glitch Investigator run {report.run_id}  [{report.model}] ===")
    for step in report.steps:
        print(f"{ICONS.get(step.name, '  ')} {step.name:<9} {step.detail}")
    print("\n--- Result ---")
    print(f"Status      : {report.status}")
    print(f"Confidence  : {report.confidence:.2f}")
    print(f"Tests       : before = {report.tests_before or 'n/a'} | after = {report.tests_after or 'n/a'}")
    if report.cited_patterns:
        print(f"Grounded in : {', '.join(report.cited_patterns)}")
    print(f"Summary     : {report.summary}")
    if report.diagnosis:
        print(f"\nDiagnosis:\n{report.diagnosis}")
    if report.changes:
        print("\nChanges:")
        for change in report.changes:
            print(f"  - {change}")
    if show_diff and report.fixed_code:
        print("\nProposed diff:")
        print(report.diff())


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # emoji in hints break the Windows console otherwise
    load_dotenv()
    setup_logging()

    parser = argparse.ArgumentParser(description="Diagnose and fix bugs in a logic_utils.py file.")
    parser.add_argument("file", type=Path, help="Path to the logic_utils.py version to investigate")
    parser.add_argument("--mode", choices=["auto", "live", "record", "replay"], default="auto",
                        help="live = call Claude; replay = use recorded responses (no API key); "
                             "auto = live if ANTHROPIC_API_KEY is set, else replay")
    parser.add_argument("--max-iters", type=int, default=3, help="Max fix-and-verify attempts")
    parser.add_argument("--out", type=Path, help="Write the proposed fix here (never overwrites the input)")
    parser.add_argument("--no-diff", action="store_true", help="Do not print the diff")
    args = parser.parse_args(argv)

    if not args.file.is_file():
        print(f"Error: {args.file} is not a file.", file=sys.stderr)
        return 2
    try:
        client = make_client(args.mode)
    except LLMError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    report = GlitchInvestigator(client, max_iterations=args.max_iters).investigate(
        args.file.read_text(encoding="utf-8")
    )
    print_report(report, show_diff=not args.no_diff)

    if args.out and report.fixed_code:
        if args.out.resolve() == args.file.resolve():
            print("Refusing to overwrite the input file; choose a different --out.", file=sys.stderr)
            return 2
        args.out.write_text(report.fixed_code, encoding="utf-8")
        print(f"\nProposed fix written to {args.out}. Review it before replacing logic_utils.py.")

    return 0 if report.status in ("FIXED", "NO_BUGS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
