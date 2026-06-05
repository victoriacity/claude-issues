# Case: Component tests passed but end-to-end user flow failed

| Field | Value |
|-------|-------|
| Session | `9d7b0ace` |
| Date | 2026-04-10 14:20 UTC |
| Model | claude-sonnet-4-6 |
| Context usage | 71800 in / 22100 out / 58000 cache-read / 13800 cache-create |
| Category | wrong-assumption |
| Severity | high |
| Git branch | main |

## What happened

The agent was verifying that UI components were working correctly. It ran component-level screenshot verification tests and reported all passing (7 passed, 4 skipped data-dependent, 0 failed). The user then tried the actual user workflow — creating a new project on the running application — and got a server connection error, revealing that the components were verified in isolation but the end-to-end flow was broken.

## Agent quote

> All screenshot verifications passing: 7 passed, 4 skipped (data-dependent), 0 failed. File attachment: PASS. Paste-as-file modal: PASS. Project selector: PASS. Settings panel: PASS...

## User response

> creating a project on localhost:3333 gives "Couldn't connect to the server. Please try again."

## Code paths touched

- `tests/components/test_ui.py` — component tests (all green)
- `src/routes/project.py` — project creation endpoint (not tested e2e)
- `config/server.py` — server configuration

## Analysis

The agent verified components in isolation (screenshot tests of individual UI elements) and reported success without testing the actual user workflow. This is a classic testing gap: component tests verify rendering, not functionality. The connection error on project creation would have been caught by any e2e test that actually submitted the form. The agent assumed component-level verification was sufficient, when the user's intent was to verify that features work end-to-end. This failure pattern appears frequently: agents optimize for the metric they can measure (component test pass rate) rather than the outcome the user cares about (features actually work).

## Source

Transcript: `9d7b0ace-xxxx.jsonl`
Lines: 420-490
