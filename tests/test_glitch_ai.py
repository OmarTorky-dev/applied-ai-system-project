"""Tests for the Glitch Investigator system. No API key needed: the LLM is a scripted fake."""

from pathlib import Path

import pytest

from glitch_ai.agent import GlitchInvestigator, score_confidence
from glitch_ai.guardrails import changed_functions, check_code
from glitch_ai.llm import FixProposal, LLMError, ReplayClient
from glitch_ai.retriever import Retriever, load_knowledge_base, tokenize
from glitch_ai.sandbox import TestRun, parse_pytest_output, run_tests

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
CORRECT = (ROOT / "logic_utils.py").read_text(encoding="utf-8")


def sample(name: str) -> str:
    return (SAMPLES / f"{name}.py").read_text(encoding="utf-8")


# The minimal correct fix for samples/lying_hints.py: only check_guess changes.
LYING_FIXED = sample("lying_hints").replace(
    '    g, s = str(guess), str(secret)\n'
    '    if g > s:\n'
    '        return "Too High", "📈 Go HIGHER!"\n'
    '    return "Too Low", "📉 Go LOWER!"',
    '    if guess > secret:\n'
    '        return "Too High", "📉 Go LOWER!"\n'
    '    return "Too Low", "📈 Go HIGHER!"')
assert LYING_FIXED != sample("lying_hints")


class FakeLLM:
    """Returns pre-scripted proposals in order and records every prompt it receives."""

    name = "fake"

    def __init__(self, proposals):
        self.proposals = list(proposals)
        self.prompts = []

    def propose_fix(self, system, prompt):
        self.prompts.append(prompt)
        item = self.proposals.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def proposal(code, cited=("KB02",), confidence=0.9):
    return FixProposal(diagnosis="test diagnosis", cited_patterns=list(cited),
                       changes=["change"], fixed_code=code, confidence=confidence)


@pytest.fixture(scope="module")
def retriever():
    return Retriever(load_knowledge_base())


def agent(llm, retriever, **kw):
    return GlitchInvestigator(llm, retriever=retriever, runs_log=None, **kw)


# --- Retrieval ------------------------------------------------------------------

def test_knowledge_base_loads_all_documents():
    ids = [d.doc_id for d in load_knowledge_base()]
    assert ids == [f"KB0{i}" for i in range(1, 10)]


def test_tokenize_splits_snake_case():
    assert {"check_guess", "check", "guess"} <= set(tokenize("check_guess(9, 50)"))


@pytest.mark.parametrize("query, expected", [
    ("guess 9 compared as string '9' > '50' str int", "KB01"),
    ("Too High message says Go HIGHER swapped", "KB02"),
    ("wrong guess adds points on even attempt score", "KB04"),
    ("hard range is smaller than normal difficulty", "KB05"),
    ("parse_guess blank whitespace strip input", "KB07"),
])
def test_retriever_ranks_the_right_pattern_first(retriever, query, expected):
    assert retriever.search(query, k=3)[0].doc.doc_id == expected


def test_retriever_returns_nothing_for_unrelated_query(retriever):
    assert retriever.search("banana smoothie recipe with oat milk", k=3) == []


# --- Guardrails -----------------------------------------------------------------

def test_guardrail_accepts_correct_logic():
    assert check_code(CORRECT).ok


@pytest.mark.parametrize("snippet, reason", [
    ("import os", "Blocked import 'os'"),
    ("from subprocess import run", "Blocked import from 'subprocess'"),
    ("x = eval('1')", "Blocked call 'eval()'"),
    ("x = open('f')", "Blocked call 'open()'"),
    ("x = ().__class__", "dunder"),
])
def test_guardrail_blocks_dangerous_code(snippet, reason):
    result = check_code(CORRECT + "\n" + snippet + "\n")
    assert not result.ok
    assert any(reason in e for e in result.errors)


def test_guardrail_enforces_function_contract():
    broken = CORRECT.replace("def check_guess(guess, secret):", "def check_guess(guess):")
    assert any("check_guess" in e for e in check_code(broken).errors)


def test_guardrail_rejects_empty_and_syntax_errors():
    assert not check_code("   ").ok
    assert "Syntax error" in check_code("def f(:\n  pass").errors[0]


# --- Sandbox --------------------------------------------------------------------

def test_sandbox_correct_code_passes_everything():
    run = run_tests(CORRECT)
    assert run.all_passed and run.total == 15


def test_sandbox_reports_specific_failures():
    run = run_tests(sample("haywire_scoring"))
    assert {f.test_name for f in run.failures} == {
        "test_wrong_guess_never_adds_points", "test_first_try_win_scores_100"}


def test_sandbox_refuses_to_execute_unsafe_code():
    run = run_tests(sample("malicious"))
    assert run.error and "guardrail" in run.error
    assert not (ROOT / "pwned.txt").exists()


def test_parse_pytest_output_collection_error():
    run = parse_pytest_output("E   ImportError: boom\n1 error in 0.1s")
    assert run.error == "ImportError: boom"


# --- Agent loop -----------------------------------------------------------------

