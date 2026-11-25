# Presentation: Glitch Investigator AI

**Length:** about 7 minutes · 15 slides · 1 live demo (with an offline backup)
**Slides:** [Glitch Investigator AI deck](https://claude.ai/artifact/WvaSTxncweqmWZw8i6suPo). It's private until shared from the deck's Share menu, and it exports to PowerPoint or PDF. The speaker notes in the deck match the script below.

---

## Outline

| # | Slide | Section | Time | Key point |
|---|---|---|---|---|
| 1 | Cover | Problem | 0:00 | An AI agent that proves its fixes before you trust them |
| 2 | Where it started | Problem | 0:20 | Module 1: AI-written game with silent bugs, fixed by hand |
| 3 | The question | Problem | 0:50 | Can an AI fix AI code, and can you trust the fix? |
| 4 | How it works | System | 1:05 | 7 steps: guard, test, retrieve, propose, validate, verify, report, plus the human gate |
| 5 | Retrieval | System | 1:45 | The failing tests are the search query |
| 6 | Demo | System | 2:15 | **Live:** `python investigate.py samples/lying_hints.py` |
| 7 | Guardrails | System | 3:00 | Refuse first, never fake a fix |
| 8 | Confidence | System | 3:30 | 60% tests, 20% grounding, 20% model; capped at 0.5 |
| 9 | Results | Evidence | 4:00 | 49/49 tests, 36/37 live runs, 100% refusals |
| 10 | Key finding | Evidence | 4:25 | Passing tests ≠ correct (`"inf"` crash) |
| 11 | The payoff | Evidence | 5:05 | The agent caught the same mistake itself, live |
| 12 | Limitations | Reflection | 5:35 | Only as good as the tests; biased KB; blocklist; small eval |
| 13 | AI collaboration | Reflection | 5:55 | Accepted: scope check · Changed: Claude-only → provider-agnostic |
| 14 | What I learned | Reflection | 6:20 | The model was the easy part |
| 15 | Close | Reflection | 6:40 | What this says about me as an AI engineer |

To get closer to 5 minutes, skip slide 3 (say the question on slide 2) and slide 14 (fold it into slide 15).

---

## Demo plan

**Before presenting**
1. Open a terminal in the project folder and activate the venv: `.venv\Scripts\activate`.
2. Run `python -m pytest -q` once to warm the cache. It should print `49 passed`.
3. Check whether you have Gemini quota (free tier: about 20 requests per day per model). If unsure, demo in replay mode. It's the same output and can't fail.
4. Make the terminal font large (≥ 20 pt).

**During the demo (slide 6, ~45 s)**
```bash
python investigate.py samples/lying_hints.py --no-diff      # live if .env has a key
python investigate.py samples/lying_hints.py --mode replay  # guaranteed backup
python investigate.py samples/malicious.py                  # optional: instant REFUSED
```
Point at: `Baseline: 12/16` → `RETRIEVE KB02, KB01` → `cites ['KB01', 'KB02']` → `16/16` → `FIXED`.

**If anything goes wrong:** stay on slide 6. It shows the same run, so just walk through it.

---

## Full script

**1 · Cover (0:00)**
Hi, I’m Omar. My final project is Glitch Investigator AI: an AI agent that finds and fixes logic bugs, but only reports success when it can prove the fix with real tests. The theme of this talk is trust: how do you build an AI tool you can actually trust?

**2 · Where it started (0:20)**
This started as my Module 1 project. An AI generated a number-guessing game that looked fine but was quietly broken: the hints lied because numbers were compared as strings, so 9 counted as bigger than 50. Scoring added points for wrong guesses. Hard mode was easier than Normal. I debugged it by hand, and I noticed I was following the same loop every time: reproduce, recognise the pattern, fix the root cause, re-test.

**3 · The question (0:50)**
So the final project asks: could an AI agent do that loop for me? And the harder question: could I trust what it tells me? Because the whole lesson of Module 1 was that AI code can look clean and confident while being wrong.

**4 · How it works (1:05)**
Here’s the agent. Step one, guardrails: it parses the code without running it, and refuses anything dangerous. Step two, it runs my real test suite to see what’s actually broken. Step three, retrieval: it searches a knowledge base of nine bug patterns I wrote from my Module 1 bug log. Step four, the model, Gemini, proposes a diagnosis and a fix and must cite which documents it used. Step five checks that fix with the same guardrails. Step six re-runs the tests; if anything still fails, the new failures go back into retrieval and it tries again, up to three times. And finally a report, and a human decides. The AI never applies anything itself.

**5 · Retrieval (1:45)**
The retrieval part matters because it grounds the model. My first version searched with the code, and the parsing document came back for every single input, because the code mentions everything. So I switched the query to the evidence: the failing test names and assertions. For the lying-hints bug, the top two results are exactly the two real causes, and the model cited exactly those two.

**6 · Demo (2:15)**
*[Run the command.]* Guardrails pass. The tests show 12 of 16 passing. Retrieval finds the two right patterns. The model proposes a fix citing them, the fix passes the guardrails and the scope check, and the tests go to 16 of 16. Look at the diff: it removes the string comparison instead of patching the messages. That’s the root cause, the same one I found by hand in Module 1.

**7 · Guardrails (3:00)**
Reliability is also about what the system refuses to do. Malicious code is rejected before anything executes, and the model never sees it. If the tests already pass, it doesn’t call the model at all. And when Google’s API was overloaded during my evaluation, the agent reported an error instead of pretending. The same guardrails also check the AI’s own output.

**8 · Confidence (3:30)**
How sure is it? I don’t let the model grade itself. Sixty percent of the score is test evidence, twenty is grounding, meaning it cited real retrieved documents, and only twenty is the model’s own rating, because Gemini said “1.00” on every run, including one that was wrong. Two safety rules: edits outside what the tests cover cost points, and any failing test caps the score at 0.5. That cap exists because my unit tests caught my first formula giving a broken fix 0.94.

**9 · Results (4:00)**
I evaluated it with a harness that runs every sample, repeats live runs for consistency, and measures retrieval against hand-labelled answers. 49 of 49 unit tests pass. 36 of 37 live runs ended exactly as expected; the one miss was Google’s API being overloaded, which the agent reported honestly. Every malicious input was refused. Retrieval is great for single bugs but misses some patterns when a file has four kinds of bugs at once.

**10 · Key finding (4:25)**
Here’s the most important thing I learned. While reviewing the AI’s fixes by hand, I found one that passed all 15 tests but crashed on the input “inf”. The tests just never tried it. I didn’t special-case “inf”. I added a general rule: whatever a player types, parsing must never crash. And the humbling part: that rule also found a crash in my own hand-written code from Module 1. The tester needed testing.

**11 · The payoff (5:05)**
And this is the payoff. In a live evaluation run, the model made that exact same mistake again. Notice it rated itself 1.00 confident. But this time the new test caught it, the agent fed that failure back in, retrieval pulled different documents, and the second attempt passed. Under the old tests, that broken fix would have been reported as done with full confidence. I didn’t script this; the loop just did its job.

**12 · Limitations (5:35)**
It has real limits. “Fixed” only means the tests pass, and there’s still an untested behaviour change in one fix. The knowledge base is biased toward the bugs I happened to find, and one pattern is never retrieved because no test mentions exceptions. The guardrails are a blocklist, not a real sandbox. And my evaluation set is small. These are all written up in the model card.

**13 · AI collaboration (5:55)**
I built this with Claude Code as a pair programmer, checking in after every step. One suggestion I accepted: the scope check. When Gemini rewrote a function nobody asked it to touch, Claude suggested flagging that, and it now catches edits the tests can’t see. One I changed: the original design only supported Claude, but my key was for Gemini, so instead of switching wholesale we made the system provider-agnostic. That ended up mattering when I ran out of quota on one model mid-evaluation.

**14 · What I learned (6:20)**
The biggest lesson: the model was the easy part. Gemini fixed almost everything on the first try. What made the system trustworthy was everything around it: evidence over confidence, testing my own tests, and designing honest behaviour for when things go wrong.

**15 · Close (6:40)**
So, what does this say about me as an AI engineer? I don’t trust a model because it sounds sure. I build the tests, guardrails and evidence that make it earn that trust, and then I test those too. The code, the evaluation and the model card are all on GitHub. Thank you, happy to take questions.

---

## Likely questions

| Question | Short answer |
|---|---|
| Why TF-IDF and not embeddings? | Nine short docs. TF-IDF is deterministic, explainable (scores show in the trace) and unit-testable. Embeddings would be the next step at a larger scale. |
| Couldn’t the model just game the tests? | The prompt forbids it, the scope check flags edits outside the failing functions, and a human reads every diff. A clever special-case inside an implicated function could still slip through. That’s a stated limitation. |
| Why not let the model apply the fix? | The tests can be incomplete, as the `"inf"` bug proved. A human gate is cheap insurance. |
| How do you know the results aren’t cherry-picked? | Every run is logged; `eval/` has the raw JSON and console output, including the failures. Replay mode reproduces the recorded runs exactly. |
| Why Gemini? | That’s the key I had. The system is provider-agnostic; Claude works with an Anthropic key. |
| What would you do next? | Adaptive top-k retrieval, embeddings, property-based tests (Hypothesis) instead of hand-picked edge cases, and a container sandbox. |

---

## Loom walkthrough script (optional, ~3 minutes)

The rubric grades the README evidence, not the video. If you record one, it doesn’t need setup or installation.

1. **(0:00)** “This is Glitch Investigator AI, an agent that fixes bugs and proves it.” Show the README top section.
2. **(0:20)** `python -m streamlit run app.py` → the 🎮 Play tab: play two guesses to show the game.
3. **(0:45)** 🕵️ AI Investigator tab → pick `lying_hints`, mode **replay** → Investigate. Walk through the status, confidence, before and after test counts, and the agent trace.
4. **(1:30)** Expand the diagnosis and diff. Point out the cited docs and the “human review required” note.
5. **(1:50)** Pick `malicious` → Investigate → REFUSED instantly.
6. **(2:05)** Terminal: `python evaluate.py` → 7/7, then open `eval/README.md` §2 to show the `"inf"` finding and the self-correction trace.
7. **(2:40)** Close on `model_card.md` limitations: “It’s only as good as its tests, and I can show you exactly where it falls short.”
