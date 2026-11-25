---
id: KB04
title: Scoring sign errors (wrong guesses add points)
tags: score, update_score, sign, penalty, even, parity, points
---
## Symptoms
- The score goes up after a wrong guess.
- Behaviour differs between even and odd attempts.
- `test_wrong_guess_never_adds_points` fails.

## Root cause
A branch adds instead of subtracts, or a condition such as `attempt_number % 2 == 0` gives a
different penalty depending on parity. Penalties must not depend on the attempt number.

## Fix
Any wrong guess ("Too High" or "Too Low") costs exactly 5 points: `return current_score - 5`.
Remove parity checks. Unknown outcomes return the score unchanged.
Wins: see KB03 for the bonus formula and the 10-point floor.
