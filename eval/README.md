# Evaluation: is the Glitch Investigator reliable?

This folder holds every evaluation run, the raw logs behind the README's sample outputs, and
a structured review of fix quality. Everything here was produced by [`evaluate.py`](../evaluate.py)
or [`investigate.py`](../investigate.py). Reproduce the offline numbers with:

```bash
python evaluate.py                       # replay mode: free, offline, deterministic
python -m pytest                         # 49 unit tests
```

## TL;DR

| Experiment | Model | Oracle | Result |
|---|---|---|---|
| Unit tests (fake LLM) | none | n/a | **49 / 49 pass** |
| Live, top-k=3, 3 repeats | gemini-3.6-flash | v1 (15 tests) | **15/15** runs matched expected status; 12/12 buggy runs FIXED, all on the 1st attempt; consistency 100% |
| Live, top-k=5 | gemini-3.6-flash | v1 (15 tests) | **7/7**; citation coverage on the hardest sample rose from 0.50 to 0.83 |
| v1 fixes re-checked against the v2 oracle | (recorded) | v2 (16 tests) | **1 of 4 AI fixes crashes on `"inf"`**; 2 more inherited a latent crash from the *human* code |
| Live, top-k=3, 3 repeats | gemini-3.5-flash-lite | v2 (16 tests) | **14/15**; 11/12 FIXED; the one miss was a Google 503 outage (reported as ERROR, not a bad fix); **1 run self-corrected on attempt 2** |
| Replay of recorded v2 runs | (recorded) | v2 (16 tests) | **7/7** |
| Retrieval only (no model) | none | n/a | Single-bug samples: 100% of relevant docs in the top 2. Four-bug sample: 50% at k=3, 83% at k=5 |

**In one line:** 36 of 37 live runs ended in the expected status (36 of 36 if you exclude the run lost to a
Google 503 outage); confidence on correct fixes averaged 1.00, but evaluation showed that **"tests pass" was not the same
as "correct"** until I added a robustness invariant to the oracle. After that the agent caught and
fixed its own crash bug live.

---

## 1. End-to-end accuracy and consistency

Expected outcomes: the 4 buggy samples should be **FIXED**, `clean` should be **NO_BUGS** (with no model
call) and `malicious` / `syntax_error` should be **REFUSED** (never executed).

- **v1, gemini-3.6-flash, 3 repeats:** [v1_15_tests/results_live_k3.md](v1_15_tests/results_live_k3.md). Every run matched. All 12
  buggy runs were fixed on the first attempt and cited the same docs every time (100% consistent).
- **v2, gemini-3.5-flash-lite, 3 repeats:** [results_live_lite_k3.md](results_live_lite_k3.md). 14/15. `haywire_scoring` run 2
  hit `503 UNAVAILABLE` four times in a row; the agent stopped retrying and reported **ERROR**
  ("the AI could not produce a fix"), not a fake success. The same outage during recording is kept in
  [sample_runs/haywire_scoring_503_error.txt](sample_runs/haywire_scoring_503_error.txt).
