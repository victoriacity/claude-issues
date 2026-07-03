#!/usr/bin/env python3
"""Harvest user corrections/feedback from Claude Code session transcripts.

One iteration of the self-improve loop calls this to collect every
human-authored correction in a trailing N-day window, deduplicated across
loop iterations via a state file.

Usage (stdlib-only, Python 3.9+):
    python3 harvest_corrections.py \
        --project-cwd /path/to/project \
        --days 7 \
        --min-score 3 \
        --state .claude/self-improve/harvest-state.json \
        --output .claude/self-improve/corrections.jsonl

Uses the vendored 8-layer correction detector (correction_signals.py).
Emits one JSON event per newly-seen correction, with the assistant turn
before (what Claude did) and after (how Claude reacted) for distillation.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Vendored 8-layer detector (correction_signals.py, same directory).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from correction_signals import (  # noqa: E402
    extract_text_from_content,
    get_ngrams,
    score_user_message,
)

INTERRUPT_MARKER_RE = re.compile(r'\[Request interrupted by user[^\]]*\]')
SYSTEM_REMINDER_RE = re.compile(r'<system-reminder>[\s\S]*?</system-reminder>')
HARNESS_MESSAGE_RE = re.compile(
    r'^\s*(<command-name>|<local-command-stdout>|<task-notification>|Caveat:'
    r'|This session is being continued from a previous conversation)'
)

USER_TEXT_LIMIT = 2000
ASSISTANT_BEFORE_LIMIT = 1200
ASSISTANT_AFTER_LIMIT = 800


def project_slug(cwd):
    """Map a project cwd to its ~/.claude/projects/ directory name."""
    return re.sub(r'[^A-Za-z0-9-]', '-', cwd)


def parse_ts(ts):
    try:
        return datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except (ValueError, AttributeError, TypeError):
        return None


def clean_user_text(text):
    """Strip harness-injected blocks; return (clean_text, was_interruption)."""
    interrupted = bool(INTERRUPT_MARKER_RE.search(text))
    text = INTERRUPT_MARKER_RE.sub('', text)
    text = SYSTEM_REMINDER_RE.sub('', text)
    return text.strip(), interrupted


def is_human_text_message(content):
    """True if the message contains at least one human-authored text block."""
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get('type') == 'text' and block.get('text', '').strip():
                return True
    return False


def harvest_session(filepath, since_dt):
    """Scan one main-session JSONL file; return correction candidate events."""
    session_id = Path(filepath).stem
    events = []
    pending = []  # events waiting for the next assistant text (assistant_after)

    prev_assistant_text = ''
    session_has_errors = False
    msg_index = 0
    user_message_lengths = []
    prior_user_ngrams = {}
    model = None
    git_branch = None
    cwd = None

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line_num, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if record.get('isSidechain'):
                continue
            if record.get('gitBranch') and not git_branch:
                git_branch = record['gitBranch']
            if record.get('cwd') and not cwd:
                cwd = record['cwd']

            rec_type = record.get('type', '')

            if rec_type == 'assistant':
                msg = record.get('message', {})
                if not isinstance(msg, dict):
                    continue
                if msg.get('model'):
                    model = msg['model']
                text = extract_text_from_content(msg.get('content', ''))
                if text.strip():
                    for ev in pending:
                        ev['assistant_after'] = text.strip()[:ASSISTANT_AFTER_LIMIT]
                    pending = []
                    prev_assistant_text = text
                continue

            if rec_type != 'user':
                continue
            msg = record.get('message', {})
            if not isinstance(msg, dict) or msg.get('role') != 'user':
                continue
            if record.get('isMeta'):
                continue

            content = msg.get('content', '')
            raw_text = extract_text_from_content(content)
            if '"is_error": true' in line or '"is_error":true' in line:
                session_has_errors = True

            if not is_human_text_message(content):
                continue

            text, interrupted = clean_user_text(raw_text)
            if not text or HARNESS_MESSAGE_RE.search(raw_text):
                continue

            ts = parse_ts(record.get('timestamp'))
            in_window = ts is not None and ts >= since_dt

            score, layers, keywords = score_user_message(
                text,
                prev_assistant_text_len=len(prev_assistant_text),
                msg_index=msg_index,
                user_message_lengths=user_message_lengths,
                prior_user_ngrams=prior_user_ngrams,
                session_has_errors=session_has_errors,
            )
            if interrupted:
                score += 3
                layers = layers + ['interruption']

            if in_window and score > 0:
                event = {
                    'id': f'{session_id}:{line_num}',
                    'session_id': session_id,
                    'line_num': line_num,
                    'timestamp': record.get('timestamp'),
                    'score': score,
                    'layers': layers,
                    'keywords': keywords[:10],
                    'user_text': text[:USER_TEXT_LIMIT],
                    'assistant_before': prev_assistant_text.strip()[:ASSISTANT_BEFORE_LIMIT],
                    'assistant_after': '',
                    'interrupted': interrupted,
                    'model': model,
                    'git_branch': git_branch,
                    'cwd': cwd,
                }
                events.append(event)
                pending.append(event)

            user_message_lengths.append(len(text))
            prior_user_ngrams[msg_index] = get_ngrams(text)
            msg_index += 1

    return events


def load_state(path):
    if path and os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'processed': {}, 'last_run': None}


def save_state(path, state):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=1)


def main():
    parser = argparse.ArgumentParser(description='Harvest user corrections from Claude Code transcripts')
    parser.add_argument('--project-cwd', default=os.getcwd(),
                        help='Project working directory whose transcripts to scan (default: cwd)')
    parser.add_argument('--transcript-dir', default=None,
                        help='Explicit transcript dir (overrides --project-cwd derivation)')
    parser.add_argument('--days', type=int, default=7, help='Trailing window in days (default: 7)')
    parser.add_argument('--min-score', type=int, default=3,
                        help='Minimum correction score to emit (default: 3)')
    parser.add_argument('--state', default=None,
                        help='State file for cross-iteration dedup (omit for stateless scan)')
    parser.add_argument('--output', default=None,
                        help='Append new events to this JSONL file (default: stdout)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report without updating state or output file')
    args = parser.parse_args()

    if args.transcript_dir:
        tdir = Path(args.transcript_dir).expanduser()
    else:
        tdir = Path.home() / '.claude' / 'projects' / project_slug(str(Path(args.project_cwd).resolve()))
    if not tdir.is_dir():
        print(f'ERROR: transcript dir not found: {tdir}', file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    since_dt = now - timedelta(days=args.days)
    state = load_state(args.state)
    processed = state.get('processed', {})

    files = sorted(p for p in tdir.glob('*.jsonl') if p.is_file())
    scanned = 0
    all_events = []
    for fp in files:
        # mtime prefilter: a file untouched since the window start has no in-window events
        if datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc) < since_dt:
            continue
        scanned += 1
        all_events.extend(harvest_session(fp, since_dt))

    flagged = [e for e in all_events if e['score'] >= args.min_score]
    new_events = [e for e in flagged if e['id'] not in processed]

    if args.output and not args.dry_run:
        os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
        with open(args.output, 'a', encoding='utf-8') as f:
            for e in new_events:
                f.write(json.dumps(e, ensure_ascii=False) + '\n')
    else:
        for e in new_events:
            print(json.dumps(e, ensure_ascii=False))
    if not args.dry_run:
        if args.state:
            for e in new_events:
                processed[e['id']] = e['timestamp'] or now.isoformat()
            # prune entries that have aged out of the window
            cutoff = since_dt - timedelta(days=1)
            state['processed'] = {
                k: v for k, v in processed.items()
                if (parse_ts(v) or now) >= cutoff
            }
            state['last_run'] = now.isoformat()
            save_state(args.state, state)

    summary = {
        'transcript_dir': str(tdir),
        'window_days': args.days,
        'since': since_dt.isoformat(),
        'sessions_scanned': scanned,
        'candidates_scored': len(all_events),
        'flagged_at_min_score': len(flagged),
        'new_events': len(new_events),
        'output': args.output or 'stdout',
        'dry_run': args.dry_run,
    }
    print(json.dumps(summary, indent=2), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
