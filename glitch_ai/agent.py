"""The Glitch Investigator agent: a plan -> act -> check loop.

1. GUARD     Static guardrail check on the submitted code (refuse unsafe input).
2. TEST      Run the pytest suite to collect real evidence of what is broken.
3. RETRIEVE  Search the bug-pattern knowledge base using the failing tests and the code.
4. PROPOSE   Ask Claude for a diagnosis and a full fix, grounded in the retrieved docs.
5. VALIDATE  Guardrail-check the fix and verify the citations came from retrieval.
6. VERIFY    Re-run the tests on the fix. If any still fail, feed the new failures
             back into step 3 and try again (up to max_iterations).
7. REPORT    Status, confidence score, diff and full trace for a human to approve.
"""

from __future__ import annotations

import difflib
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .guardrails import changed_functions, check_code, implicated_functions
from .llm import FixProposal, LLMClient, LLMError
from .retriever import RetrievedDoc, Retriever, load_knowledge_base
from .sandbox import TestRun, run_tests, test_sources

log = logging.getLogger("glitch_ai.agent")

RUNS_LOG = Path(__file__).resolve().parent.parent / "logs" / "runs.jsonl"

SYSTEM_PROMPT = """You are Glitch Investigator, a careful Python debugging assistant.
You repair `logic_utils.py`, the pure game-logic module of a number-guessing game.

Rules:
- Base your diagnosis on the failing tests and on the retrieved bug-pattern documents.
  Cite the IDs of the documents you used (e.g. "KB01"). Only cite IDs that were provided.
- Fix root causes. Never special-case test inputs, never delete or weaken behaviour to make
  a test pass, and never change a function's signature or return shape.
- Keep the fix minimal: only change functions that the failing tests call. Leave every other
  function exactly as it is, even if you would write it differently.
- Keep the four public functions: get_range_for_difficulty(difficulty),
  parse_guess(raw), check_guess(guess, secret), update_score(current_score, outcome, attempt_number).
- Do not import modules or touch files, the network or the OS. The module must stay pure.
- Return the complete corrected file in `fixed_code`, not a diff.
- Set `confidence` honestly: lower it if the documents do not cover a failure or if you are guessing."""


@dataclass
class Step:
    name: str
    detail: str
    data: dict = field(default_factory=dict)


@dataclass
class Report:
    status: str                    # FIXED, PARTIAL, FAILED, NO_BUGS, REFUSED, ERROR
    confidence: float
    summary: str
    original_code: str
    fixed_code: str | None = None
    diagnosis: str | None = None
    changes: list[str] = field(default_factory=list)
    cited_patterns: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)  # changed but not implicated by tests
    iterations: int = 0
    tests_before: str = ""
    tests_after: str = ""
    steps: list[Step] = field(default_factory=list)
    run_id: str = ""
    model: str = ""

    def diff(self) -> str:
        if not self.fixed_code:
            return ""
        return "".join(
            difflib.unified_diff(
                self.original_code.splitlines(keepends=True),
                self.fixed_code.splitlines(keepends=True),
                fromfile="logic_utils.py (submitted)",
                tofile="logic_utils.py (proposed fix)",
            )
        )


def score_confidence(tests: TestRun, proposal: FixProposal | None,
                     retrieved: list[RetrievedDoc], bad_citations: list[str],
                     out_of_scope: list[str] | tuple = ()) -> float:
    """Blend three independent signals into one 0-1 score.

    - 60%  test evidence: fraction of the suite that passes after the fix (objective)
    - 20%  model self-rating, clamped to [0, 1] (subjective, so weighted lightly)
    - 20%  grounding: the fix cites retrieved docs and no invented IDs
    Then: -0.1 for every function changed that no failing test implicates (untested edits),
    and any remaining test failure caps the score at 0.5.
    """
    if tests.error:
        return 0.0
    model_conf = min(max(proposal.confidence, 0.0), 1.0) if proposal else 0.0
    grounding = 0.0
    if proposal and retrieved:
        retrieved_ids = {r.doc.doc_id for r in retrieved}
        valid = [c for c in proposal.cited_patterns if c in retrieved_ids]
        grounding = 1.0 if valid and not bad_citations else (0.5 if valid else 0.0)
    score = 0.6 * tests.pass_rate + 0.2 * model_conf + 0.2 * grounding
    score -= 0.1 * len(out_of_scope)
    if not tests.all_passed:
        # A fix that still fails any test must never look trustworthy. Without this cap,
        # 14/15 passing plus a confident model scored 0.94 in testing.
        score = min(score, 0.5)
    return round(score, 2)


