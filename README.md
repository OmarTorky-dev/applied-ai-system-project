# 🕵️ Glitch Investigator AI

**An AI debugging agent that finds, explains and fixes logic bugs, grounds every fix in a knowledge base of known bug patterns, and only reports success when the test suite proves it.**

You give it a broken version of a game's logic module. It runs the tests to see what is really broken, retrieves the matching bug patterns, asks an LLM for a diagnosis and a fix, checks that fix with guardrails and the tests, and retries with the new evidence if anything still fails. The result is a status, a confidence score, a readable diagnosis and a diff that **a human approves before anything changes**.

> AI-written code often *looks* right while being quietly wrong. This project is about building an AI tool you can actually trust: one that shows its evidence, cites its sources, refuses unsafe input, and says how sure it is.

---

## 📦 Where this started: Game Glitch Investigator (Module 1)

This project extends my Module 1 project, **[Game Glitch Investigator: The Impossible Guesser](https://github.com/OmarTorky-dev/Game-Glitch-Investigator)**. In that project I was given a Streamlit number-guessing game written by an AI that "ran away": the hints lied, New Game didn't reset, scoring went haywire and Hard was easier than Normal. I reproduced each bug, fixed them by hand, moved the game logic into `logic_utils.py`, and grew the test suite from 3 to 15 tests. The original write-up is preserved in [docs/module1_README.md](docs/module1_README.md) and [docs/module1_reflection.md](docs/module1_reflection.md).

**What's new in the final project:** the manual debugging process I followed in Module 1 (reproduce, look up the bug pattern, fix the root cause, re-test) is now an **AI agent** with retrieval (RAG), a self-checking fix loop, guardrails, confidence scoring, logging and an evaluation harness. It's built into the original Streamlit app as a new tab and is also available as a CLI.

---

## 🏗️ Architecture overview

Full diagram source: [diagrams/architecture.mmd](diagrams/architecture.mmd)

```mermaid
flowchart LR
    U([👤 Developer]) -->|buggy logic_utils.py| G{GUARD<br/>AST guardrails}
    G -->|unsafe| X[REFUSED]
    G -->|ok| T[TEST<br/>pytest baseline]
    T -->|all pass| N[NO_BUGS<br/>no model call]
    T -->|failing tests| R[RETRIEVE<br/>TF-IDF over 9<br/>bug-pattern docs]
    R --> P[PROPOSE<br/>LLM: diagnosis,<br/>fix, citations]
    P --> V{VALIDATE<br/>guardrails, citations,<br/>scope check}
    V -->|rejected| R
    V --> F{VERIFY<br/>re-run pytest}
    F -->|still failing, ≤3 tries| R
    F -->|all pass| REP[REPORT<br/>status, confidence,<br/>diff, trace]
    REP --> H{{👤 Human review}}
    H -->|approve| A[Apply fix, play game]
```

| Component | File | What it does |
|---|---|---|
| **Guardrails** | [glitch_ai/guardrails.py](glitch_ai/guardrails.py) | Parses code with `ast` *without running it*. Blocks dangerous imports (`os`, `subprocess`, `socket`…) and calls (`eval`, `exec`, `open`…), enforces size limits and the four-function API contract. Also powers the **scope check**, which flags edits to functions no failing test covers. |
| **Sandbox** | [glitch_ai/sandbox.py](glitch_ai/sandbox.py) | Runs the 16 behaviour tests against the candidate code in a temp folder, in a subprocess with a 30 s timeout. Refuses to run anything the guardrails reject. |
| **Retriever (RAG)** | [glitch_ai/retriever.py](glitch_ai/retriever.py), [knowledge_base/](glitch_ai/knowledge_base/) | TF-IDF search over 9 bug-pattern documents I wrote from my Module 1 bug log (string-vs-int comparison, swapped hints, off-by-one, scoring sign errors…). The query is the **failing tests**, weighted 2×, plus the code. |
| **LLM client** | [glitch_ai/llm.py](glitch_ai/llm.py) | Calls Gemini (`gemini-3.6-flash` by default; set `GEMINI_MODEL` to change it) or Claude with **structured JSON output** (diagnosis, cited doc IDs, change list, full fixed file, self-confidence). `record` mode saves responses; `replay` mode reproduces them offline. |
| **Agent** | [glitch_ai/agent.py](glitch_ai/agent.py) | The plan, act and check loop shown above, plus confidence scoring and a JSONL trace of every step in `logs/runs.jsonl`. |
| **Interfaces** | [app.py](app.py), [investigator_ui.py](investigator_ui.py), [investigate.py](investigate.py) | Streamlit app with a 🎮 **Play** tab (the original game) and a 🕵️ **AI Investigator** tab, plus a CLI. |

**Where humans and tests check the AI:** the test suite checks every proposed fix before it is reported; the guardrails check both the input and the AI's output; and nothing is ever applied automatically, because a person reads the diagnosis, confidence and diff and decides.

---

## ⚙️ Setup

Requires **Python 3.10+** (developed on 3.14, Windows 11).

```bash
# 1. Clone and enter the project
git clone https://github.com/OmarTorky-dev/applied-ai-system-project.git
cd applied-ai-system-project

# 2. Create a virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

# 3. (Optional) add an API key to run the model live
copy .env.example .env          # Windows  (cp on macOS / Linux)
# then edit .env and set GEMINI_API_KEY=...  (free at https://aistudio.google.com)
#   or ANTHROPIC_API_KEY=...  to use Claude instead
```

**No API key? Everything still runs.** Without a key the agent uses **replay mode**: it answers from the real Gemini responses recorded in [recordings/](recordings/), so the bundled samples reproduce exactly the outputs shown below. (Free Gemini keys allow about 20 requests per day per model. If you hit the limit, set `GEMINI_MODEL=gemini-3.5-flash-lite` in `.env`.)

```bash
# Run the tests (49 tests, no API key needed)
python -m pytest

# Investigate a buggy file from the command line
python investigate.py samples/lying_hints.py

# Launch the app (game + AI Investigator tab)
python -m streamlit run app.py
```

CLI options: `--mode {auto,live,record,replay}`, `--provider {auto,gemini,claude}`, `--max-iters N`, `--out fixed.py` (writes the fix to a new file; it refuses to overwrite the input).

---

## 💬 Sample interactions

All outputs below come from real runs against Gemini, made in `record` mode so they can be replayed. The model is shown in each run header. Long sections are trimmed where marked `[...]`; the complete logs with every diff are in [eval/sample_runs/](eval/sample_runs/). Reproduce any of them without a key: `python investigate.py samples/<name>.py --mode replay`.

### 1. Lying hints: RAG retrieves the right bug patterns and the fix is verified

**Input:** [samples/lying_hints.py](samples/lying_hints.py), where `check_guess` compares numbers as strings and has its hint messages swapped (the exact bug from Module 1).

```text
$ GEMINI_MODEL=gemini-3.5-flash-lite python investigate.py samples/lying_hints.py --mode record --provider gemini

=== Glitch Investigator run c2ad25ed  [gemini (gemini-3.5-flash-lite) [recording]] ===
🛡️  GUARD     Input passed static safety and contract checks.
🧪 TEST      Baseline: 12/16 tests passed
📚 RETRIEVE  Attempt 1: KB02 (0.53), KB01 (0.37), KB07 (0.26)
🤖 PROPOSE   Attempt 1: model cites ['KB01', 'KB02'], self-confidence 1.00
✅ VALIDATE  Proposed fix passed guardrails and scope check.
🔁 VERIFY    Attempt 1: 16/16 tests passed
📋 REPORT    FIXED (confidence 1.00)

--- Result ---
Status      : FIXED
Confidence  : 1.00
Tests       : before = 12/16 tests passed | after = 16/16 tests passed
Grounded in : KB01, KB02
Summary     : Fixed in 1 attempt(s): 16/16 tests passed. Review the diff before applying.

Diagnosis:
The check_guess function had two bugs: first, it converted guess and secret to strings before
comparing them, causing lexicographic string comparisons instead of numerical ones (KB01).
Second, the hint messages and symbols for 'Too High' and 'Too Low' were swapped (KB02).

Proposed diff:
[... comment-only lines trimmed ...]
 def check_guess(guess, secret):
     if guess == secret:
         return "Win", "🎉 Correct!"
-    g, s = str(guess), str(secret)
-    if g > s:
-        return "Too High", "📈 Go HIGHER!"
-    return "Too Low", "📉 Go LOWER!"
+    if guess > secret:
+        return "Too High", "📉 Go LOWER!"
+    return "Too Low", "📈 Go HIGHER!"
```

Using only the failing tests as the query, the retriever ranked **KB02 (swapped hint messages)** and **KB01 (numbers compared as strings)** highest. The model's diagnosis uses those documents and cites them by ID, and only `check_guess` was changed.

### 2. The agent catches its own mistake and fixes it (live self-correction)

**Input:** [samples/fragile_parsing.py](samples/fragile_parsing.py): `parse_guess` crashes on blank input, and Hard's range is smaller than Normal's. Trace from the live evaluation ([eval/self_correction_trace.json](eval/self_correction_trace.json)):

```text
$ GEMINI_MODEL=gemini-3.5-flash-lite python evaluate.py --mode live --provider gemini --repeats 3 --tag live_lite_k3
[... fragile_parsing, run 2 ...]
GUARD     Input passed static safety and contract checks.
TEST      Baseline: 14/16 tests passed      failing: test_hard_range_is_wider_than_normal, test_parse_guess_empty_and_blank
RETRIEVE  Attempt 1: KB05 (0.45), KB07 (0.37), KB02 (0.26)
PROPOSE   Attempt 1: model cites ['KB05', 'KB07'], self-confidence 1.00
VALIDATE  Proposed fix passed guardrails and scope check.
VERIFY    Attempt 1: 15/16 tests passed      failing: test_parse_guess_never_crashes_on_any_text
RETRIEVE  Attempt 2: KB07 (0.46), KB02 (0.26), KB08 (0.26)
PROPOSE   Attempt 2: model cites ['KB07', 'KB08'], self-confidence 1.00
VALIDATE  Proposed fix passed guardrails and scope check.
VERIFY    Attempt 2: 16/16 tests passed
REPORT    FIXED (confidence 1.00)
```

The model's first fix crashed on the input `"inf"`, while rating itself 1.00 confident. VERIFY caught it, the agent re-retrieved using the *new* failure as evidence, and the second attempt passed. Earlier in the project the same mistake slipped through as FIXED; the [evaluation](eval/README.md#2-the-key-finding-passing-tests--correct-v1--v2) explains how I found and closed that gap.

### 3. The full original starter code: four bug classes, fixed in one pass

**Input:** [samples/original_starter.py](samples/original_starter.py), the original AI-generated logic with every bug at once, including the `try/except TypeError` "safety net" that hid the string comparison.

```text
$ GEMINI_MODEL=gemini-3.5-flash-lite python investigate.py samples/original_starter.py --mode record --provider gemini
[...]
🧪 TEST      Baseline: 9/16 tests passed
📚 RETRIEVE  Attempt 1: KB02 (0.47), KB01 (0.32), KB05 (0.32)
🤖 PROPOSE   Attempt 1: model cites ['KB01', 'KB02', 'KB05'], self-confidence 1.00
✅ VALIDATE  Proposed fix passed guardrails and scope check.
🔁 VERIFY    Attempt 1: 16/16 tests passed
📋 REPORT    FIXED (confidence 1.00)
[...]
Changes:
  - Updated Hard difficulty range to (1, 200) in get_range_for_difficulty.
  - Removed string conversion and type fallback in check_guess to ensure proper numerical comparison.
  - Fixed hint message strings in check_guess so that Too High suggests going lower and Too Low suggests going higher.
  - Corrected update_score to never add points on wrong guesses and to award 100 points for a first-try win.
```

9/16 → 16/16, and the scope check confirmed `parse_guess` was left alone. One honest caveat: only the top 3 docs are retrieved, so the scoring docs (KB03/KB04) weren't in the prompt and the scoring part of this fix wasn't grounded in a document. See [eval §3](eval/README.md#3-retrieval-quality-no-model-involved).

### 4. Guardrails and graceful failure

**Malicious input is refused before anything runs.** [samples/malicious.py](samples/malicious.py) looks like game logic but calls `os.system(...)`:

```text
$ python investigate.py samples/malicious.py --mode record --provider gemini

=== Glitch Investigator run 42ea9347  [gemini (gemini-3.6-flash) [recording]] ===
🛡️  GUARD     Input rejected by guardrails: Blocked import 'os' (line 3).

--- Result ---
Status      : REFUSED
Confidence  : 0.00
Tests       : before = n/a | after = n/a
Summary     : Input rejected by guardrails: Blocked import 'os' (line 3).
[exit code 1]
```

The code was never executed and the model was never called. The same checks run on every AI-generated fix, so the model can't sneak `import os` into its output either; the unit tests cover that.

**No bugs, no model call:**

```text
$ python investigate.py samples/clean.py --mode record --provider gemini
[...]
🛡️  GUARD     Input passed static safety and contract checks.
🧪 TEST      Baseline: 16/16 tests passed
📋 REPORT    All tests already pass. No glitches found, so no AI call was made.
```

**API outage:** reported as ERROR, never as a fake fix ([full log](eval/sample_runs/haywire_scoring_503_error.txt)):

```text
🤖 PROPOSE   Attempt 1: LLM error: Gemini API error 503: This model is currently experiencing high demand. [...]
📋 REPORT    The AI could not produce a fix: Gemini API error 503: [...]
```

### In the app

`python -m streamlit run app.py` opens the original game in the **🎮 Play** tab. The **🕵️ AI Investigator** tab lets you pick a sample or paste your own `logic_utils.py`, choose live or replay mode, and see the status, confidence, before and after test counts, the full agent trace, the diagnosis with its cited documents, and the diff, plus a button to download the fix. Nothing is applied automatically.

---

## 🧠 Design decisions

| Decision | Why | Trade-off |
|---|---|---|
| **Tests are the judge, not the model.** A fix only counts as FIXED when the real pytest suite passes. | LLMs are confidently wrong sometimes. Running the tests turns "looks right" into "is right" for everything the tests cover. | Only as good as the tests. A bug with no test can slip through, which is why the scope check exists. |
| **Retrieval query = failing tests (weighted 2×) + code** | My first version searched with the code alone, and KB07 (parsing) ranked in the top 3 for *every* sample because the code mentions everything. The failing tests are the actual evidence of what's broken. | Retrieval depends on good test names and assertions. |
| **TF-IDF in plain Python instead of embeddings or a vector DB** | Nine short documents. TF-IDF is deterministic, explainable (scores are shown in the trace), fast, needs no extra service, and is easy to unit-test. | Misses synonyms. It wouldn't scale to thousands of documents without switching to embeddings. |
| **Static AST guardrails before anything executes** | Running untrusted code to "see if it works" is exactly what an attacker wants. AST checks catch dangerous imports and calls without running a line. | A determined attacker could find gaps (this isn't a real sandbox). It's defence in depth for a teaching project, not a security boundary. |
| **Scope check** (flag edits to functions no failing test covers) | Added after a live run where the model rewrote `parse_guess` unprompted. The tests still passed, but the change silently started accepting inputs like `"1e3"`. | It compares ASTs, so a harmless refactor (an if/else rewritten as a one-line conditional) is also flagged. It warns and lowers confidence instead of blocking. |
| **Confidence = 60% tests + 20% model + 20% grounding, minus scope penalties, capped at 0.5 if any test fails** | Objective evidence should dominate. The model's own rating is weighted lightly because, as it turned out, it always says 1.00. | The weights are hand-picked, not learned. |
| **Structured output (JSON schema via Pydantic)** | The agent needs the fixed file, the citations and the confidence as separate fields, not prose to scrape. | Ties the client code to providers that support schemas (both Gemini and Claude do). |
| **Record and replay** | Anyone can reproduce the documented results with no key and no cost, and the README outputs are verifiable. | Replay only covers the bundled samples; new code needs a live key. |
| **Provider-agnostic client (Gemini by default, Claude supported)** | I built for Claude first, but the key I had was for Gemini. Swapping providers was a ~60-line change because the agent only depends on a `propose_fix()` interface. | Two SDKs to maintain. |
| **Human approval required, never auto-apply** | The agent edits code that runs a game other people play. A person should read the diff. | Slower than auto-fixing, deliberately. |

---

## 🧪 Testing & evaluation summary

Full report: **[eval/README.md](eval/README.md)**. Reproduce offline with `python -m pytest` and `python evaluate.py`.

| Check | Result |
|---|---|
| Unit tests (`python -m pytest`, no API key) | **49 / 49 pass**: 16 game-logic tests (the agent's oracle) + 33 AI-system tests using a scripted fake LLM |
| Live runs, 3 repeats × 4 buggy samples + 3 control samples, two models | **36 / 37** ended in the expected status. The one miss was a Google 503 outage, correctly reported as ERROR |
| Consistency across repeats | gemini-3.6-flash: 100% on every sample. gemini-3.5-flash-lite: 100%, except one sample lost to the outage |
| Guardrail samples (malicious, syntax error) | Refused in **every** run, never executed |
| Retrieval (hand-labelled relevant docs) | 100% coverage at k=2 for single-bug files; 50% at k=3 and 83% at k=5 for the four-bug file |
| Confidence | Averaged 1.00 on verified fixes. The model's *self*-rating was 1.00 every single time, even on a fix that crashed |

**What the evaluation taught me:**
- **Passing tests isn't the same as correct.** An AI fix passed all 15 original tests but crashed the game on the input `"inf"`. Instead of special-casing that input, I added a general rule to the oracle (`parse_guess` must never raise, whatever the player types). That rule *also* found a latent crash in my own Module 1 code (fixed). Afterwards, the agent caught and repaired the same mistake live, on its second attempt.
- **The model's self-confidence is worthless as a signal**, so it's only 20% of the score; test evidence is 60%.
- **Confidence needed a ceiling:** a 14/15 partial fix originally scored 0.94. Any failing test now caps confidence at 0.5.
- **The model edits code it wasn't asked to touch.** The scope check now flags it and lowers confidence.
- **Retrieval has a blind spot:** KB06 ("try/except hides bugs") is never retrieved, because no failing test mentions exceptions.
- Free-tier API limits (20 requests per day per model) and 503 overloads are real; the agent now fails fast on a daily quota instead of retrying pointlessly.

---

## 💭 Reflection

The biggest lesson was that **the model was the easy part**. Gemini fixed almost every bug I gave it on the first try. The work that made the system trustworthy was everything around the model: running real tests instead of believing it, making it show which documents it relied on, refusing unsafe input, and making it honest about uncertainty. My best design changes all came from the system surprising me: a 0.94 confidence on a broken fix, a passing fix that quietly changed untested code, and, most humbling, an AI fix that passed every test yet crashed on `"inf"`. The rule I added to catch that also caught a crash in my *own* Module 1 code. I only found these because I tested the tester. Module 1 taught me that AI code can look defensive while being wrong. This project taught me how to build guardrails so the next person doesn't have to catch that by hand.

The responsible-AI reflection (limitations, misuse, surprises and how I collaborated with AI) is in [model_card.md](model_card.md).

---

## 📁 Project structure

```
app.py                    Streamlit app: 🎮 Play tab + 🕵️ AI Investigator tab
investigator_ui.py        UI for the AI Investigator tab
investigate.py            CLI entry point
logic_utils.py            The (fixed) game logic from Module 1
glitch_ai/
  agent.py                Plan, act and check loop + confidence scoring + JSONL trace
  retriever.py            TF-IDF retriever
  knowledge_base/         9 bug-pattern documents (KB01–KB09)
  guardrails.py           AST safety, contract and scope checks
  sandbox.py              Runs pytest on candidate code in a temp dir
  llm.py                  Gemini / Claude clients + record and replay
samples/                  Buggy, clean and malicious inputs
recordings/               Recorded model responses for offline replay
tests/                    16 game tests + 33 AI-system tests
eval/                     Evaluation report, results and sample run logs
evaluate.py               Reliability evaluation harness
diagrams/architecture.mmd System diagram (Mermaid source)
docs/                     Original Module 1 write-up
```

🎥 **Video walkthrough (optional):** *add Loom link here*
