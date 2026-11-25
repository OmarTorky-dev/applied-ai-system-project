"""Reliability evaluation for the Glitch Investigator agent.

Three experiments, results written to eval/results.json and eval/results.md:

1. End-to-end:   run the agent on every sample and check the final status matches the
                 expected one (FIXED / NO_BUGS / REFUSED), the tests after the fix, the
                 confidence score and the out-of-scope edits.
2. Consistency:  with --repeats N (live mode), run each buggy sample N times and measure how
                 often the agent reaches the same outcome.
3. Retrieval:    with no model at all, measure how many of each sample's relevant knowledge-
                 base docs (hand-labelled below) the retriever returns for top-k = 1..5.

Usage:
    python evaluate.py                       # replay mode: free, offline, deterministic
    python evaluate.py --mode live --repeats 3
    python evaluate.py --mode live --top-k 5 --tag k5
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from glitch_ai import setup_logging
from glitch_ai.agent import GlitchInvestigator
from glitch_ai.llm import LLMError, make_client
from glitch_ai.retriever import Retriever, load_knowledge_base
from glitch_ai.sandbox import run_tests, test_sources

ROOT = Path(__file__).resolve().parent
EVAL_DIR = ROOT / "eval"

# Expected outcome and the knowledge-base docs a careful human would say are relevant.
CASES = {
    "lying_hints":      {"expected": "FIXED",   "relevant": ["KB01", "KB02"]},
    "haywire_scoring":  {"expected": "FIXED",   "relevant": ["KB03", "KB04"]},
    "fragile_parsing":  {"expected": "FIXED",   "relevant": ["KB05", "KB07"]},
    "original_starter": {"expected": "FIXED",   "relevant": ["KB01", "KB02", "KB03",
                                                             "KB04", "KB05", "KB06"]},
    "clean":            {"expected": "NO_BUGS", "relevant": []},
    "malicious":        {"expected": "REFUSED", "relevant": []},
    "syntax_error":     {"expected": "REFUSED", "relevant": []},
}


def coverage(found: list[str], relevant: list[str]) -> float | None:
    if not relevant:
        return None
    return round(len(set(found) & set(relevant)) / len(relevant), 2)


def run_end_to_end(client, repeats: int, top_k: int) -> list[dict]:
    rows = []
    agent = GlitchInvestigator(client, top_k=top_k)
    for name, case in CASES.items():
        code = (ROOT / "samples" / f"{name}.py").read_text(encoding="utf-8")
        # Only buggy samples involve the model, so only they are worth repeating.
        n = repeats if case["expected"] == "FIXED" else 1
        for i in range(1, n + 1):
            start = time.time()
            report = agent.investigate(code)
            retrieved = sorted({d["id"] for s in report.steps if s.name == "RETRIEVE"
                                for d in s.data.get("docs", [])})
            rows.append({
                "sample": name,
                "run": i,
                "expected": case["expected"],
                "status": report.status,
                "passed": report.status == case["expected"],
                "tests_before": report.tests_before,
                "tests_after": report.tests_after,
                "iterations": report.iterations,
                "confidence": report.confidence,
                "cited": report.cited_patterns,
                "retrieved": retrieved,
                "retrieval_coverage": coverage(retrieved, case["relevant"]),
                "citation_coverage": coverage(report.cited_patterns, case["relevant"]),
                "out_of_scope": report.out_of_scope,
                "seconds": round(time.time() - start, 1),
                "summary": report.summary,
            })
            r = rows[-1]
            mark = "PASS" if r["passed"] else "FAIL"
            print(f"  [{mark}] {name:<17} run {i}: {r['status']:<8} conf={r['confidence']:.2f} "
                  f"tests={r['tests_after'] or '-'} cited={r['cited']} "
                  f"scope={r['out_of_scope'] or '-'} ({r['seconds']}s)")
    return rows


def run_retrieval_experiment(max_k: int = 5) -> dict:
    """Model-free: how much of the relevant set does top-k retrieval find?"""
    retriever = Retriever(load_knowledge_base())
    results = {}
    for name, case in CASES.items():
        if not case["relevant"]:
            continue
        code = (ROOT / "samples" / f"{name}.py").read_text(encoding="utf-8")
        tests = run_tests(code)
        failures = "\n".join(f"- {f.test_name}: {f.message}" for f in tests.failures)
        evidence = failures + "\n" + "\n".join(
            test_sources([f.test_name for f in tests.failures]).values())
        query = evidence + "\n" + evidence + "\n" + code   # same query the agent builds
        ranked = [r.doc.doc_id for r in retriever.search(query, k=max_k)]
        results[name] = {
            "relevant": case["relevant"],
            "ranking": ranked,
            "coverage_at_k": {k: coverage(ranked[:k], case["relevant"]) for k in range(1, max_k + 1)},
        }
    return results


def summarize(rows: list[dict]) -> dict:
    fixed_rows = [r for r in rows if r["expected"] == "FIXED"]
    by_sample: dict[str, list[dict]] = {}
    for r in fixed_rows:
        by_sample.setdefault(r["sample"], []).append(r)
    consistency = {
        s: round(sum(r["status"] == "FIXED" for r in rs) / len(rs), 2) for s, rs in by_sample.items()
    }
    confs = [r["confidence"] for r in fixed_rows]
    cit = [r["citation_coverage"] for r in fixed_rows if r["citation_coverage"] is not None]
    return {
        "runs": len(rows),
        "passed": sum(r["passed"] for r in rows),
        "fixed_runs": len(fixed_rows),
        "fixed_ok": sum(r["status"] == "FIXED" for r in fixed_rows),
        "first_try": sum(r["status"] == "FIXED" and r["iterations"] == 1 for r in fixed_rows),
        "mean_confidence_buggy": round(statistics.mean(confs), 2) if confs else None,
        "mean_citation_coverage": round(statistics.mean(cit), 2) if cit else None,
        "runs_with_out_of_scope_edits": sum(bool(r["out_of_scope"]) for r in fixed_rows),
        "consistency": consistency,
    }


def write_markdown(meta: dict, summary: dict, rows: list[dict], retrieval: dict, path: Path) -> None:
    lines = [
        f"# Evaluation results: `{meta['tag']}`",
        "",
        f"- **Model:** {meta['model']}  ",
        f"- **Mode:** {meta['mode']} · **top-k:** {meta['top_k']} · **repeats:** {meta['repeats']}  ",
        f"- **Date:** {meta['date']}  ",
        f"- **Command:** `{meta['command']}`",
        "",
        "## Summary",
        "",
        f"- **{summary['passed']}/{summary['runs']}** runs ended in the expected status.",
        f"- Buggy samples: **{summary['fixed_ok']}/{summary['fixed_runs']}** fixed "
        f"({summary['first_try']} on the first attempt).",
        f"- Mean confidence on buggy samples: **{summary['mean_confidence_buggy']}**.",
        f"- Mean citation coverage (relevant KB docs the model cited): "
        f"**{summary['mean_citation_coverage']}**.",
        f"- Runs with out-of-scope edits flagged: **{summary['runs_with_out_of_scope_edits']}**.",
        "- Consistency (share of repeats that reached FIXED): "
        + ", ".join(f"`{s}` {v:.0%}" for s, v in summary["consistency"].items()),
        "",
        "## End-to-end runs",
        "",
        "| Sample | Run | Expected | Got | Result | Tests after | Attempts | Confidence | Cited | Retrieval cov. | Citation cov. | Out-of-scope edits |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        fmt = lambda v: "-" if v is None else f"{v:.2f}"
        lines.append(
            f"| {r['sample']} | {r['run']} | {r['expected']} | {r['status']} | "
            f"{'✅ Pass' if r['passed'] else '❌ Fail'} | {r['tests_after'] or '-'} | "
            f"{r['iterations']} | {r['confidence']:.2f} | {', '.join(r['cited']) or '-'} | "
            f"{fmt(r['retrieval_coverage'])} | {fmt(r['citation_coverage'])} | "
            f"{', '.join(r['out_of_scope']) or '-'} |"
        )
    lines += [
        "",
        "## Retrieval experiment (no model involved)",
        "",
        "Share of each sample's hand-labelled relevant docs found in the top-k results.",
        "",
        "| Sample | Relevant docs | Ranking | k=1 | k=2 | k=3 | k=4 | k=5 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, res in retrieval.items():
        c = res["coverage_at_k"]
        lines.append(f"| {name} | {', '.join(res['relevant'])} | {' > '.join(res['ranking'])} | "
                     + " | ".join(f"{c[k]:.2f}" for k in range(1, 6)) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    load_dotenv()
    setup_logging()
    parser = argparse.ArgumentParser(description="Evaluate the Glitch Investigator agent.")
    parser.add_argument("--mode", choices=["replay", "live"], default="replay")
    parser.add_argument("--provider", choices=["auto", "gemini", "claude"], default="auto")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--tag", default=None, help="Name for the output files (default: mode)")
    args = parser.parse_args(argv)

    try:
        client = make_client(args.mode, args.provider)
    except LLMError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    tag = args.tag or args.mode
    print(f"Evaluating with {client.name}, top-k={args.top_k}, repeats={args.repeats}")
    rows = run_end_to_end(client, args.repeats, args.top_k)
    retrieval = run_retrieval_experiment()
    summary = summarize(rows)
    meta = {
        "tag": tag, "model": client.name, "mode": args.mode, "top_k": args.top_k,
        "repeats": args.repeats, "date": time.strftime("%Y-%m-%d %H:%M"),
        "command": "python evaluate.py " + " ".join(argv if argv is not None else sys.argv[1:]),
    }
    EVAL_DIR.mkdir(exist_ok=True)
    (EVAL_DIR / f"results_{tag}.json").write_text(
        json.dumps({"meta": meta, "summary": summary, "runs": rows, "retrieval": retrieval},
                   indent=2), encoding="utf-8")
    write_markdown(meta, summary, rows, retrieval, EVAL_DIR / f"results_{tag}.md")

    print(f"\n{summary['passed']}/{summary['runs']} runs matched the expected status; "
          f"{summary['fixed_ok']}/{summary['fixed_runs']} buggy runs fixed; "
          f"mean confidence {summary['mean_confidence_buggy']}; "
          f"consistency {summary['consistency']}")
    print(f"Wrote eval/results_{tag}.md and eval/results_{tag}.json")
    return 0 if summary["passed"] == summary["runs"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
