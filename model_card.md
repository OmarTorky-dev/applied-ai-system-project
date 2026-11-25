# Model Card: Glitch Investigator AI

## Overview

| | |
|---|---|
| **System** | Glitch Investigator AI: a retrieval-augmented, test-verified debugging agent |
| **Task** | Diagnose and repair logic bugs in `logic_utils.py`, the game-logic module of a Streamlit number-guessing game |
| **Underlying model** | Google Gemini via `google-genai` (`gemini-3.6-flash` by default; `gemini-3.5-flash-lite` used for some evaluation runs). Claude (`claude-opus-5-5`) is supported as an alternative provider. No model was fine-tuned. |
| **AI features** | RAG over a 9-document bug-pattern knowledge base · agentic plan, act and check loop (up to 3 attempts) · structured JSON output · confidence scoring · guardrails · JSONL logging |
| **Outputs** | Status (FIXED / PARTIAL / FAILED / NO_BUGS / REFUSED / ERROR), confidence 0–1, diagnosis, cited knowledge-base IDs, change list, unified diff, step-by-step trace |
| **Human in the loop** | Always. The agent never applies a fix; a person reviews the diff and decides. |
| **Author** | Omar Torky (CodePath AI110 final project), built with Claude Code as an AI pair programmer |

## Intended use

**For:** learning and demonstrating how to make an LLM-based coding assistant trustworthy, and repairing small, pure-Python modules that have an existing test suite, specifically `logic_utils.py` and variants of it.

**Not for:** production codebases, security-sensitive code, code without tests, or any situation where a fix is applied without a human reading it. The guardrails are tuned to this one module's API (four required functions) and would reject most other files.

## How it decides

1. Static guardrails parse the code with `ast` (without running it) and refuse dangerous imports and calls, oversized input, syntax errors, and a broken function contract.
2. The 16-test suite runs in a temporary folder to collect real evidence of what's broken.
3. A TF-IDF retriever searches the knowledge base, using the failing tests (weighted 2×) plus the code as the query.
4. The LLM receives the code, the failing tests and their source, and the top-3 documents. It must return a diagnosis, the IDs of the documents it used, and the complete fixed file.
5. The fix is guardrail-checked. Citations are checked against what was actually retrieved, and a **scope check** flags any function that was changed even though no failing test calls it.
6. The tests run again. Any remaining failure goes back to step 3 as new evidence.
7. **Confidence** = 60% test pass rate + 20% model self-rating + 20% grounding (valid citations), minus 0.1 per out-of-scope edit, and capped at 0.5 if any test still fails.

## Evaluation summary

Full report: [eval/README.md](eval/README.md).

- **49/49** unit tests pass (scripted fake LLM, no API key).
- **36/37** live runs ended in the expected status across two Gemini models; the one miss was an API outage, reported as ERROR.
- 100% of runs on malicious or invalid input were refused without executing anything.
- Retrieval finds 100% of relevant docs at k=2 for single-bug files, but only 50% at k=3 for a file with four bug classes.
- Live self-correction was observed: a fix that crashed on `"inf"` was caught by the tests and repaired on attempt 2.

---

## Limitations and biases

- **It is only as good as its tests.** "FIXED" means "the 16 tests pass", not "the code is correct". An AI fix passed all 15 original tests while crashing on `"inf"`. I added an invariant test for that, but any behaviour the tests don't pin down is unprotected: a v2 fix still silently changed `"1e3"` from "not a number" to 1000.
- **The knowledge base reflects my own bugs.** All 9 documents come from the specific glitches I found in Module 1 (string comparison, swapped hints, scoring signs, ranges, parsing). The system is biased toward recognising *those* bug families. A novel bug gets weak or irrelevant retrieval, and the model fixes it from the tests alone, without grounding.
- **Retrieval has blind spots.** The query is dominated by failing-test text, so patterns that tests never mention are never retrieved. KB06 ("try/except that hides bugs") was not retrieved in any run, even at k=5. Top-3 also can't cover a file with more than three bug classes.
- **TF-IDF is literal.** It matches words, not meaning, so a bug described with different vocabulary won't match.
- **Model self-confidence is uninformative.** Gemini rated itself 1.00 on every run, including the fix that crashed, which is why that signal is weighted at only 20%. The confidence weights themselves are hand-picked, not learned or calibrated.
- **The scope check is syntactic.** It compares ASTs, so a harmless refactor (an if/else rewritten as a one-line conditional) is flagged as an out-of-scope change, and a semantically meaningful change inside an "allowed" function is not flagged at all.
- **The guardrails are not a sandbox.** AST blocklists stop obvious attacks (`import os`, `eval`, dunder access) but a determined attacker could probably find a gap. Code that passes runs in a normal subprocess with only a timeout.
- **Small, homogeneous evaluation set.** 7 samples, all variations of one 40-line module, so the results say little about other code. The hand-labelled "relevant documents" were labelled by me, the same person who wrote the knowledge base.
- **Provider limits.** Free-tier quotas (about 20 requests per day per model) and 503 overloads mean live runs can fail for reasons unrelated to the code; the agent reports these as ERROR.
- **The model strips comments.** Three of four fixes deleted the file's header comment, a small loss of documentation that tests can't see.

