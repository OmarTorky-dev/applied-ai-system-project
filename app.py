import random
import streamlit as st

# FIX: Game logic now lives in logic_utils.py (refactored with Claude Code agent
# mode) so it can be unit-tested without running Streamlit.
from logic_utils import check_guess, get_range_for_difficulty, parse_guess, update_score

# NEW (final project): the AI agent that diagnoses and fixes broken versions of logic_utils.py.
from investigator_ui import render_investigator


def start_new_game(low: int, high: int):
    """Reset every piece of per-game state."""
    # FIX: New Game used to reset only attempts and secret. It left status as
    # "won"/"lost" (the game stayed locked), set attempts to 0 while startup used 1,
    # ignored the difficulty range, and kept the old score and history. Claude
    # suggested one reset helper shared by startup, New Game and difficulty changes.
    st.session_state.secret = random.randint(low, high)
    st.session_state.attempts = 0
    st.session_state.score = 0
    st.session_state.status = "playing"
    st.session_state.history = []


st.set_page_config(page_title="Glitchy Guesser", page_icon="🎮")

st.title("🎮 Game Glitch Investigator")
st.caption("A number-guessing game, plus an AI agent that finds and fixes its glitches.")

st.sidebar.header("Settings")

difficulty = st.sidebar.selectbox(
    "Difficulty",
    ["Easy", "Normal", "Hard"],
    index=1,
)

attempt_limit_map = {
    "Easy": 6,
    "Normal": 8,
    # FIX: Raised from 5 to 6 after play-testing: with the wider 1-200 range,
    # 5 attempts felt way too hard. My call; Claude made the edit.
    "Hard": 6,
}
attempt_limit = attempt_limit_map[difficulty]

low, high = get_range_for_difficulty(difficulty)

st.sidebar.caption(f"Range: {low} to {high}")
st.sidebar.caption(f"Attempts allowed: {attempt_limit}")

# FIX: Start a fresh game on first load AND whenever the difficulty changes, so the
# secret always comes from the range shown in the sidebar.
if st.session_state.get("difficulty") != difficulty:
    st.session_state.difficulty = difficulty
    start_new_game(low, high)

tab_play, tab_ai = st.tabs(["🎮 Play", "🕵️ AI Investigator"])

with tab_play:
    st.subheader("Make a guess")

    # FIX: The banner used to render *before* the guess was processed, so "Attempts left"
    # was always one guess behind, and it hard-coded "1 and 100". A placeholder is
    # filled in at the end of the script with the up-to-date count and the real range.
    status_banner = st.empty()

    debug_panel = st.expander("Developer Debug Info")

    raw_guess = st.text_input(
        "Enter your guess:",
        key=f"guess_input_{difficulty}"
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        submit = st.button("Submit Guess 🚀")
    with col2:
        new_game = st.button("New Game 🔁")
    with col3:
        show_hint = st.checkbox("Show hint", value=True)

    if new_game:
        start_new_game(low, high)
        st.success("New game started.")

    if st.session_state.status != "playing":
        if st.session_state.status == "won":
            st.success("You already won. Start a new game to play again.")
        else:
            st.error("Game over. Start a new game to try again.")
    elif submit:
        ok, guess_int, err = parse_guess(raw_guess)

        if not ok:
            # FIX: Invalid input no longer uses up an attempt or goes into the history.
            st.error(err)
        else:
            st.session_state.attempts += 1
            st.session_state.history.append(guess_int)

            # FIX: The secret used to become a str on every even attempt, which forced
            # check_guess into alphabetical comparison. It now always stays an int.
            outcome, message = check_guess(guess_int, st.session_state.secret)

            if show_hint:
                st.warning(message)

            st.session_state.score = update_score(
                current_score=st.session_state.score,
                outcome=outcome,
                attempt_number=st.session_state.attempts,
            )

            if outcome == "Win":
                st.balloons()
                st.session_state.status = "won"
                st.success(
                    f"You won! The secret was {st.session_state.secret}. "
                    f"Final score: {st.session_state.score}"
                )
            elif st.session_state.attempts >= attempt_limit:
                st.session_state.status = "lost"
                st.error(
                    f"Out of attempts! "
                    f"The secret was {st.session_state.secret}. "
                    f"Score: {st.session_state.score}"
                )

    status_banner.info(
        f"Guess a number between {low} and {high}. "
        f"Attempts left: {attempt_limit - st.session_state.attempts}"
    )

    with debug_panel:
        st.write("Secret:", st.session_state.secret)
        st.write("Attempts:", st.session_state.attempts)
        st.write("Score:", st.session_state.score)
        st.write("Difficulty:", difficulty)
        st.write("History:", st.session_state.history)

with tab_ai:
    render_investigator()

st.divider()
st.caption("Built by an AI that claims this code is production-ready.")