def test_agent_fixes_bug_on_first_attempt(retriever):
    llm = FakeLLM([proposal(LYING_FIXED, cited=["KB01", "KB02"])])
    report = agent(llm, retriever).investigate(sample("lying_hints"))
    assert report.status == "FIXED"
    assert report.iterations == 1
    assert report.tests_before == "11/15 tests passed"
    assert report.tests_after == "15/15 tests passed"
    assert report.confidence >= 0.9
    # RAG is really in the prompt: the retrieved document text reaches the model.
    assert 'id="KB02"' in llm.prompts[0]
    assert "test_single_digit_guess_is_compared_numerically" in llm.prompts[0]


def test_agent_retries_with_feedback_after_a_bad_fix(retriever):
    half_fixed = sample("lying_hints").replace(
        '"📈 Go HIGHER!"\n    return "Too Low", "📉 Go LOWER!"',
        '"📉 Go LOWER!"\n    return "Too Low", "📈 Go HIGHER!"')
    llm = FakeLLM([proposal(half_fixed, cited=["KB02"]), proposal(LYING_FIXED, cited=["KB01"])])
    report = agent(llm, retriever).investigate(sample("lying_hints"))
    assert report.status == "FIXED"
    assert report.iterations == 2
    assert "previous_attempt" in llm.prompts[1]
    verify_steps = [s.detail for s in report.steps if s.name == "VERIFY"]
    assert verify_steps[0] != verify_steps[1]


def test_agent_rejects_unsafe_fix_and_tells_the_model(retriever):
    evil = "import os\n" + LYING_FIXED
    llm = FakeLLM([proposal(evil), proposal(LYING_FIXED, cited=["KB02"])])
    report = agent(llm, retriever).investigate(sample("lying_hints"))
    assert report.status == "FIXED"
    assert "guardrail_rejection" in llm.prompts[1]
    assert any("rejected by guardrails" in s.detail for s in report.steps)


def test_agent_skips_the_model_when_no_bugs(retriever):
    llm = FakeLLM([])
    report = agent(llm, retriever).investigate(CORRECT)
    assert report.status == "NO_BUGS" and llm.prompts == []


def test_agent_refuses_malicious_input_without_calling_model(retriever):
    llm = FakeLLM([])
    report = agent(llm, retriever).investigate(sample("malicious"))
    assert report.status == "REFUSED" and llm.prompts == []


def test_agent_reports_partial_progress(retriever):
    # Fixes the hint messages but keeps the string comparison: 13/15.
    partial = sample("lying_hints").replace(
        '"📈 Go HIGHER!"\n    return "Too Low", "📉 Go LOWER!"',
        '"📉 Go LOWER!"\n    return "Too Low", "📈 Go HIGHER!"')
    llm = FakeLLM([proposal(partial)])
    report = agent(llm, retriever, max_iterations=1).investigate(sample("lying_hints"))
    assert report.status == "PARTIAL"
    assert report.confidence < 0.9


def test_agent_handles_llm_errors_gracefully(retriever):
    llm = FakeLLM([LLMError("Rate limited")])
    report = agent(llm, retriever).investigate(sample("lying_hints"))
    assert report.status == "FAILED"
    assert "Rate limited" in report.summary


def test_hallucinated_citation_lowers_confidence(retriever):
    honest = agent(FakeLLM([proposal(LYING_FIXED, cited=["KB02"])]), retriever)
    liar = agent(FakeLLM([proposal(LYING_FIXED, cited=["KB02", "KB99"])]), retriever)
    a = honest.investigate(sample("lying_hints"))
    b = liar.investigate(sample("lying_hints"))
    assert b.confidence < a.confidence
    assert any("KB99" in s.detail for s in b.steps if s.name == "VALIDATE")


def test_confidence_is_zero_when_tests_cannot_run():
    assert score_confidence(TestRun(error="boom"), None, [], []) == 0.0


def test_replay_client_raises_clear_error_for_unknown_prompt(tmp_path):
    with pytest.raises(LLMError, match="No recording"):
        ReplayClient(directory=tmp_path).propose_fix("sys", "never seen")


# --- Scope check (added after a live Gemini run rewrote parse_guess unprompted) ------

def test_changed_functions_ignores_comments_and_docstrings():
    edited = CORRECT.replace('"""Return (low, high) inclusive range for a given difficulty."""',
                             '"""A different docstring."""') + "\n# a new comment\n"
    assert changed_functions(CORRECT, edited) == set()


def test_changed_functions_detects_logic_edit():
    edited = CORRECT.replace("return current_score - 5", "return current_score - 6")
    assert changed_functions(CORRECT, edited) == {"update_score"}


def test_agent_flags_out_of_scope_edits(retriever):
    # lying_hints only breaks check_guess. This "fix" is correct but also rewrites parse_guess.
    overreach = LYING_FIXED.replace('int(float(raw)) if "." in raw else int(raw)',
                                    'int(float(raw))')
    assert overreach != LYING_FIXED
    clean = agent(FakeLLM([proposal(LYING_FIXED, cited=["KB02"])]), retriever)
    messy = agent(FakeLLM([proposal(overreach, cited=["KB02"])]), retriever)
    a = clean.investigate(sample("lying_hints"))
    b = messy.investigate(sample("lying_hints"))
    assert a.status == b.status == "FIXED"
    assert a.out_of_scope == [] and b.out_of_scope == ["parse_guess"]
    assert b.confidence < a.confidence
    assert "parse_guess" in b.summary
