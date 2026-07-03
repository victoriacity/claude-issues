# claude-issues

Claude Code skills for learning from your own session history:

- **`transcript-audit`** — scan your local Claude Code conversation transcripts (the JSONL files under `~/.claude/projects/`) for agent failures, instruction violations, user corrections, and behavioral patterns. Produces case reports with verbatim quotes, a synthesis report, and a reproducible benchmark suite.
- **`self-improve-loop`** — a recurring `/loop` that recursively improves Claude's behavior: each iteration harvests user corrections from the past 7 days of the current project's transcripts, distills them into durable rules (CLAUDE.md, conventions, memory), verifies earlier fixes actually stopped the pattern, and escalates repeat offenders toward mechanical enforcement.

Both are standalone: Python 3.9+ standard library only, no third-party dependencies, no network access. They read your local transcripts and write to your project's own files.

## self-improve-loop

Start it with the `/loop` feature and it runs unattended:

```
/loop /self-improve-loop        # self-paced: the model schedules its own next iteration
/loop 2h /self-improve-loop     # fixed interval
/self-improve-loop              # one-shot single iteration
```

Each iteration: **HARVEST** (deduped extraction of user corrections from the trailing 7-day window) → **DISTILL** (cluster by root cause; discard work requests and noise) → **APPLY** (write rules into the lightest adequate steering surface, max 3 per iteration) → **VERIFY** (check earlier fixes against fresh evidence) → **RECORD** (append a ledger entry) → **SCHEDULE** (pace the next wake-up).

The recursion is the point: a correction pattern that reappears *after* a fix landed climbs an escalation ladder — rewrite the rule → move it somewhere more binding → propose mechanical enforcement (hook/validation script) → postmortem the fix strategy itself. The loop also tunes its own detection threshold from observed precision. See `skills/self-improve-loop/SKILL.md` for the full procedure.

## transcript-audit

Claude Code stores every session as a JSONL file in `~/.claude/projects/<project-dir>/`. Each line is a typed event (user message, assistant response, tool result, system event). This skill runs a five-phase pipeline over those files:

1. **Signal extraction** — scan transcripts for failure indicators (tool errors, user corrections, conversational loops). 8 user-correction detection layers + point signals for tool errors, interruptions, and self-corrections.
2. **Packet extraction** — build compact failure-context packets (signal + surrounding messages) for flagged sessions.
3. **Agent classification** — parallel subagents review packets, classify true positives vs infrastructure noise vs benign retries, write case files.
4. **Synthesis** — aggregate cases into a statistical report.
5. **Benchmark derivation** — turn failure patterns into reproducible test cases.

See `skills/transcript-audit/SKILL.md` for the full pipeline reference (signal weights, failure categories, common mistakes).

### When to use

- Periodic quality audit of Claude Code behavior across many sessions
- After a sprint or project phase, to identify systematic failure patterns
- Investigating a specific failure type across many sessions
- Building an eval suite from real-world failure data

Not designed for single-session investigation (just read the JSONL directly) or real-time monitoring. For a standing loop that acts on what it finds, use `self-improve-loop` instead.

## Install

Drop either skill (or both) into the standard Claude Code skills location:

```bash
# user-scope (available across all projects)
cp -r skills/transcript-audit skills/self-improve-loop ~/.claude/skills/

# or project-scope
cp -r skills/transcript-audit skills/self-improve-loop /path/to/your/project/.claude/skills/
```

Then in a Claude Code session, invoke them as `/transcript-audit` or `/self-improve-loop` (or `/loop /self-improve-loop` for the recurring form). Each skill folder is self-contained — installing one without the other works.

## Run the scripts manually

The scripts work standalone — useful if you want to run them without going through the Claude Code skill harness.

Requirements: **Python 3.10+, standard library only**. No third-party dependencies.

```bash
# self-improve-loop: harvest new corrections from the trailing 7-day window
python skills/self-improve-loop/scripts/harvest_corrections.py \
  --project-cwd /path/to/your/project \
  --days 7 --min-score 3 \
  --state .claude/self-improve/harvest-state.json \
  --output .claude/self-improve/corrections.jsonl
```

```bash
# Phase 1: scan transcripts, produce scored index
python skills/transcript-audit/scripts/extract_signals.py \
  --transcript-dir ~/.claude/projects/<project-dir>/ \
  --since 2026-04-01 \
  --until 2026-04-15 \
  --output data/phase1_index.jsonl

# Phase 2: extract failure-context packets
python skills/transcript-audit/scripts/extract_packets.py \
  --index data/phase1_index.jsonl \
  --transcript-dir ~/.claude/projects/<project-dir>/ \
  --output-dir data/packets/

# Phase 3 is agent-driven (see skills/transcript-audit/agents/classifier.md)
# It writes case files to cases/YYYY-MM-DD/

# Phase 4: synthesize a REPORT.md
python skills/transcript-audit/scripts/synthesize_report.py \
  --cases-dir cases/ \
  --index data/phase1_index.jsonl \
  --output REPORT.md

# Phase 5: derive benchmarks from cases
python skills/transcript-audit/scripts/build_benchmarks.py \
  --cases-dir cases/ \
  --output-dir benchmarks/
```

## Layout

```
skills/self-improve-loop/
├── SKILL.md                       # Skill manifest + the 6-step iteration procedure
├── scripts/
│   ├── harvest_corrections.py     # Deduped 7-day correction extraction (state-file dedup)
│   └── correction_signals.py      # Vendored 8-layer correction detector
└── agents/
    └── distiller.md               # Distillation-subagent instructions (cluster + classify)

skills/transcript-audit/
├── SKILL.md                       # Skill manifest + full pipeline doc
├── scripts/
│   ├── extract_signals.py         # Phase 1: scan + score
│   ├── extract_packets.py         # Phase 2: failure-context packets
│   ├── synthesize_report.py       # Phase 4: aggregate to REPORT.md
│   └── build_benchmarks.py        # Phase 5: derive benchmarks
├── agents/
│   └── classifier.md              # Phase 3 classifier-agent instructions
├── assets/
│   └── case-template.md           # Case file template
└── examples/                      # Six example case files showing output shape
```

## License

MIT — see `LICENSE`.
