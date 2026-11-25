---
id: KB08
title: Broken function contracts (wrong return shape)
tags: contract, return, tuple, signature, docstring, unpack, NotImplementedError
---
## Symptoms
- Tests fail with `TypeError: cannot unpack non-iterable` or `ValueError: too many values to unpack`.
- A function raises `NotImplementedError` because it is still a stub.

## Root cause
A function returns a different shape than its docstring and callers expect, or was never implemented.

## Fix
Keep the documented contract: `check_guess -> (outcome, message)`,
`parse_guess -> (ok, value, error)`, `get_range_for_difficulty -> (low, high)`,
`update_score -> int`. Do not change a contract just to make one test pass; fix the code so that
every caller still works.
