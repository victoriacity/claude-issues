---
name: self-improve-loop
description: "Use when setting up a recurring /loop that recursively improves Claude's performance from real user corrections and feedback. Each iteration harvests corrections from the past 7 days of the current project's session transcripts, distills them into durable rules (CLAUDE.md, conventions, memory, skills), verifies earlier fixes actually stopped the pattern, and escalates repeat offenders toward mechanical enforcement. Trigger whenever the user wants Claude to 'learn from feedback', 'stop repeating mistakes', 'improve itself from transcripts', or asks for a standing self-improvement loop."
version: 1
last-updated: 2026-07-03
update-reason: "Initial version"
success-criteria:
  - slug: harvest_deduped
    description: "Each iteration processes only corrections not seen by prior iterations (state-file dedup)"
  - slug: improvements_durable
    description: "Every applied improvement lands in a governing document, not just conversation"
  - slug: provenance_exact
    description: "Every improvement cites session ID, line number, and verbatim user quote"
  - slug: recurrence_escalated
    description: "A correction pattern that reappears after a fix is escalated, never re-fixed identically"
  - slug: rule_budget_respected
    description: "At most 3 improvements per iteration; no near-duplicate rules created"
  - slug: loop_scheduled
    description: "Under /loop dynamic mode, every iteration ends with a ScheduleWakeup call or an explicit stop decision"
inputs:
  - name: transcript_dir
    type: command_output
    source: "~/.claude/projects/<slug-of-cwd>/ JSONL session files (derived automatically from the project cwd)"
  - name: window_days
    type: conversation
    source: "Trailing window, default 7 days"
outputs:
  - name: improvements
    type: file_edit
    description: "Rules embedded in CLAUDE.md / conventions / memory / skill files"
  - name: ledger
    type: file_edit
    description: ".claude/self-improve/ledger.jsonl — one entry per iteration with fingerprints and outcomes"
---

# /self-improve-loop

Set up a recurring loop that turns real user corrections into durable behavioral rules, then checks its own past fixes against fresh transcript evidence. The loop is recursive in two senses: each iteration's improvements are validated (or escalated) by the next iteration's data, and the loop tunes its own detection thresholds from observed precision.

Works on any Claude Code project: everything it needs is the project's transcript directory (`~/.claude/projects/<slug-of-cwd>/`, derived automatically) and the project's own steering documents. The scripts are Python 3.9+ standard library only.

## How to start the loop

The loop rides on the `/loop` feature. Three ways to run:

```
# Self-paced (recommended) — the model schedules its own next iteration via ScheduleWakeup
/loop /self-improve-loop

# Fixed interval — the harness re-fires the prompt every 2 hours
/loop 2h /self-improve-loop

# One-shot — run a single iteration now, no recurrence
/self-improve-loop
```

