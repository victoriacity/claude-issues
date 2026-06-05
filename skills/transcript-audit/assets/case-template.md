# Case: {one-line summary}

| Field | Value |
|-------|-------|
| Session | `{session_id}` |
| Date | {YYYY-MM-DD HH:MM UTC} |
| Model | {model_id} |
| Context usage | {input_tokens} in / {output_tokens} out / {cache_read} cache-read / {cache_creation} cache-create |
| Category | {tool-error / wrong-assumption / instruction-violation / scope-creep / repeated-failure / hallucination / wrong-approach / user-intent-miss} |
| Severity | {low / medium / high} |
| Git branch | {branch} |

## What happened

{2-4 sentence description of the failure}

## Agent quote

> {exact assistant text from transcript}

## User response (if applicable)

> {exact user text from transcript, or "N/A" for automated sessions}

## Code paths touched

- `{file_path}` — {what agent did}

## Analysis

{Root cause analysis: why did the failure occur, which category, which principle violated if applicable}

## Source

Transcript: `{path to JSONL}`
Lines: {approximate range}
