---
id: KB09
title: Streamlit reruns reset variables (session_state)
tags: streamlit, session_state, rerun, reset, secret, button, state
---
## Symptoms
- The secret number changes every time a button is clicked.
- A "New Game" button leaves old status, score or history behind.

## Root cause
Streamlit re-executes the whole script on every interaction. Plain variables are recreated;
only `st.session_state` survives. Partial resets leave stale state.

## Fix
Store the secret, attempts, score, status and history in `st.session_state`, initialise them once,
and reset all of them together in a single `start_new_game()` helper. Keep pure game logic in
`logic_utils.py` so it can be tested without Streamlit.