- **Guardrail cases were 100% reliable** in every run (they're deterministic and involve no model).

## 2. The key finding: passing tests ≠ correct (v1 → v2)

While reviewing the v1 diffs by hand, I tried edge-case inputs on the AI's `fragile_parsing` fix.
It passed all 15 tests, yet:

```text
'inf'                   -> CRASH OverflowError cannot convert float infinity to integer
'1e3'                   -> (True, 1000, None)        # original code rejects this
'12345678901234567890'  -> (True, 12345678901234567168, None)   # precision lost
```

A player typing `inf` would crash the game. The tests never tried it. So instead of special-casing
`"inf"`, I added a general **invariant** to the oracle, `test_parse_guess_never_crashes_on_any_text`
(10 hostile inputs; whatever a player types, `parse_guess` must return a result and never raise).

Re-checking the four recorded v1 fixes against the new oracle ([v1_fixes_vs_v2_oracle.txt](v1_fixes_vs_v2_oracle.txt)):

| v1 fix for | v2 result | Whose bug? |
|---|---|---|
| fragile_parsing | 15/16: crashes | **The AI's**: its rewrite of `parse_guess` introduced the crash |
| lying_hints | 15/16: crashes | **Mine (Module 1)**: the hand-written `parse_guess` crashes on `"1" + "0"*400 + ".0"`; the AI correctly left it alone |
| haywire_scoring | 15/16: crashes | **Mine**, same inherited bug |
| original_starter | 16/16 | n/a (`except Exception` catches everything) |

So the invariant found a crash in the AI's code **and** a latent crash in the human-written code. I
fixed `logic_utils.py` (`except (ValueError, OverflowError)`).

**The payoff, live** ([self_correction_trace.json](self_correction_trace.json)): in the v2 run, the model made
*the same mistake again* on attempt 1. This time VERIFY caught it and the loop fixed it:

```text
TEST      Baseline: 14/16 tests passed
RETRIEVE  Attempt 1: KB05 (0.45), KB07 (0.37), KB02 (0.26)
PROPOSE   Attempt 1: model cites ['KB05', 'KB07'], self-confidence 1.00
VERIFY    Attempt 1: 15/16 tests passed   failing: test_parse_guess_never_crashes_on_any_text
RETRIEVE  Attempt 2: KB07 (0.46), KB02 (0.26), KB08 (0.26)
PROPOSE   Attempt 2: model cites ['KB07', 'KB08'], self-confidence 1.00
VERIFY    Attempt 2: 16/16 tests passed
REPORT    FIXED (confidence 1.00)
```

Under the v1 oracle, attempt 1 would have been reported as FIXED with confidence 1.00. Note the model
said "self-confidence 1.00" on the attempt that crashed: **the model's self-rating carried no
information in any of my runs**, which is why it's only 20% of the confidence score.

## 3. Retrieval quality (no model involved)

Each sample's relevant knowledge-base docs are hand-labelled in `evaluate.py`. Share found in the top-k:

| Sample | Relevant | k=1 | k=2 | k=3 | k=4 | k=5 |
|---|---|---|---|---|---|---|
| lying_hints | KB01, KB02 | 0.50 | **1.00** | 1.00 | 1.00 | 1.00 |
| haywire_scoring | KB03, KB04 | 0.50 | **1.00** | 1.00 | 1.00 | 1.00 |
| fragile_parsing | KB05, KB07 | 0.50 | **1.00** | 1.00 | 1.00 | 1.00 |
| original_starter | KB01–KB06 | 0.17 | 0.33 | 0.50 | 0.67 | 0.83 |

- Retrieval is excellent for single-bug files but **top-3 can't cover a file with four bug classes**.
  With k=3 the model still fixed the scoring bugs, but without a retrieved doc to ground them. With k=5
  ([v1_15_tests/results_live_k5.md](v1_15_tests/results_live_k5.md)) it cited KB03 and KB04 as well (citation coverage 0.50 → 0.83).
- **KB06 (try/except that hides bugs) is never retrieved**, even at k=5. The query is built mostly from
  failing tests, and no test mentions exceptions. That's a known blind spot of evidence-weighted retrieval.
- I kept k=3 as the default: it's enough for typical single-bug inputs and keeps prompts short. A
  better future fix is an adaptive k (retrieve more when more tests fail).

## 4. Fix-quality review (structured human review)

Tests say whether a fix works; this review asks whether it's a fix a careful developer would accept.
Each recorded v2 fix was read in full and probed with edge-case inputs (`inf`, `1e3`, `" 42 "`, a
30-digit decimal). **Reviewers:** first pass by my AI assistant (Claude), then checked by me.
*(Omar: confirm each verdict below, then delete this note.)*

| Sample | Model | Criteria | Result | Notes |
|---|---|---|---|---|
| lying_hints | gemini-3.5-flash-lite | Fixes root cause, minimal diff, no new crashes | ✅ Pass | Only `check_guess` changed; removed the `str()` comparison instead of patching messages |
| haywire_scoring | gemini-3.5-flash-lite | Same | ✅ Pass | Only `update_score` changed; removed the parity check entirely |
| fragile_parsing | gemini-3.6-flash | Same | ⚠️ Pass with note | No crashes, but now accepts `"1e3"` as 1000 (untested behaviour change) |
| original_starter | gemini-3.5-flash-lite | Same | ✅ Pass | Changed exactly the 3 broken functions, left `parse_guess` alone, deleted the hiding `try/except` |
| *all four* | both | Preserves documentation | ❌ Fail | Three of four fixes deleted the file's header comment. Cosmetic, but it's why a human should read every diff |
| v1 fragile_parsing | gemini-3.6-flash | No new crashes | ❌ Fail | Crashed on `"inf"`; led to the v2 invariant (§2) |

## 5. Unit tests: 49 / 49

`python -m pytest` runs 16 game-logic tests (the agent's oracle) and 33 AI-system tests with a scripted fake LLM.
They cover retrieval ranking, guardrails (5 attack types), the retry loop, rejection of an unsafe fix,
hallucinated-citation penalties, the scope check, PARTIAL and ERROR reporting, and the 0.5 confidence cap.

## Files

| File | What |
|---|---|
| `results_replay.*` | v2 replay run (offline, reproducible) |
| `results_live_lite_k3.*`, `console_live_lite_k3.txt` | v2 live consistency run |
| `v1_15_tests/` | All v1 results, logs and recordings (before the invariant test) |
| `v1_fixes_vs_v2_oracle.txt` | v1 AI fixes re-tested against the v2 oracle |
| `self_correction_trace.json` | Full trace of the live two-attempt self-correction |
| `sample_runs/` | Complete CLI output for each sample (the README's sample interactions) |
