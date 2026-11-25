---
id: KB06
title: try/except blocks that hide bugs instead of fixing them
tags: try, except, TypeError, ValueError, fallback, swallow, silent
---
## Symptoms
- No crash and no error in the console, but results are silently wrong.
- A function contains `except TypeError:` or a bare `except:` with an alternative computation.

## Root cause
A "safety net" catches an error caused by a real bug (usually a type mismatch) and continues
with a different, incorrect computation. The bug becomes invisible.

## Fix
Delete the fallback branch and fix the root cause (for example keep values as `int`, KB01).
Only catch exceptions you expect from user input (e.g. `ValueError` from `int("abc")`)
and turn them into a clear error message, never into a guessed answer.
