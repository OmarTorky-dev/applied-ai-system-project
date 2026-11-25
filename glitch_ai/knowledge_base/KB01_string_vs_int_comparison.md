---
id: KB01
title: Numbers compared as strings (lexicographic comparison)
tags: comparison, type, str, int, hint, check_guess, alphabetical
---
## Symptoms
- A guess that is clearly smaller than the secret is reported as "Too High" (or the reverse).
- Bugs only appear for numbers with a different digit count, e.g. guess 9 vs secret 50.
- Tests such as `test_single_digit_guess_is_compared_numerically` fail.

## Root cause
One side of the comparison is a `str`. Python compares strings character by character,
so `"9" > "50"` is `True` because the character "9" sorts after "5". This often happens
when code calls `str(secret)` or `str(guess)` before comparing, or when a `try/except TypeError`
falls back to comparing `str(guess)` with `str(secret)`.

## Fix
Keep both values as `int` for the entire comparison. Remove any `str(...)` conversion and any
fallback branch that compares string versions of the numbers. If input can arrive as text,
convert it once with `int(...)` in the parsing step, not inside `check_guess`.
