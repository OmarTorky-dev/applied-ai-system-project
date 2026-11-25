---
id: KB05
title: Difficulty settings that do not match their names
tags: difficulty, range, easy, normal, hard, get_range_for_difficulty
---
## Symptoms
- "Hard" is easier than "Normal" because its number range is smaller.
- `test_hard_range_is_wider_than_normal` fails.
- The UI banner shows a different range than the game actually uses.

## Root cause
Hard-coded ranges were edited inconsistently. A harder level must have a wider range
(more possible secrets) or fewer attempts, never a narrower range.

## Fix
Use Easy = (1, 20), Normal = (1, 100), Hard = (1, 200). Unknown difficulty falls back to
Normal's (1, 100). Always read the range from `get_range_for_difficulty` instead of repeating it.
