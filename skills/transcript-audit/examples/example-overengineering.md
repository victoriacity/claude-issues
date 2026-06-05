# Case: Agent added conditional logic when copy-from-template sufficed

| Field | Value |
|-------|-------|
| Session | `a969f3db` |
| Date | 2026-04-16 09:30 UTC |
| Model | claude-sonnet-4-6 |
| Context usage | 38400 in / 9200 out / 31500 cache-read / 6900 cache-create |
| Category | wrong-approach |
| Severity | low |
| Git branch | main |

## What happened

The user asked the agent to implement template initialization for new projects. The agent created a multi-step process: seed a file from a build mode constant before running a delegate prompt, with a fallback to a template if the delegate failed. The user pointed out that simply copying from the project template was sufficient.

## Agent quote

> I've implemented the initialization flow: first, `kit.py` is seeded from `BUILD_MODE_KIT_PY` before running the delegate prompt. If the delegate fails or produces invalid output, it falls back to the template version. This ensures we always have a valid starting point...

## User response

> shouldn't it be just copied from project template?

## Code paths touched

- `src/agent.py` — initialization logic with conditional seeding and fallback
- `templates/project/kit.py` — the template file that should have been copied directly

## Analysis

The agent over-engineered the solution. A simple file copy was the correct approach, but the agent added conditional logic, a fallback path, and a build-mode constant — all unnecessary complexity. This is a common pattern where the agent treats "more thorough" as "better" when the user wants the simplest correct solution. The conditional logic also introduced a subtle bug risk: the build-mode constant and the template could diverge, creating exactly the kind of inconsistency the simple copy avoids.

## Source

Transcript: `a969f3db-xxxx.jsonl`
Lines: 150-190
