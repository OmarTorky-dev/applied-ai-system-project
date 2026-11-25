# 💭 Reflection: Game Glitch Investigator

Answer each question in 3 to 5 sentences. Be specific and honest about what actually happened while you worked. This is about your process, not trying to sound perfect.

## 1. What was broken when you started?

The first time I ran `python -m streamlit run app.py`, the game loaded without any crash: a title, a sidebar with a difficulty picker, a text box, "Submit Guess" and "New Game" buttons, and a "Developer Debug Info" expander that shows the secret number. Everything *looked* fine, but once I started guessing with the debug panel open, the hints, the attempt counter and the New Game button were all misbehaving. I played two games (Normal with secret 50, and Hard with secret 30) and wrote down what I expected versus what actually happened.

**Bugs I noticed (expected vs. actual):**

1. **The hints lie on every other guess.** With the secret at 50, I expected a guess of 60 to say "Go LOWER!", but it said "📈 Go HIGHER!". A guess of 40 on the next turn gave the correct hint, so the bug only shows up on even-numbered attempts. On those turns the app turns the secret into a string, so the numbers get compared alphabetically (`"9" > "50"`) and the hint messages are swapped. *Note:* in the original starter code the messages were backwards on **every** guess ("Too High" → "Go HIGHER!"). I had already flipped the messages in the main branch of `check_guess` before logging this, which is why my playthrough only showed the bad hint on even attempts. The string-comparison fallback still had them backwards.
2. **New Game doesn't start a new game.** After losing, I expected "New Game" to let me play again. Instead the app kept showing "Game over. Start a new game to try again." and ignored every guess, because `status` is never reset to `"playing"`. New Game also sets attempts to 0 instead of 1, always picks the secret from 1–100 regardless of difficulty, and doesn't clear the history.
3. **You get fewer attempts than promised.** On Normal the sidebar says 8 attempts allowed, but the game ended with "Out of attempts!" after my 7th submission. `attempts` starts at 1 instead of 0. The "Attempts left" banner also shows the count from *before* your last guess (it still said 7 after my first guess).
4. **Difficulty and range don't line up.** Hard uses 1–50, which is *easier* than Normal's 1–100, and the main banner always says "Guess a number between 1 and 100" even on Easy or Hard.
5. **Score goes haywire.** A wrong "Too High" guess *adds* +5 points on even attempts and subtracts 5 on odd attempts, so the score bounced between 0 and 5 while I was guessing wrong.

**Bug Reproduction Log**

