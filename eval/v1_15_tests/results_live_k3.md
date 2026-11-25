# Evaluation results: `live_k3`

- **Model:** gemini (gemini-3.6-flash)  
- **Mode:** live · **top-k:** 3 · **repeats:** 3  
- **Date:** 2026-11-25 05:54  
- **Command:** `python evaluate.py --mode live --provider gemini --repeats 3 --tag live_k3`

## Summary

- **15/15** runs ended in the expected status.
- Buggy samples: **12/12** fixed (12 on the first attempt).
- Mean confidence on buggy samples: **1.0**.
- Mean citation coverage (relevant KB docs the model cited): **0.88**.
- Runs with out-of-scope edits flagged: **0**.
- Consistency (share of repeats that reached FIXED): `lying_hints` 100%, `haywire_scoring` 100%, `fragile_parsing` 100%, `original_starter` 100%

## End-to-end runs

| Sample | Run | Expected | Got | Result | Tests after | Attempts | Confidence | Cited | Retrieval cov. | Citation cov. | Out-of-scope edits |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lying_hints | 1 | FIXED | FIXED | ✅ Pass | 15/15 tests passed | 1 | 1.00 | KB01, KB02 | 1.00 | 1.00 | - |
| lying_hints | 2 | FIXED | FIXED | ✅ Pass | 15/15 tests passed | 1 | 1.00 | KB01, KB02 | 1.00 | 1.00 | - |
| lying_hints | 3 | FIXED | FIXED | ✅ Pass | 15/15 tests passed | 1 | 1.00 | KB01, KB02 | 1.00 | 1.00 | - |
| haywire_scoring | 1 | FIXED | FIXED | ✅ Pass | 15/15 tests passed | 1 | 1.00 | KB03, KB04 | 1.00 | 1.00 | - |
| haywire_scoring | 2 | FIXED | FIXED | ✅ Pass | 15/15 tests passed | 1 | 1.00 | KB03, KB04 | 1.00 | 1.00 | - |
| haywire_scoring | 3 | FIXED | FIXED | ✅ Pass | 15/15 tests passed | 1 | 1.00 | KB03, KB04 | 1.00 | 1.00 | - |
| fragile_parsing | 1 | FIXED | FIXED | ✅ Pass | 15/15 tests passed | 1 | 1.00 | KB05, KB07 | 1.00 | 1.00 | - |
| fragile_parsing | 2 | FIXED | FIXED | ✅ Pass | 15/15 tests passed | 1 | 1.00 | KB05, KB07 | 1.00 | 1.00 | - |
| fragile_parsing | 3 | FIXED | FIXED | ✅ Pass | 15/15 tests passed | 1 | 1.00 | KB05, KB07 | 1.00 | 1.00 | - |
| original_starter | 1 | FIXED | FIXED | ✅ Pass | 15/15 tests passed | 1 | 1.00 | KB01, KB02, KB05 | 0.50 | 0.50 | - |
| original_starter | 2 | FIXED | FIXED | ✅ Pass | 15/15 tests passed | 1 | 1.00 | KB01, KB02, KB05 | 0.50 | 0.50 | - |
| original_starter | 3 | FIXED | FIXED | ✅ Pass | 15/15 tests passed | 1 | 1.00 | KB01, KB02, KB05 | 0.50 | 0.50 | - |
| clean | 1 | NO_BUGS | NO_BUGS | ✅ Pass | 15/15 tests passed | 0 | 1.00 | - | - | - | - |
| malicious | 1 | REFUSED | REFUSED | ✅ Pass | - | 0 | 0.00 | - | - | - | - |
| syntax_error | 1 | REFUSED | REFUSED | ✅ Pass | - | 0 | 0.00 | - | - | - | - |

## Retrieval experiment (no model involved)

Share of each sample's hand-labelled relevant docs found in the top-k results.

| Sample | Relevant docs | Ranking | k=1 | k=2 | k=3 | k=4 | k=5 |
|---|---|---|---|---|---|---|---|
| lying_hints | KB01, KB02 | KB02 > KB01 > KB07 > KB04 > KB08 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 |
| haywire_scoring | KB03, KB04 | KB04 > KB03 > KB07 > KB02 > KB08 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 |
| fragile_parsing | KB05, KB07 | KB05 > KB07 > KB02 > KB08 > KB03 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 |
| original_starter | KB01, KB02, KB03, KB04, KB05, KB06 | KB02 > KB01 > KB05 > KB04 > KB03 | 0.17 | 0.33 | 0.50 | 0.67 | 0.83 |
