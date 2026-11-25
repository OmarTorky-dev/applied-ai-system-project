# AI Interactions Log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

## Agent Workflow (SF8)

> Document your experience using an AI agent (e.g., Cursor Agent, Claude, Copilot) to make multi-step changes autonomously.

**What task did you give the agent?**

I gave Claude Code (Claude Opus 5.5, agent mode in VS Code) the full project instructions and asked it to work through all three phases. It had to stop and check in with me at every 📍 Checkpoint. For Phase 2, the multi-step task was: move `check_guess`, `parse_guess`, `update_score` and `get_range_for_difficulty` into `logic_utils.py`, fix the bugs from my reproduction log, update the import in `app.py`, and write pytest cases for each fix.

**What did the agent do?**

1. Installed `requirements.txt`, launched the app with `python -m streamlit run app.py`, and ran the starter tests (3 failed with `NotImplementedError`).
2. Played two games by driving the real `app.py` with Streamlit's `AppTest` harness, and recorded the bugs plus a reproduction table in `reflection.md`.
3. Checkpoint 1: it asked how to set up git, since my folder was a ZIP download rather than a clone. I gave it my fork URL, and it ran `git init`, connected the fork, and committed the bug log.
4. Added `# FIXME` comments at each bug location and committed them.
5. Rewrote `logic_utils.py` with the fixed logic, updated `app.py` (import, `start_new_game()` helper, int-only secret, banner placeholder), and expanded `tests/test_game_logic.py` to 15 tests.
6. Ran `pytest` (15 passed), then replayed the same two games against the fixed app to confirm the fixes in the UI.
7. Committed and pushed the fixes, then stopped at Checkpoint 2 for my review.

**What did you have to verify or fix manually?**

- **Hard difficulty:** the agent proposed Hard = 1–200 with the existing 5 attempts. I kept the range but decided 5 attempts was way too hard, so I had it raise the limit to 6.
- **Credit in comments:** a code comment first said *I* chose the 1–200 range. The agent corrected it to say Claude proposed it, because I hadn't actually made that call.
- **Harness vs. app error:** the first post-fix replay failed with `ModuleNotFoundError: No module named 'logic_utils'`. The agent checked that this came from its test harness running from a different folder, not from the app (`streamlit run` adds the app folder to the import path), and reran with `PYTHONPATH=.`.
- **Suspicious result:** after switching to Hard, the secret came out as exactly 50 (the value from the previous test). The agent reran the difficulty switch four times to confirm it was a coincidence and not leftover state.
- I reviewed every diff and played the fixed game myself at the checkpoints.

---

## Test Generation (SF7)

> Document how you used AI to help generate or improve tests.

| Edge Case | Prompt Used | AI-Suggested Test | Did It Pass? | Your Reasoning |
|-----------|-------------|-------------------|--------------|----------------|
| Starter tests compare a tuple to a string | "Generate a pytest case in tests/test_game_logic.py that targets the bug you just fixed; confirm it passes with the existing starter tests" | Change the starter tests to `outcome, _ = check_guess(50, 50)` instead of changing `check_guess` to return a string | ✅ Yes | `app.py` needs both the outcome and the message, and the docstring says it returns a tuple. Changing the function just to make the tests pass would have broken the game. |
| Single-digit guess vs. two-digit secret (`9` vs `50`) | Same prompt, targeting the lying-hints bug | `test_single_digit_guess_is_compared_numerically`: `check_guess(9, 50)` must be "Too Low" + "HIGHER" | ✅ Yes | This is exactly the case where alphabetical comparison (`"9" > "50"`) gave the wrong answer. |
| Same guess on different attempts | Same prompt | `test_hint_is_the_same_on_every_attempt`: four calls to `check_guess(60, 50)` give one identical result | ✅ Yes | The bug only showed up on even attempts. The real cause was in `app.py`, so I also replayed the game in the UI. |
| Wrong guess on any attempt number | Same prompt, targeting scoring | `test_wrong_guess_never_adds_points`: attempts 1–8, both "Too High" and "Too Low" subtract 5 | ✅ Yes | The old code added +5 for "Too High" on even attempts, so the test loops over both parities. |
| Blank / whitespace / non-numeric input | "Add edge-case tests for parse_guess" | `test_parse_guess_strips_whitespace`, `test_parse_guess_empty_and_blank`, `test_parse_guess_rejects_text` | ✅ Yes | `"   "` used to give "That is not a number." instead of "Enter a guess.", so stripping whitespace was a small extra fix. |