| Input | Expected Behavior | Actual Behavior | Console Output / Error |
|-------|-------------------|-----------------|------------------------|
| Normal, secret = 50, 1st guess `60` (attempt #2 internally) | "Too High" → "📉 Go LOWER!" | "📈 Go HIGHER!" shown; score went **up** from 0 to 5 | none |
| Normal, secret = 50, guess `9` on an even attempt | "Too Low" → "Go HIGHER!" | Outcome recorded as "Too High" (string compare `"9" > "50"`); score +5 | none |
| Normal, secret = 50, guesses `60, 40, 9, 70, abc, 45, 55` | 8 attempts allowed, game still running after 7 guesses | "Out of attempts! The secret was 50. Score: 0" after the 7th guess | none |
| After losing, click **New Game 🔁**, then guess `10` | Fresh game: status reset, history cleared, guesses accepted | Still shows "Game over. Start a new game to try again."; guess ignored; history still holds old guesses | none |
| Select **Hard** in sidebar | Larger range than Normal; banner shows the Hard range | Sidebar says "Range: 1 to 50" (smaller than Normal's 1–100); banner still says "between 1 and 100" | none |
| Fresh Normal game, first guess submitted | "Attempts left" drops from 8 to 7 | Starts at 7 before any guess, still shows 7 after the first guess | none |

None of these bugs crash the app or print anything in the terminal. They are all silent logic bugs, which is why they're easy to miss. Separately, running `pytest` at the start failed all 3 tests with `NotImplementedError: Refactor this function from app.py into logic_utils.py`, because `logic_utils.py` is still a stub.

---

## 2. How did you use AI as a teammate?

**Tools:** I used Claude Code (Claude Opus 5.5) inside VS Code in agent mode. It read `app.py` and `logic_utils.py` together, ran the game, made multi-file edits and ran `pytest`, and I reviewed each diff and checked in at every checkpoint.

**✅ A correct AI suggestion: the real cause of the lying hints was in `app.py`, not `check_guess`.**
My first instinct was that `check_guess` just had its messages backwards. Claude traced it further. On every even attempt, `app.py` does `secret = str(st.session_state.secret)`, which makes `guess > secret` raise a `TypeError`. The `except TypeError` branch then compares strings alphabetically (`"9" > "50"` is True) and has its messages swapped. It suggested deleting the str conversion in `app.py` *and* the whole fallback branch, instead of patching the messages. I verified this by replaying the exact same game (secret 50; guesses 60, 40, 9, 70, 45, 55…) before and after. Before, 60 got "Go HIGHER!" on attempt 2. After, every guess got the right hint, and `test_single_digit_guess_is_compared_numerically` and `test_hint_is_the_same_on_every_attempt` pass.

**⚠️ A misleading AI suggestion: the `try/except TypeError` "safety net" in the original code.**
The AI-generated starter code looked defensive, as if it catches a type error and keeps going. In reality it hid the bug: instead of crashing loudly when an int was compared to a str, it silently gave wrong answers using alphabetical order. A crash would have pointed straight at the problem, while this "fallback" made the game look like it worked. I verified it by reading the branch line by line and seeing that `"9" > "50"` is `True` in Python. Lesson: a `try/except` that swallows an error is not automatically a fix.

**❌ A suggestion I did not accept as written: making `check_guess` return just a string so the starter tests pass.**
After the refactor, the 3 starter tests still failed. They do `assert check_guess(50, 50) == "Win"`, but `check_guess` returns a tuple, `("Win", "🎉 Correct!")`. The quickest way to turn the tests green was to change `check_guess` to return only the outcome string. I rejected that, because `app.py` needs both the outcome *and* the hint message, and the function's own docstring in `logic_utils.py` says it returns `(outcome, message)`. Changing the function to satisfy the tests would have made the tests pass and broken the game. Instead I kept the function's contract and changed the tests to unpack it: `outcome, _ = check_guess(50, 50)`. I verified this by running `pytest` (all tests pass) and replaying the game to confirm the hint messages still show up.

---

## 3. Debugging and testing your fixes

I only counted a bug as fixed when it passed two checks: an automated `pytest` test targeting that bug, **and** a replay of the exact input from my Bug Reproduction Log in the running app. The second check mattered. The hint bug lived in `app.py` (turning the secret into a string), which unit tests on `check_guess` alone can't see. So I also replayed the full game with Streamlit's `AppTest` harness, which runs the real `app.py`, enters guesses and clicks buttons. The replay confirmed that 60 now says "Go LOWER!" on every attempt, typing `abc` no longer uses up an attempt, Normal allows all 8 guesses, and clicking New Game after losing actually starts a playable game.

The pytest suite grew from 3 starter tests to 15. For example, `test_wrong_guess_never_adds_points` checks every attempt number from 1 to 8 and showed that a "Too High" guess now always costs 5 points instead of sometimes adding 5. `test_hard_range_is_wider_than_normal` encodes the rule that Hard should really be harder.

AI helped design the tests. Claude proposed one test per bug in my reproduction log, plus parse_guess edge cases (blank input, whitespace, text). It also pointed out that the starter tests were comparing a tuple to a string (see section 2). Final result: `15 passed in 0.09s`.

---

## 4. What did you learn about Streamlit and state?

A Streamlit app is a Python script that runs **from top to bottom every time you interact with it**. Clicking a button, typing in a box, or changing the sidebar all trigger a "rerun" of the whole file. That means a normal variable like `secret = random.randint(1, 100)` would get a brand-new value on every click. `st.session_state` is a dictionary that survives reruns, like the app's memory for your browser tab. That's why the game only picks a secret `if "secret" not in st.session_state`. The rerun model also caused one of our bugs: the "Attempts left" banner was drawn near the top of the script, *before* the code further down processed the new guess, so it always showed the old number. The fix was to reserve a spot with `st.empty()` and fill it in at the end of the script, once the state was up to date.

---

## 5. Looking ahead: your developer habits

**A habit I want to keep:** reproduce a bug with an exact input *before* fixing it, then rerun that same input afterward. Writing the Bug Reproduction Log first gave me a checklist, and replaying the same game (secret 50; guesses 60, 40, 9…) before and after was the clearest proof the fixes worked. I also liked splitting the work into small commits (log the bugs → mark the FIXMEs → apply the fixes → write the docs), so the history tells the story.

**Something I'd do differently:** I'd ask the AI to explain the root cause before asking for a fix. My first instinct about the hint bug was "the messages are backwards", and I had already flipped them by hand before this session. That was only half the problem, because the real cause was the secret becoming a string in `app.py`. I'd also play-test the AI's choices sooner. The AI's proposal of Hard = 1–200 with 5 attempts looked reasonable on paper, but it was way too hard in practice, so I bumped it to 6 attempts.

**How this changed my view of AI-generated code:** AI code can look clean and even "defensive" (like that `try/except TypeError`) while being quietly wrong. Now I treat it as a first draft that I have to run, test and question, and I only trust it once tests and a real playthrough agree.