## Misuse and how it's prevented

| Possible misuse | Mitigation in the system | Residual risk |
|---|---|---|
| Submitting malicious code so the agent executes it ("just run the tests") | AST guardrails refuse blocked imports and calls **before anything runs**; the sandbox refuses to execute anything that fails them; 30 s timeout against infinite loops | AST blocklists can be bypassed by a determined attacker; don't expose this to untrusted users without a real sandbox (container, no network) |
| The model inserting harmful code into its "fix" (prompt injection through comments in the submitted file, or a bad model output) | Every AI-generated fix goes through the same guardrails; a rejected fix is never run, and the reason is fed back to the model | Same as above |
| Gaming the tests: a fix that special-cases test inputs or weakens behaviour to go green | System prompt forbids it; the scope check flags edits outside the failing tests' functions; a human reviews every diff | A clever special-case inside an implicated function would pass; human review is the real defence |
| Blindly trusting the output ("it said FIXED, ship it") | Never auto-applies; the CLI refuses to overwrite its input; the report always shows the diff, the cited sources and a confidence score capped at 0.5 if anything fails | People can still click "download" without reading |
| Leaking API keys | Keys live only in a gitignored `.env`; replay mode needs no key at all | A user could paste a key somewhere public |
| Running up API costs or quota | Max 3 attempts per run; no model call at all when tests already pass or input is refused; fails fast on a daily quota | n/a |

## What surprised me while testing reliability

1. **Passing tests did not mean a correct fix.** I expected the test suite to be the safety net. Instead, a hand review found an AI fix that passed all 15 tests but crashed the game on `"inf"`. The general rule I added (`parse_guess` must never raise) then **found a crash in my own Module 1 code** too, on very long decimals. The tester needed testing.
2. **The model was confidently wrong.** It reported self-confidence 1.00 on the attempt that crashed, and on every other run. Its own confidence carried zero information.
3. **My first confidence formula was dangerous.** A partial fix (14/15 tests) scored 0.94, high enough that someone might trust it. My unit tests caught this before any real use, and I added the 0.5 cap.
4. **The model "helps" too much.** On the very first live run, Gemini rewrote a function nobody asked it to touch. The tests still passed, so only reading the diff revealed it.
5. **The agent loop proved itself on its own.** In a live evaluation run, the model repeated the `"inf"` mistake, VERIFY caught it, retrieval shifted to new documents based on the new failure, and attempt 2 passed. I hadn't scripted that; it came out of the design.
6. **Infrastructure failures are common.** Two of my runs on the lite model failed with a 503 overload even after four retries each, and I used up a day's free quota mid-evaluation. Handling "the AI didn't answer" turned out to be as important as handling "the AI answered wrong".

## AI collaboration

I built this project with **Claude Code** (Claude Opus 5.5) as a pair programmer inside VS Code, working one rubric step at a time with a check-in after each. I made the scope and direction calls; Claude proposed designs, wrote most of the code and documents, ran the tests and evaluations, and reported what it found. I reviewed each step before moving on.

### A suggestion I accepted: the scope check

During the first live Gemini run, the model fixed the hint bug correctly but **also rewrote `parse_guess`**, which no failing test pointed to. All tests passed, so the agent reported FIXED with confidence 1.00. Claude flagged that the rewrite silently changed behaviour (`"1e3"` became valid) and suggested a **scope check**: compare each function's AST before and after, work out which functions the failing tests actually call, flag any other function that changed, lower the confidence, and add "keep the fix minimal" to the system prompt. I accepted it because it targets exactly the failure mode that tests can't see, untested edits, and it's cheap and explainable. It's covered by unit tests, and in the evaluation runs that followed, the agent made no out-of-scope edits at all.

### A suggestion I did not accept as written: building the AI layer only on Claude

Claude's original design called the **Claude API only** (`claude-opus-5-5`), with Claude-specific features such as server-side refusal fallbacks. When I went to get a key, I had a **Google Gemini** key, not an Anthropic one, so I didn't accept the Claude-only design as written. Instead, we kept the Claude client but made the system **provider-agnostic**: the agent only depends on a small `propose_fix(system, prompt) -> FixProposal` interface, and we added a Gemini client with the same structured-output schema. Gemini became the default, and Claude still works if an Anthropic key is set. This turned out better than the original plan: switching providers took about 60 lines of code, the record and replay layer works for any model, and later it let me fall back to a different Gemini model when one hit its daily quota.
