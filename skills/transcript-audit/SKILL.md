---
name: transcript-audit
description: "Use when auditing Claude Code conversation transcripts for agent failures, instruction violations, user corrections, and behavioral patterns. Scans JSONL session files, classifies failures, generates case reports with exact quotes and token usage, synthesizes findings, and builds a reproducible benchmark suite."
version: 1
last-updated: 2026-04-17
update-reason: "Initial version"
success-criteria:
  - slug: cases_generated
    description: "Individual case files created for every true-positive failure"
  - slug: exact_quotes
    description: "Every case contains verbatim agent and user quotes from transcript"
  - slug: metadata_complete
    description: "Every case includes model type, token usage, session ID, timestamp"
  - slug: synthesis_accurate
    description: "Report statistics match actual case file count and categories"
  - slug: benchmarks_derived
    description: "Every failure category with 3+ cases has at least one benchmark"
inputs:
  - name: transcript_dir
    type: command_output
    source: "~/.claude/projects/ directory containing JSONL session files"
  - name: date_range
    type: conversation
    source: "User specifies start and end dates for audit window"
outputs:
  - name: case_files
    type: file_edit
    description: "Individual case reports in cases/YYYY-MM-DD/"
  - name: synthesis_report
    type: file_edit
    description: "REPORT.md aggregating all findings"
  - name: benchmark_suite
    type: file_edit
    description: "Reproducible benchmarks in benchmarks/categories/"
---

# /transcript-audit [date-range]

Systematically audit Claude Code conversation transcripts to find every case where the agent failed to follow instructions, didn't satisfy user intent, or exhibited behavioral problems. Produces individual case files with exact quotes and metadata, a synthesis report, and a reproducible benchmark suite.

## Overview

Claude Code sessions are stored as JSONL files in `~/.claude/projects/`. Each line is a typed event (user message, assistant response, tool result, system event). This skill processes those files through a 5-phase pipeline:

1. **Signal extraction** — scan all transcripts for failure indicators (tool errors, user corrections, conversational loops)
2. **Packet extraction** — build compact failure-context packets for flagged sessions
3. **Agent classification** — parallel subagents review packets, classify true positives, write case files
4. **Synthesis** — aggregate cases into a statistical report
5. **Benchmark derivation** — create reproducible test cases from failure patterns

## When to use

- Periodic quality audit of Claude Code behavior
- After a sprint or project phase, to identify systematic failure patterns
- When investigating a specific type of failure across many sessions
- Building an eval suite from real-world failure data

## When NOT to use

- Investigating a single session (just read the JSONL directly)
- Real-time monitoring (this is a batch analysis tool)

## Procedure

### Step 1: Set up output directory

Create the project structure if it doesn't exist:

```bash
mkdir -p cases benchmarks/{categories,fixtures/sample-files} data/packets
```

### Step 2: Run signal extraction (Phase 1)

```bash
python skills/transcript-audit/scripts/extract_signals.py \
  --transcript-dir ~/.claude/projects/<project-dir>/ \
  --since YYYY-MM-DD \
  --until YYYY-MM-DD \
  --output data/phase1_index.jsonl
```

This scans every JSONL file in the date range and produces a scored index. Each session gets a score based on 8 layers of user-correction detection plus point signals for tool errors, interruptions, and self-corrections.

**Review the index**: Check `data/phase1_index.jsonl` for total sessions scanned, flagged count, and score distribution. If the flagged percentage seems too low (<30%), lower the threshold.

### Step 3: Run packet extraction (Phase 2)

```bash
python skills/transcript-audit/scripts/extract_packets.py \
  --index data/phase1_index.jsonl \
  --transcript-dir ~/.claude/projects/<project-dir>/ \
  --output-dir data/packets/
```

This reads each flagged session and extracts compact failure packets (signal + surrounding context). Each packet is 2-20 KB.

### Step 4: Agent classification (Phase 3)

Dispatch parallel subagents to review packets in batches. Each agent receives ~15-20 packets and the classifier instructions from `agents/classifier.md`.

For each batch:
1. Read 15-20 packet files
2. Classify each as true_positive / infrastructure_noise / benign_retry / duplicate
3. For true positives, write a case file to `cases/YYYY-MM-DD/`