class GlitchInvestigator:
    def __init__(self, llm: LLMClient, retriever: Retriever | None = None,
                 max_iterations: int = 3, top_k: int = 3, runs_log: Path | None = RUNS_LOG):
        self.llm = llm
        self.retriever = retriever or Retriever(load_knowledge_base())
        self.max_iterations = max_iterations
        self.top_k = top_k
        self.runs_log = runs_log

    # -- helpers ---------------------------------------------------------------------
    def _step(self, report: Report, name: str, detail: str, **data) -> None:
        report.steps.append(Step(name, detail, data))
        log.info("[%s] %s: %s", report.run_id, name, detail)

    @staticmethod
    def _failure_text(tests: TestRun) -> str:
        return "\n".join(f"- {f.test_name}: {f.message}" for f in tests.failures)

    def _build_prompt(self, code: str, tests: TestRun, docs: list[RetrievedDoc],
                      attempt: int, previous: FixProposal | None,
                      rejection: str | None = None) -> str:
        doc_block = "\n\n".join(
            f'<document id="{r.doc.doc_id}" title="{r.doc.title}">\n{r.doc.body}\n</document>'
            for r in docs
        ) or "(no relevant documents were found; say so and lower your confidence)"
        parts = [
            f"<retrieved_bug_patterns>\n{doc_block}\n</retrieved_bug_patterns>",
            f"<code file=\"logic_utils.py\">\n{code}\n</code>",
            f"<failing_tests count=\"{tests.failed}\" passing=\"{tests.passed}\">\n"
            f"{self._failure_text(tests)}\n</failing_tests>",
            "<failing_test_source>\n" + "\n\n".join(
                test_sources([f.test_name for f in tests.failures]).values())
            + "\n</failing_test_source>",
        ]
        if rejection:
            parts.append(
                "<guardrail_rejection>\nYour previous fix was rejected before it could run: "
                f"{rejection}\nFollow the rules in the system prompt.\n</guardrail_rejection>"
            )
        elif previous is not None:
            parts.append(
                f"<previous_attempt number=\"{attempt - 1}\">\nYour previous fix still failed "
                f"the tests listed above. Your earlier diagnosis was:\n{previous.diagnosis}\n"
                "Re-examine the code shown above (it is your previous fix) and correct it.\n"
                "</previous_attempt>"
            )
        parts.append("Diagnose every failing test and return the complete fixed file.")
        return "\n\n".join(parts)

    def _log_run(self, report: Report) -> None:
        if not self.runs_log:
            return
        self.runs_log.parent.mkdir(exist_ok=True)
        record = {
            "run_id": report.run_id,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "model": report.model,
            "status": report.status,
            "confidence": report.confidence,
            "iterations": report.iterations,
            "tests_before": report.tests_before,
            "tests_after": report.tests_after,
            "cited_patterns": report.cited_patterns,
            "steps": [asdict(s) for s in report.steps],
        }
        with self.runs_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    # -- main loop -------------------------------------------------------------------
    def investigate(self, code: str) -> Report:
        report = Report(status="ERROR", confidence=0.0, summary="", original_code=code,
                        run_id=uuid.uuid4().hex[:8], model=self.llm.name)
        try:
            self._investigate(code, report)
        except Exception as exc:  # last-resort guard: never crash the caller
            log.exception("[%s] unexpected error", report.run_id)
            report.status, report.confidence = "ERROR", 0.0
            report.summary = f"Unexpected error: {exc}"
            self._step(report, "ERROR", report.summary)
        self._log_run(report)
        return report

    def _investigate(self, code: str, report: Report) -> None:
        # 1. GUARD
        guard = check_code(code)
        if not guard.ok:
            report.status = "REFUSED"
            report.summary = "Input rejected by guardrails: " + "; ".join(guard.errors)
            self._step(report, "GUARD", report.summary, errors=guard.errors)
            return
        self._step(report, "GUARD", "Input passed static safety and contract checks.")

        # 2. TEST (baseline)
        baseline = run_tests(code)
        report.tests_before = baseline.summary()
        self._step(report, "TEST", f"Baseline: {baseline.summary()}",
                   failing=[f.test_name for f in baseline.failures])
        if baseline.error:
            report.summary = f"The test suite could not run: {baseline.error}"
            report.tests_after = report.tests_before
            self._step(report, "REPORT", report.summary)
            return
        if baseline.all_passed:
            report.status, report.confidence = "NO_BUGS", 1.0
            report.tests_after = report.tests_before
            report.summary = "All tests already pass. No glitches found, so no AI call was made."
            self._step(report, "REPORT", report.summary)
            return

        current_code, current_tests = code, baseline
        proposal: FixProposal | None = None
        rejection: str | None = None
        best: tuple[FixProposal, TestRun, list[RetrievedDoc], list[str], list[str]] | None = None
        # Functions the failing tests actually exercise; edits elsewhere are untested.
        implicated = implicated_functions(
            "\n".join(test_sources([f.test_name for f in baseline.failures]).values()))

        for attempt in range(1, self.max_iterations + 1):
            report.iterations = attempt

            # 3. RETRIEVE: the query is built from the evidence, not just the code.
            # Failing tests are weighted 2x over the code, which mentions every topic.
            evidence = self._failure_text(current_tests) + "\n" + "\n".join(
                test_sources([f.test_name for f in current_tests.failures]).values())
            query = evidence + "\n" + evidence + "\n" + current_code
            docs = self.retriever.search(query, k=self.top_k)
            self._step(report, "RETRIEVE",
                       f"Attempt {attempt}: " + (", ".join(
                           f"{r.doc.doc_id} ({r.score:.2f})" for r in docs) or "no relevant docs"),
                       docs=[{"id": r.doc.doc_id, "score": r.score} for r in docs])

            # 4. PROPOSE
            prompt = self._build_prompt(current_code, current_tests, docs, attempt, proposal, rejection)
            rejection = None
            try:
                proposal = self.llm.propose_fix(SYSTEM_PROMPT, prompt)
            except LLMError as exc:
                self._step(report, "PROPOSE", f"Attempt {attempt}: LLM error: {exc}")
                report.summary = f"The AI could not produce a fix: {exc}"
                break
            self._step(report, "PROPOSE",
                       f"Attempt {attempt}: model cites {proposal.cited_patterns or 'nothing'}, "
                       f"self-confidence {proposal.confidence:.2f}",
                       diagnosis=proposal.diagnosis)

            # 5. VALIDATE
            retrieved_ids = {r.doc.doc_id for r in docs}
            bad_citations = [c for c in proposal.cited_patterns if c not in retrieved_ids]
            if bad_citations:
                self._step(report, "VALIDATE",
                           f"Warning: cited {bad_citations}, which were not retrieved "
                           "(possible hallucination; confidence reduced).")
            fix_guard = check_code(proposal.fixed_code)
            if not fix_guard.ok:
                self._step(report, "VALIDATE",
                           "Proposed fix rejected by guardrails: " + "; ".join(fix_guard.errors))
                rejection = "; ".join(fix_guard.errors)
                continue
            for f in current_tests.failures:
                implicated |= implicated_functions(
                    "\n".join(test_sources([f.test_name]).values()))
            out_of_scope = sorted(changed_functions(code, proposal.fixed_code) - implicated)
            if out_of_scope:
                self._step(report, "VALIDATE",
                           f"Passed guardrails, but also changed {out_of_scope}, which no failing "
                           "test covers (untested edit; flagged for review, confidence reduced).",
                           out_of_scope=out_of_scope)
            else:
                self._step(report, "VALIDATE", "Proposed fix passed guardrails and scope check.")

            # 6. VERIFY
            after = run_tests(proposal.fixed_code)
            self._step(report, "VERIFY", f"Attempt {attempt}: {after.summary()}",
                       failing=[f.test_name for f in after.failures])
            if best is None or after.pass_rate > best[1].pass_rate:
                best = (proposal, after, docs, bad_citations, out_of_scope)
            if after.all_passed:
                break
            if after.error is None:
                current_code, current_tests = proposal.fixed_code, after

        # 7. REPORT
        if best is None:
            # ERROR = the model never answered (quota, network); FAILED = it answered badly.
            llm_failed = any("LLM error" in s.detail for s in report.steps if s.name == "PROPOSE")
            report.status = "ERROR" if llm_failed else "FAILED"
            report.tests_after = report.tests_before
            report.summary = report.summary or "No valid fix was produced."
            self._step(report, "REPORT", report.summary)
            return

        proposal, after, docs, bad_citations, out_of_scope = best
        report.fixed_code = proposal.fixed_code
        report.diagnosis = proposal.diagnosis
        report.changes = proposal.changes
        report.cited_patterns = proposal.cited_patterns
        report.out_of_scope = out_of_scope
        report.tests_after = after.summary()
        report.confidence = score_confidence(after, proposal, docs, bad_citations, out_of_scope)
        if after.all_passed:
            report.status = "FIXED"
            report.summary = (f"Fixed in {report.iterations} attempt(s): {after.summary()}. "
                              "Review the diff before applying.")
            if out_of_scope:
                report.summary += (f" Note: it also changed {', '.join(out_of_scope)}, "
                                   "which no failing test covers; check that edit by hand.")
        elif after.passed > baseline.passed:
            report.status = "PARTIAL"
            report.summary = (f"Improved from {baseline.summary()} to {after.summary()}; "
                              "a human should finish the job.")
        else:
            report.status = "FAILED"
            report.summary = f"No improvement after {report.iterations} attempt(s)."
        self._step(report, "REPORT", f"{report.status} (confidence {report.confidence:.2f})")
