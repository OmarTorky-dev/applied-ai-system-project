# Sample glitch: the hint bug from the original starter code.
# Numbers are compared as strings and the hint messages are swapped.


def get_range_for_difficulty(difficulty: str):
    if difficulty == "Easy":
        return 1, 20
    if difficulty == "Normal":
        return 1, 100
    if difficulty == "Hard":
        return 1, 200
    return 1, 100


def parse_guess(raw: str):
    if raw is None:
        return False, None, "Enter a guess."
    raw = raw.strip()
    if raw == "":
        return False, None, "Enter a guess."
    try:
        value = int(float(raw)) if "." in raw else int(raw)
    except ValueError:
        return False, None, "That is not a number."
    return True, value, None


def check_guess(guess, secret):
    if guess == secret:
        return "Win", "🎉 Correct!"
    g, s = str(guess), str(secret)
    if g > s:
        return "Too High", "📈 Go HIGHER!"
    return "Too Low", "📉 Go LOWER!"


def update_score(current_score: int, outcome: str, attempt_number: int):
    if outcome == "Win":
        points = 100 - 10 * (attempt_number - 1)
        if points < 10:
            points = 10
        return current_score + points
    if outcome in ("Too High", "Too Low"):
        return current_score - 5
    return current_score
