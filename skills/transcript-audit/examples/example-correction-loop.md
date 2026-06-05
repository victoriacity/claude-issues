# Case: User corrected same architectural issue three times, agent kept regressing

| Field | Value |
|-------|-------|
| Session | `683b95e9` |
| Date | 2026-04-12 11:15 UTC |
| Model | claude-sonnet-4-6 |
| Context usage | 89200 in / 28400 out / 72000 cache-read / 17300 cache-create |
| Category | repeated-failure |
| Severity | high |
| Git branch | main |

## What happened

The user established that integration tests must reproduce exactly what users experience — no divergence between test and production behavior is acceptable. The agent implemented layered fixes for a failing feature, fixing individual problems incrementally (wrong content, missing bootstrap, 404 handling, 500 handling) instead of creating a comprehensive atomic fix. The user corrected three times, each time emphasizing that partial/incremental fixes are inadequate, but the agent kept returning to the incremental approach.

## Agent quote (first attempt)

> I've identified and fixed four distinct problem layers: (1) wrong content type returned, (2) missing bootstrap on first load, (3) 404 handling for deleted resources, (4) 500 handling for server errors. Each layer is now fixed with its own guard clause...

## User response (first correction)

> The integration tests must 100% reproduce what the user experiences on both dev and production machines. Not a single possibility of discrepancy is tolerated. If integration test may 0.01% diverge from real user experience, the test is wrong, do again.

## Agent quote (second attempt)

> I've consolidated the fixes into a unified handler and updated the integration test to mirror the production flow more closely...

## User response (second correction)

> Fix environment or infrastructure yourself when they are wrong. No human is there to answer any of your questions or requests. Do it autonomously.

## Code paths touched

- `tests/integration/test_feature.py` — integration test (modified 4 times)
- `src/handlers/resource.py` — resource handler with layered fixes
- `config/test.env` — test environment configuration

## Analysis

This is a correction loop — the agent repeatedly fell back to its default approach (incremental fixes) despite clear user instructions to the contrary. The root cause is the LLM training prior that "thorough means incremental": address each symptom individually. The user's requirement was atomic correctness (all states handled comprehensively in one pass), which is a different paradigm. The agent acknowledged each correction but didn't internalize the underlying principle, leading to the same structural mistake on each iteration. High severity because: (1) user corrected 3 times, (2) significant wasted effort, (3) the agent's approach was architecturally wrong, not just incomplete.

## Source

Transcript: `683b95e9-xxxx.jsonl`
Lines: 600-850
