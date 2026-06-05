# claude-issues

`transcript-audit` — a Claude Code skill that scans your local Claude Code conversation transcripts (the JSONL files under `~/.claude/projects/`) for agent failures, instruction violations, user corrections, and behavioral patterns. It produces individual case reports with verbatim quotes and metadata, a synthesis report, and a reproducible benchmark suite.

## What it does

Claude Code stores every session as a JSONL file in `~/.claude/projects/<project-dir>/`. Each line is a typed event (user message, assistant response, tool result, system event). This skill runs a five-phase pipeline over those files:

1. **Signal extraction** — scan transcripts for failure indicators (tool errors, user corrections, conversational loops). 8 user-correction detection layers + point signals for tool errors, interruptions, and self-corrections.
2. **Packet extraction** — build compact failure-context packets (signal + surrounding messages) for flagged sessions.
3. **Agent classification** — parallel subagents review packets, classify true positives vs infrastructure noise vs benign retries, write case files.
4. **Synthesis** — aggregate cases into a statistical report.
5. **Benchmark derivation** — turn failure patterns into reproducible test cases.

See `skills/transcript-audit/SKILL.md` for the full pipeline reference (signal weights, failure categories, common mistakes).

## When to use

- Periodic quality audit of Claude Code behavior across many sessions
- After a sprint or project phase, to identify systematic failure patterns
- Investigating a specific failure type across many sessions
- Building an eval suite from real-world failure data

Not designed for single-session investigation (just read the JSONL directly) or real-time monitoring.

## Install

Drop the skill into the standard Claude Code skills location:

```bash
# user-scope (available across all projects)
cp -r skills/transcript-audit ~/.claude/skills/

# or project-scope
cp -r skills/transcript-audit /path/to/your/project/.claude/skills/
```

Then in a Claude Code session, invoke it as `/transcript-audit`.

## Run the pipeline manually

The scripts work standalone — useful if you want to run the pipeline without going through the Claude Code skill harness.

Requirements: **Python 3.10+, standard library only**. No third-party dependencies.

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
