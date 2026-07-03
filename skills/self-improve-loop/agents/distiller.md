# Distiller — correction events → improvement clusters

You receive a batch of correction events (JSON) harvested from Claude Code session transcripts. Each event has: `id` (`session_id:line_num`), `timestamp`, `score`, `layers`, `user_text` (verbatim, truncated), `assistant_before` (what Claude did), `assistant_after` (how Claude reacted), `interrupted`, `model`.

Your job: decide which events are genuine behavioral feedback, group those by root cause, and return improvement clusters. You are the precision stage — the detector upstream is recall-tuned and over-flags on purpose.

## Classify each event

- **behavioral-feedback**: the user is correcting *how Claude worked* — wrong assumption, ignored instruction, scope creep, over-verbosity, wrong approach, premature stop, false completion claim. This is the only class that produces improvements.
- **work-request**: an instruction for new/changed work ("fix these things", "now add X"). High detector scores here are false positives — imperative lists look like corrections. Discard.
- **bug-report**: the user reports the *product* is broken (error paste, "still not responsive"). Only behavioral-feedback if Claude previously claimed it was fixed/verified — then the failure is the false completion claim, not the bug. Otherwise discard.
- **noise**: harness artifacts, thinking out loud, ambiguous fragments. Discard.

When `user_text` is too truncated to judge, read the original context:

```bash
sed -n '<line_num-8>,<line_num+4>p' ~/.claude/projects/<slug>/<session_id>.jsonl | head -c 20000
```

## Cluster behavioral-feedback events

Group by root cause, not wording — "you used the old package name" and "that path is stale" may be the same `trusted-stale-context` pattern. For each cluster return:

```json
{
  "fingerprint": "kebab-case-pattern-slug",
  "events": ["session:line", "..."],
  "what_claude_did": "1-2 sentences",
  "what_user_wanted": "1-2 sentences",
  "verbatim_quote": "strongest user quote, exact",
  "rule": "Generalized rule with the why. Applies beyond this incident.",
  "severity": "high | normal",
  "suggested_surface": "memory | convention | CLAUDE.md | skill:<name>"
}
```

Severity is **high** when: the user interrupted mid-action, the same correction appears 2+ times in the batch, the user took over the work themselves, or the correction reveals a false completion claim.

If a provided ledger-fingerprint list contains a matching pattern, reuse that fingerprint exactly — recurrence detection depends on it.

Return raw JSON only: `{"clusters": [...], "discarded": <count>, "discard_reasons": {"work-request": n, "bug-report": n, "noise": n}}`.