If the skill is not installed under `.claude/skills/` (so `/self-improve-loop` doesn't resolve), use the prompt form: `/loop Read <path-to-this-SKILL.md> and run one iteration`.

Corrections accrue at human speed, so short intervals waste tokens. Under dynamic mode, follow the pacing rules in Step 6.

## Files

| Path | Purpose |
|------|---------|
| `<skill-dir>/scripts/harvest_corrections.py` | Deduped 7-day correction extraction |
| `<skill-dir>/scripts/correction_signals.py` | Vendored 8-layer correction detector (recall-tuned) |
| `<skill-dir>/agents/distiller.md` | Instructions for distillation subagents |
| `<project>/.claude/self-improve/harvest-state.json` | Cross-iteration dedup state (managed by the script) |
| `<project>/.claude/self-improve/corrections.jsonl` | Accumulated correction events |
| `<project>/.claude/self-improve/ledger.jsonl` | One entry per iteration: clusters, fingerprints, actions, precision |
| `<project>/.claude/self-improve/config.json` | Tunable knobs: `min_score`, `window_days`, `rule_budget` |

`<skill-dir>` is wherever this SKILL.md lives. `<project>` is the working directory of the project being improved — the loop's state travels with the project it learns about. Whether to commit `.claude/self-improve/` or gitignore it is the host project's choice; the loop works either way.

## One iteration

### Step 1 — HARVEST

Read `<project>/.claude/self-improve/config.json` if it exists (defaults: `min_score=3`, `window_days=7`, `rule_budget=3`). Then:

```bash
python3 <skill-dir>/scripts/harvest_corrections.py \
  --project-cwd "$(pwd)" \
  --days 7 --min-score 3 \
  --state .claude/self-improve/harvest-state.json \
  --output .claude/self-improve/corrections.jsonl
```

The script scans every main-session JSONL for the current project, scores each human message across 8 correction layers, filters harness noise (compaction summaries, command output, system reminders), and emits only events not seen by prior iterations. Each event carries the verbatim user text, the assistant turn being corrected, and the assistant's reaction. Use `--transcript-dir` to point at a non-default transcript location.

**If `new_events` is 0**: skip to Step 5 (record an empty iteration), then Step 6. Do not manufacture improvements from stale data — an empty iteration is a correct outcome, not a failure.

### Step 2 — DISTILL

Group the new events into clusters that share a root behavioral cause (same rule violated, not same wording). For ≤10 events, distill inline. For more, dispatch parallel subagents with `<skill-dir>/agents/distiller.md`, ~10 events each, then merge clusters.

For each cluster produce:
- **What Claude did** and **what the user actually wanted** (with verbatim quotes + `session_id:line_num` provenance)
- **The generalized rule** — phrased so it applies beyond the triggering incident; state the *why*, not just the *what*
- **Severity**: high (interruption, repeated correction, user takeover) or normal
- **Fingerprint**: a short kebab-case slug for the failure pattern (e.g. `assumed-stale-package-name`). Fingerprints are how recurrence is detected across iterations — reuse an existing ledger fingerprint when the pattern matches; mint a new one only for genuinely new patterns.

Discard clusters that are not behavioral feedback: infrastructure noise, the user thinking out loud, new task instructions that merely *look* like corrections. Count discards — they feed the precision tuning in Step 6.

### Step 3 — APPLY (with escalation ladder)

Read the ledger tail (last ~10 entries) first. For each surviving cluster, check whether its fingerprint already has a fix on record, and pick the action one rung above whatever was done last time:

| Level | Condition | Action |
|-------|-----------|--------|
| 0 | New pattern | Write the rule into the *lightest adequate surface* (see below) |
| 1 | Recurred once after a fix | Strengthen: rewrite with concrete trigger phrases and a banned/required-behavior list; move the rule to a more prominent or more binding document |
| 2 | Recurred twice | Propose mechanical enforcement: a hook or validation script. Create it if the project lets you; otherwise file a high-priority item in the project's task tracker (TASKS.md, issues) — never leave it as an unowned suggestion |
| 3 | Recurred after mechanical enforcement | Write a postmortem: the fix strategy itself is wrong. Analyze why three fixes failed before writing a fourth |

**Target surfaces, lightest first.** Prefer editing an existing rule over adding a new one — every added rule consumes context budget in all future sessions:
1. Auto-memory (if this Claude Code setup has a persistent memory directory) — user-preference-shaped corrections
2. A themed doc the project already has (`docs/conventions/*.md`, CONTRIBUTING, project README section)
3. The project's `CLAUDE.md` — only for rules that must bind every session
4. A specific skill's SKILL.md — when the correction targets that skill's procedure

Follow the host project's conventions for recording feedback if it has them (e.g. a `feedback/` directory with one record per correction). Never edit files the project marks protected (hooks, guarded CLAUDE.md sections) — route those through the task tracker instead.

**Rule budget**: apply at most `rule_budget` (default 3) improvements per iteration, highest severity first; defer the rest to the next iteration (they stay in `corrections.jsonl` and their clusters are recorded in the ledger as `deferred`). A single-event cluster only qualifies if high severity; otherwise record it as `watching` and act when a second event confirms the pattern.

### Step 4 — VERIFY

Before writing each rule: grep the target surfaces for an existing rule covering the same behavior — if found, strengthen it in place rather than duplicating, and grep for contradictions with what you're about to write. After writing: confirm the rule reads correctly in context and appears exactly once.

Recurrence verification (the recursive core): for every fingerprint that got a fix in an earlier iteration, check whether any *new* event in this window matches it **with a timestamp after the fix landed**. A match means the fix failed → escalate per the ladder. No matches across a full window means the fix is holding → mark it `holding` in the ledger.

### Step 5 — RECORD

Append one entry to `<project>/.claude/self-improve/ledger.jsonl`:

```json
{"ts": "<iso>", "window_days": 7, "new_events": 12, "clusters": 4, "discarded": 2,
 "actions": [{"fingerprint": "assumed-stale-package-name", "level": 0, "target": "docs/conventions/tooling.md", "events": ["<session:line>", "..."]}],
 "holding": ["earlier-fingerprint"], "deferred": [], "watching": [],
 "precision": 0.67, "min_score": 3}
```

If the project uses git, commit everything the iteration touched (rules, ledger, state) in one commit following the host's commit conventions, e.g.: `improve(self-improve-loop): <n> rules from <m> corrections — <fingerprints>`. If the host project has a session-reporting convention (Slack, log file), post a one-line summary — but only for iterations that applied or escalated something; silent-skip empty iterations.

### Step 6 — SCHEDULE (dynamic /loop mode only)

Self-tune first: precision = clusters acted on ÷ clusters distilled. If precision < 0.5 across the last 3 non-empty iterations, raise `min_score` by 1 in `config.json`; if the user manually reports a missed correction, lower it by 1 (floor 2).

Then schedule the next wake with the same `/loop` prompt:
- New events were found this iteration → `delaySeconds: 1200` (user is active; more corrections likely soon)
- No new events → `delaySeconds: 3600` (max backoff; corrections accrue at human speed)
- Never schedule below 900s — transcript growth cannot outpace that, and tighter polling just burns tokens

Stop (omit ScheduleWakeup and say why) when: the user asks to stop, the transcript directory disappears, or 3 consecutive iterations ended in errors you could not fix.

If running under fixed-interval `/loop` or one-shot, skip scheduling — but still print the iteration summary (new events, clusters, actions, holding fingerprints) as the final message.

## Guardrails

- **Improvements must trace to evidence.** Every rule cites session:line + verbatim quote. A rule you cannot source to a transcript event does not get written.
- **Never weaken or delete an existing rule** based on absence of corrections — absence of evidence is not evidence the rule is unneeded.
- **Corrections predating an existing fix are history, not signal.** Compare event timestamp to fix timestamp before counting recurrence.
- **This loop edits steering documents, never application code.** A correction about a code bug becomes a task in the project's tracker, not a code edit from inside the loop.
- **The harvest runs in seconds; never sleep-poll transcripts in-session** — pacing between iterations is what the /loop schedule is for.

## Common mistakes

1. **Treating task instructions as corrections.** "Fix several things: 1) ..." scores high on the detector but is a work request, not behavioral feedback. The distiller must ask: *is the user correcting how Claude behaved, or asking for new work?*
2. **Re-writing the same rule at Level 0 forever.** The whole point of fingerprints is that a recurred pattern climbs the ladder. Check the ledger before applying.
3. **Rule sprawl.** Ten narrow rules that each fire once are worse than one general rule that fires ten times. Generalize, and prefer strengthening existing rules.
4. **Harvesting other projects' transcripts.** The window is scoped to the *current project's* transcript directory. Cross-project harvesting mixes incompatible conventions.
5. **Acting on the raw score.** The score is recall-tuned triage; the distiller supplies precision. Never auto-write a rule from an event without reading it.
