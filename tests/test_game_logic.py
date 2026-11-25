from logic_utils import check_guess, get_range_for_difficulty, parse_guess, update_score


# --- Starter tests -----------------------------------------------------------
# FIX: The starter tests compared the whole return value to a string, but
# check_guess returns (outcome, message), as its docstring says. I kept the
# function's contract and changed the tests to unpack the outcome.

def test_winning_guess():
    # If the secret is 50 and guess is 50, it should be a win
    outcome, _ = check_guess(50, 50)
    assert outcome == "Win"

def test_guess_too_high():
    # If secret is 50 and guess is 60, hint should be "Too High"
    outcome, _ = check_guess(60, 50)
    assert outcome == "Too High"

def test_guess_too_low():
    # If secret is 50 and guess is 40, hint should be "Too Low"
    outcome, _ = check_guess(40, 50)
    assert outcome == "Too Low"


# --- Bug: hints lied (swapped messages / alphabetical comparison) -------------

def test_too_high_message_says_go_lower():
    outcome, message = check_guess(60, 50)
    assert outcome == "Too High"
    assert "LOWER" in message

def test_too_low_message_says_go_higher():
    outcome, message = check_guess(40, 50)
    assert outcome == "Too Low"
    assert "HIGHER" in message

def test_single_digit_guess_is_compared_numerically():
    # Old bug: str comparison made "9" > "50", so 9 was reported as "Too High".
    outcome, message = check_guess(9, 50)
    assert outcome == "Too Low"
    assert "HIGHER" in message

def test_hint_is_the_same_on_every_attempt():
    # Old bug: the hint for the same guess flipped on even attempts.
    results = {check_guess(60, 50) for _ in range(4)}
    assert results == {("Too High", "📉 Go LOWER!")}


# --- Bug: scoring went haywire ------------------------------------------------

def test_wrong_guess_never_adds_points():
    # Old bug: "Too High" on an even attempt added +5.
    for attempt in range(1, 9):
        assert update_score(50, "Too High", attempt) == 45
        assert update_score(50, "Too Low", attempt) == 45

def test_first_try_win_scores_100():
    assert update_score(0, "Win", 1) == 100

def test_win_score_has_floor_of_10():
    assert update_score(0, "Win", 50) == 10


# --- Bug: difficulty ranges -----------------------------------------------------

def test_hard_range_is_wider_than_normal():
    normal_low, normal_high = get_range_for_difficulty("Normal")
    hard_low, hard_high = get_range_for_difficulty("Hard")
    assert (hard_high - hard_low) > (normal_high - normal_low)


# --- parse_guess edge cases ----------------------------------------------------

def test_parse_guess_valid_int():
    assert parse_guess("42") == (True, 42, None)

def test_parse_guess_strips_whitespace():
    assert parse_guess("  42 ") == (True, 42, None)

def test_parse_guess_empty_and_blank():
    assert parse_guess("")[0] is False
    assert parse_guess("   ")[0] is False
    assert parse_guess(None)[0] is False

def test_parse_guess_rejects_text():
    ok, value, err = parse_guess("abc")
    assert ok is False and value is None
    assert err == "That is not a number."


# --- Robustness invariant (added in the final project) -----------------------
# Found by reviewing an AI-generated fix that passed all 15 tests above but crashed the
# game on "inf". The same check then found that the hand-written version crashed on very
# long decimals. Rule: whatever a player types, parse_guess returns a result, never raises.

def test_parse_guess_never_crashes_on_any_text():
    weird_inputs = ["inf", "-inf", "nan", "1e999", "0x10", "--5", "3.5.1", "½",
                    "9" * 400, "1" + "0" * 400 + ".0"]
    for raw in weird_inputs:
        ok, value, err = parse_guess(raw)
        assert (ok and isinstance(value, int)) or (not ok and err), raw
