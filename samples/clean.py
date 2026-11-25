# FIX: Refactored all game logic out of app.py into this module with Claude Code
# (agent mode). I reviewed each function's diff before accepting it, and the
# fixes are covered by tests/test_game_logic.py.


def get_range_for_difficulty(difficulty: str):
    """Return (low, high) inclusive range for a given difficulty."""
    if difficulty == "Easy":
        return 1, 20
    if difficulty == "Normal":
        return 1, 100
    if difficulty == "Hard":
        # FIX: Hard used 1-50, a *smaller* range than Normal (so it was easier).
        # Claude flagged the mismatch and proposed 1-200 so the difficulty actually goes up.
        return 1, 200
    return 1, 100


def parse_guess(raw: str):
    """
    Parse user input into an int guess.

    Returns: (ok: bool, guess_int: int | None, error_message: str | None)
    """
    if raw is None:
        return False, None, "Enter a guess."

    # FIX: Strip whitespace so " 42 " counts as a guess and "   " counts as empty.
    raw = raw.strip()
    if raw == "":
        return False, None, "Enter a guess."

    try:
        if "." in raw:
            value = int(float(raw))
        else:
            value = int(raw)
    except (ValueError, OverflowError):  # OverflowError: float("1e400") is inf, int(inf) raises
        return False, None, "That is not a number."

    return True, value, None


def check_guess(guess, secret):
    """
    Compare guess to secret and return (outcome, message).

    outcome examples: "Win", "Too High", "Too Low"
    """
    # FIX: Removed the `except TypeError` fallback that compared numbers as strings
    # ("9" > "50") and returned swapped hints. Claude traced the root cause to app.py
    # turning the secret into a str on even attempts. That is fixed in app.py now,
    # so this function only ever compares ints.
    if guess == secret:
        return "Win", "🎉 Correct!"
    if guess > secret:
        return "Too High", "📉 Go LOWER!"
    return "Too Low", "📈 Go HIGHER!"


def update_score(current_score: int, outcome: str, attempt_number: int):
    """Update score based on outcome and attempt number."""
    if outcome == "Win":
        # FIX: Was 100 - 10 * (attempt_number + 1), which docked 20 points even
        # for a first-try win. A first-try win (attempt 1) now earns 100.
        points = 100 - 10 * (attempt_number - 1)
        if points < 10:
            points = 10
        return current_score + points

    # FIX: "Too High" used to *add* 5 points on even attempts. Any wrong guess
    # now costs 5 points, the same for both directions.
    if outcome in ("Too High", "Too Low"):
        return current_score - 5

    return current_score
