---
id: KB02
title: Hint messages swapped (Too High says "Go HIGHER")
tags: hint, message, swapped, higher, lower, check_guess, outcome
---
## Symptoms
- The outcome label is correct ("Too High") but the message tells the player to go higher.
- Tests like `test_too_high_message_says_go_lower` or `test_too_low_message_says_go_higher` fail.
- The player can never converge on the secret by following the hints.

## Root cause
The message strings were attached to the wrong branch. When the guess is greater than the secret
the player must guess LOWER; when the guess is smaller they must guess HIGHER.

## Fix
`guess > secret` must return `("Too High", "📉 Go LOWER!")` and `guess < secret` must return
`("Too Low", "📈 Go HIGHER!")`. A correct guess returns `("Win", "🎉 Correct!")`.
Keep the `(outcome, message)` tuple contract: callers and tests unpack both values.
