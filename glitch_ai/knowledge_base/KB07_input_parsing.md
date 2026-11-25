---
id: KB07
title: Fragile input parsing (whitespace, empty strings, text, decimals)
tags: parse_guess, input, strip, whitespace, empty, None, ValueError, float
---
## Symptoms
- Entering " 42 " is rejected, or blank input crashes the app.
- Entering "abc" raises an exception instead of showing an error.
- Tests in the `test_parse_guess_*` family fail.

## Root cause
Input is converted with `int(raw)` without first handling `None`, surrounding whitespace,
or non-numeric text.

## Fix
`parse_guess(raw)` returns `(ok, value, error)`:
- `None`, `""` or whitespace-only -> `(False, None, "Enter a guess.")`
- strip whitespace first: `raw = raw.strip()`
- decimals like "7.0" -> `int(float(raw))`
- anything else that fails conversion -> `(False, None, "That is not a number.")`
- success -> `(True, value, None)`