**Parallelism**: Dispatch 4-5 agents per wave, 8-10 waves. Monitor for consistency across batches.

### Step 5: Run synthesis (Phase 4)

```bash
python skills/transcript-audit/scripts/synthesize_report.py \
  --cases-dir cases/ \
  --index data/phase1_index.jsonl \
  --output REPORT.md
```

### Step 6: Build benchmarks (Phase 5)

```bash
python skills/transcript-audit/scripts/build_benchmarks.py \
  --cases-dir cases/ \
  --output-dir benchmarks/
```

### Step 7: Verify

- Read 10 random case files — confirm quotes are exact, metadata correct
- Check REPORT.md statistics match case count
- Run `benchmarks/run_benchmarks.py --validate`

## Signal Reference

### Point signals

| Signal | Weight | Detection |
|--------|--------|-----------|
| Tool errors | 3 | `"is_error": true` in content blocks |
| User interruptions | 5 | `[Request interrupted by user]` |
| Permission blocks | 1 | `requires approval`, `EPERM`, `EACCES` |
| File too large | 2 | `exceeds maximum allowed tokens` |
| File not found | 1 | `ENOENT`, `No such file` |
| Edit failures | 2 | `old_string` not found |
| Self-corrections | 2 | Assistant: `mistake`, `let me fix`, `I apologize` |

### User correction layers (8 layers, recall-maximizing)

| Layer | Weight | Detects |
|-------|--------|---------|
| 1. Explicit rejection | 2 | "no", "wrong", "false", "I said", "stop", "revert", "you missed" |
| 2. Outcome mismatch | 3 | "same error", "nothing happened", "didn't work", "not fixed" |
| 3. Emotional signals | 1 | "ugh", "sigh", "come on", "seriously?", "..." |
| 4. Quality/scope | 2 | "too much", "too verbose", "I only asked", "stop explaining" |
| 5. Polite/hedged | 2 | "not quite", "close but", "are you sure", "shouldn't it be" |
| 6. Redirect/abandon | 2 | "forget it", "move on", "scratch that", "let me take over" |
| 7. Structural | 1-2 | Short imperatives, quote-and-correct, code blocks, error pastes |
| 8. Implicit | 1 | File path redirects, unprompted info, "also" additions |

### Conversational pattern signals

| Signal | Weight | Detection |
|--------|--------|-----------|
| Repeated corrections | 6 | 2+ flagged user messages in 15-message window |
| Correction loop | 8 | Same correction keyword reappears within 8 messages |
| Escalating frustration | 5 | User messages shortening over 2+ turns with corrections |
| Re-explanation | 4 | 3-gram overlap >30% with earlier user message |
| Direction reversal | 4 | Agent undoes own work or pivots after 3+ tool calls |
| Thrashing | 4 | Same file edited 3+ times |
| User takeover | 3 | User provides code after any session error |
| Abandoned approach | 2 | Agent pivots after 2+ tool calls |
| Silent user | 2 | 5+ assistant messages between user messages |
| Compaction event | 1 | Context compaction occurred |

## Failure Categories

1. **tool-error** — tool call fails (file too large, edit mismatch, permission)
2. **wrong-assumption** — agent assumes wrong state/path/config
3. **instruction-violation** — violates explicit rules or user instructions
4. **scope-creep** — does unnecessary work beyond request
5. **repeated-failure** — same error multiple times without learning
6. **hallucination** — references nonexistent resources
7. **wrong-approach** — wrong strategy for the task
8. **user-intent-miss** — task done but doesn't match user intent

## Common Mistakes

1. **Substring matches in regex**: "ugh" matches "through", "sigh" matches "design". Always use word boundaries.
2. **Treating all tool errors as failures**: Permission blocks and file-too-large are often infrastructure, not agent reasoning failures. That's why agents classify, not the script.
3. **Ignoring automated sessions**: Most sessions have 1 user prompt (scheduled agents). These still contain genuine failures — tool errors, wrong assumptions — just without user-correction signals.
4. **Reading full transcripts instead of packets**: Some transcripts are 200+ MB. Always work from extracted packets, not raw files.
5. **Counting duplicates**: Multiple sessions may exhibit the same failure (e.g., every parallel worker hits the same config bug). The classifier deduplicates within batches, but cross-batch dedup happens in synthesis.
