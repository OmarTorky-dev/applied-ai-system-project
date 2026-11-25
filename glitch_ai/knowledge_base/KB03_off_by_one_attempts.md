---
id: KB03
title: Off-by-one errors in counters and score formulas
tags: off-by-one, attempts, counter, attempt_number, formula, first try
---
## Symptoms
- The player gets one fewer attempt than promised, or a banner is always one step behind.
- A first-try win does not score the maximum.
- Tests like `test_first_try_win_scores_100` fail with a value 10 or 20 points too low.

## Root cause
Counters start at 1 instead of 0, or a formula uses `attempt_number + 1` where it should use
`attempt_number - 1`. Attempt numbers in this game are 1-based: the first guess is attempt 1.

## Fix
For the win bonus use `points = 100 - 10 * (attempt_number - 1)` so attempt 1 earns 100,
then clamp with a floor: `if points < 10: points = 10`. Start attempt counters at 0 and increment
before using them.
