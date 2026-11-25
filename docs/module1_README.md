# 🎮 Game Glitch Investigator: The Impossible Guesser

## 🚨 The Situation

You asked an AI to build a simple "Number Guessing Game" using Streamlit.
It wrote the code, ran away, and now the game is unplayable. 

- You can't win.
- The hints lie to you.
- The secret number seems to have commitment issues.

## 🛠️ Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Run the broken app: `python -m streamlit run app.py`

## 🕵️‍♂️ Your Mission

1. **Play the game.** Open the "Developer Debug Info" tab in the app to see the secret number. Try to win.
2. **Find the State Bug.** Why does the secret number change every time you click "Submit"? Ask ChatGPT: *"How do I keep a variable from resetting in Streamlit when I click a button?"*
3. **Fix the Logic.** The hints ("Higher/Lower") are wrong. Fix them.
4. **Refactor & Test.** - Move the logic into `logic_utils.py`.
   - Run `pytest` in your terminal.
   - Keep fixing until all tests pass!

## 📝 Document Your Experience

- [x] **Describe the game's purpose.**
  A Streamlit number-guessing game. The app picks a secret number in a range set by the difficulty (Easy 1–20, Normal 1–100, Hard 1–200). You get a limited number of attempts (6 / 8 / 6). After each guess it tells you to go higher or lower, and your score goes down with each wrong guess. Winning sooner earns more points.

- [x] **Detail which bugs you found.**
  - **Lying hints:** on every even attempt the secret was turned into a string, so guesses were compared alphabetically (`"9" > "50"`), and the fallback branch had "Go HIGHER"/"Go LOWER" swapped. In the original code the messages were backwards on every guess.
  - **New Game didn't work:** it never reset `status`, so after a win or loss the game stayed locked on "Game over". It also ignored the difficulty range and kept the old history.
  - **Off-by-one attempts:** `attempts` started at 1, so you got one fewer guess than promised, and the "Attempts left" banner was always one guess behind.
  - **Difficulty mismatch:** Hard (1–50) was easier than Normal (1–100), and the banner always said "between 1 and 100".
  - **Haywire scoring:** a "Too High" guess *added* 5 points on even attempts, and a first-try win only scored 80.
  - **Broken tests:** `logic_utils.py` was a stub, and the starter tests compared a `(outcome, message)` tuple to a plain string.
  - Full details: [module1_reflection.md](module1_reflection.md) (Bug Reproduction Log).

- [x] **Explain what fixes you applied.**
  - Moved `get_range_for_difficulty`, `parse_guess`, `check_guess` and `update_score` from `app.py` into `logic_utils.py`, so they can be tested without Streamlit.
  - Kept the secret as an `int` and deleted the `try/except TypeError` string-comparison fallback, so hints are always numeric and correct.
  - Added a `start_new_game()` helper that resets secret, attempts, score, status and history from the current difficulty's range. It runs on first load, on New Game, and when the difficulty changes.
  - Attempts start at 0, invalid input no longer costs an attempt, and the banner is drawn *after* the guess is processed, so it shows the real range and an accurate attempts-left count.
  - Every wrong guess costs 5 points, and a first-try win scores 100 (minimum 10).
  - Hard is now 1–200 with 6 attempts.
  - Fixed the starter tests to unpack the tuple and added 12 new tests (15 total, all passing).

## 📸 Demo Walkthrough

A sample game on the fixed app (Normal difficulty; the secret is **63**, visible in "Developer Debug Info"):

1. Open the app with `python -m streamlit run app.py`. The sidebar shows **Range: 1 to 100** and **Attempts allowed: 8**, and the banner says *"Guess a number between 1 and 100. Attempts left: 8"*.
2. Enter a guess of **40** and click **Submit Guess 🚀** → hint **"📈 Go HIGHER!"**. Score: **-5**, attempts left: **7**.
3. Enter **70** → **"📉 Go LOWER!"**. Score: **-10**, attempts left: **6**.
4. Enter **abc** → error **"That is not a number."** Attempts left stays at **6** and the score stays at **-10**, because invalid input doesn't count as a guess.
5. Enter **60** → **"📈 Go HIGHER!"**. Score: **-15**, attempts left: **5**.
6. Enter **63** → **"🎉 Correct!"**, balloons, and *"You won! The secret was 63. Final score: 55"* (-15 from wrong guesses + 70 for winning on attempt 4).
7. Try to guess **10** after winning → *"You already won. Start a new game to play again."* The game is over, so the guess is ignored.
8. Click **New Game 🔁** → *"New game started."* Attempts left resets to **8**, score to **0**, and the history is cleared, with a new secret from 1–100.
9. Switch the sidebar to **Hard** → the sidebar shows **Range: 1 to 200**, **Attempts allowed: 6**, and a fresh game starts with a secret from 1–200.

**Screenshot** *(optional)*: <!-- Insert a screenshot of your fixed, winning game here -->

## 🧪 Test Results

```
$ pytest -v
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0
collected 15 items

tests/test_game_logic.py::test_winning_guess PASSED                      [  6%]
tests/test_game_logic.py::test_guess_too_high PASSED                     [ 13%]
tests/test_game_logic.py::test_guess_too_low PASSED                      [ 20%]
tests/test_game_logic.py::test_too_high_message_says_go_lower PASSED     [ 26%]
tests/test_game_logic.py::test_too_low_message_says_go_higher PASSED     [ 33%]
tests/test_game_logic.py::test_single_digit_guess_is_compared_numerically PASSED [ 40%]
tests/test_game_logic.py::test_hint_is_the_same_on_every_attempt PASSED  [ 46%]
tests/test_game_logic.py::test_wrong_guess_never_adds_points PASSED      [ 53%]
tests/test_game_logic.py::test_first_try_win_scores_100 PASSED           [ 60%]
tests/test_game_logic.py::test_win_score_has_floor_of_10 PASSED          [ 66%]
tests/test_game_logic.py::test_hard_range_is_wider_than_normal PASSED    [ 73%]
tests/test_game_logic.py::test_parse_guess_valid_int PASSED              [ 80%]
tests/test_game_logic.py::test_parse_guess_strips_whitespace PASSED      [ 86%]
tests/test_game_logic.py::test_parse_guess_empty_and_blank PASSED        [ 93%]
tests/test_game_logic.py::test_parse_guess_rejects_text PASSED           [100%]

============================= 15 passed in 0.08s ==============================
```

The full output is also saved in [module1_test_results.txt](module1_test_results.txt).

## 🚀 Stretch Features

- [ ] [If you choose to complete Challenge 4, describe the Enhanced UI changes here — a screenshot is optional]
