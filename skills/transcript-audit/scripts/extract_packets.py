#!/usr/bin/env python3
"""Phase 2: Extract compact failure packets from flagged sessions.

Usage:
    python extract_packets.py \
        --index data/phase1_index.jsonl \
        --transcript-dir ~/.claude/projects/<project>/ \
        --output-dir data/packets/
"""

import argparse
import json
import os
import sys
from pathlib import Path


def extract_text_from_content(content):
    """Extract plain text from message content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get('type') == 'text':
                    texts.append(block.get('text', ''))
                elif block.get('type') == 'tool_result':
                    tc = block.get('content', '')
                    if isinstance(tc, str):
                        texts.append(tc)
                    elif isinstance(tc, list):
                        for tb in tc:
                            if isinstance(tb, dict) and tb.get('type') == 'text':
                                texts.append(tb.get('text', ''))
                elif block.get('type') == 'tool_use':
                    name = block.get('name', '')
                    inp = block.get('input', {})
                    # Summarize tool call
                    if name in ('Read', 'Edit', 'Write'):
                        target = inp.get('file_path', '')
                        texts.append(f"[Tool: {name} {target}]")
                    elif name == 'Bash':
                        cmd = inp.get('command', '')[:200]
                        texts.append(f"[Tool: Bash `{cmd}`]")
                    elif name == 'Grep':
                        pat = inp.get('pattern', '')
                        texts.append(f"[Tool: Grep `{pat}`]")
                    else:
                        texts.append(f"[Tool: {name}]")
        return '\n'.join(texts)
    return ''


def summarize_message(record, max_text=500):
    """Create a compact summary of a JSONL record."""
    rec_type = record.get('type', '')
    msg = record.get('message', {})

    if rec_type in ('user', 'assistant') and isinstance(msg, dict):
        role = msg.get('role', rec_type)
        content = msg.get('content', '')
        text = extract_text_from_content(content)

        # Check for errors in tool results
        has_error = False
        error_text = ''
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('is_error'):
                    has_error = True
                    tc = block.get('content', '')
                    if isinstance(tc, str):
                        error_text = tc[:300]

        summary = {
            'role': role,
            'text': text[:max_text],
            'has_error': has_error,
        }
        if error_text:
            summary['error_text'] = error_text

        # Include model/usage for assistant messages
        if role == 'assistant':
            if msg.get('model'):
                summary['model'] = msg['model']
            if msg.get('usage'):
                summary['usage'] = msg['usage']

        return summary

    elif rec_type == 'attachment':
        att = record.get('attachment', {})
        return {
            'role': 'attachment',
            'type': att.get('type', ''),
            'text': str(att.get('stdout', '') or att.get('stderr', ''))[:300],
        }

    return {
        'role': rec_type,
        'text': str(record.get('message', ''))[:200],
    }


def extract_packet(index_entry, transcript_dir):
    """Extract a failure packet from a session transcript."""
    filepath = index_entry['file_path']

    if not os.path.exists(filepath):
        # Try resolving relative to transcript_dir
        alt = os.path.join(transcript_dir, os.path.basename(filepath))
        if os.path.exists(alt):
            filepath = alt
        else:
            return None

    # Read all messages
    messages = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line_num, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    rec_type = record.get('type', '')
                    if rec_type in ('user', 'assistant', 'attachment'):
                        messages.append({
                            'line_num': line_num,
                            'record': record,
                        })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"  Error reading {filepath}: {e}", file=sys.stderr)
        return None

    # Build the packet
    packet = {
        'session_id': index_entry['session_id'],
        'file_path': index_entry['file_path'],
        'model': index_entry.get('model'),
        'timestamp': index_entry.get('timestamp'),
        'slug': index_entry.get('slug'),
        'git_branch': index_entry.get('git_branch'),
        'is_subagent': index_entry.get('is_subagent', False),
        'total_score': index_entry.get('total_score', 0),
        'token_usage': {
            'input_tokens': index_entry.get('total_input_tokens', 0),
            'output_tokens': index_entry.get('total_output_tokens', 0),
            'cache_read_tokens': index_entry.get('total_cache_read_tokens', 0),
            'cache_creation_tokens': index_entry.get('total_cache_creation_tokens', 0),
        },
        'message_count': index_entry.get('message_count', 0),
        'human_message_count': index_entry.get('human_message_count', 0),
        'first_user_prompt': index_entry.get('first_user_prompt', ''),
        'signals_summary': {
            k: v for k, v in index_entry.get('signals', {}).items()
            if k != 'user_corrections'
        },
        'failure_contexts': [],
    }

    # Extract context windows around each signal
    user_corrections = index_entry.get('signals', {}).get('user_corrections', [])

    # Also flag lines with tool errors
    signal_lines = set()
    for correction in user_corrections:
        signal_lines.add(correction.get('line_num', -1))

    # Add context windows: 3 before, 2 after each signal
    context_radius_before = 3
    context_radius_after = 2

    for correction in user_corrections:
        target_line = correction.get('line_num', -1)
        if target_line < 0:
            # Use msg_index as fallback
            target_idx = correction.get('msg_index', 0)
            if target_idx < len(messages):
                target_line = messages[target_idx]['line_num']

        # Find messages around this line
        context_messages = []
        for m in messages:
            if (m['line_num'] >= target_line - context_radius_before * 50 and
                m['line_num'] <= target_line + context_radius_after * 50):
                # More precise: find by index proximity
                pass

        # Simpler approach: find the message index closest to target_line
        target_msg_idx = None
        for idx, m in enumerate(messages):
            if m['line_num'] >= target_line:
                target_msg_idx = idx
                break

        if target_msg_idx is None:
            target_msg_idx = len(messages) - 1

        start_idx = max(0, target_msg_idx - context_radius_before)
        end_idx = min(len(messages), target_msg_idx + context_radius_after + 1)

        context = {
            'signal': {
                'score': correction.get('score', 0),
                'layers': correction.get('layers', []),
                'keywords': correction.get('keywords', []),
                'snippet': correction.get('snippet', ''),
            },
            'messages': [
                {
                    'line_num': messages[i]['line_num'],
                    **summarize_message(messages[i]['record']),
                }
                for i in range(start_idx, end_idx)
            ],
        }
        packet['failure_contexts'].append(context)

    # Also add contexts around tool errors (if not already covered by user corrections)
    for idx, m in enumerate(messages):
        record = m['record']
        if record.get('type') == 'user':
            content = record.get('message', {}).get('content', '')
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get('is_error'):
                        # Check if this line is already covered
                        already_covered = any(
                            abs(m['line_num'] - c.get('line_num', -999)) < 20
                            for c in user_corrections
                        )
                        if not already_covered:
                            start_idx = max(0, idx - context_radius_before)
                            end_idx = min(len(messages), idx + context_radius_after + 1)
                            context = {
                                'signal': {
                                    'score': 3,
                                    'layers': ['tool_error'],
                                    'keywords': [],
                                    'snippet': str(block.get('content', ''))[:200],
                                },
                                'messages': [
                                    {
                                        'line_num': messages[i]['line_num'],
                                        **summarize_message(messages[i]['record']),
                                    }
                                    for i in range(start_idx, end_idx)
                                ],
                            }
                            packet['failure_contexts'].append(context)

    # Augment with whole-session failure shapes that the per-message walk misses
    sigs = packet['signals_summary']
    packet['failure_contexts'].extend(_thrashing_file_contexts(messages, sigs))
    packet['failure_contexts'].extend(_silent_gap_contexts(messages))

    candidate_count = len(packet['failure_contexts'])

    # Tag every context with its msg_index (for clustering + chronological sort)
    for c in packet['failure_contexts']:
        if 'msg_index' not in c:
            c['msg_index'] = _first_msg_index(c, messages)

    # Cluster near-duplicate signals so 9 firings of the same banned word don't
    # consume 9 of 30 slots
    packet['failure_contexts'] = _cluster_contexts(packet['failure_contexts'])
    clustered_count = len(packet['failure_contexts'])

    # Chronologically split into windows of <=30 contexts; each window becomes
    # a separate packet so long sessions are not silently truncated
    windows = _chronological_windows(packet['failure_contexts'], window_size=30)
    if not windows:
        windows = [[]]

    packet['_truncation_audit'] = {
        'candidate_context_count': candidate_count,
        'clustered_context_count': clustered_count,
        'window_count': len(windows),
    }

    return packet, windows


CLUSTER_RADIUS = 5  # message-index distance for grouping repeat signals


def _first_msg_index(ctx, messages):
    """Resolve ctx -> message index using the line_num of its first message."""
    msgs = ctx.get('messages', [])
    if not msgs:
        return 0
    line_num = msgs[0].get('line_num', 0)
    for idx, m in enumerate(messages):
        if m['line_num'] >= line_num:
            return idx
    return len(messages) - 1


def _cluster_contexts(contexts):
    """Merge near-duplicate signals (same keyword set + within CLUSTER_RADIUS)."""
    if not contexts:
        return contexts
    contexts.sort(key=lambda c: (c.get('msg_index', 0), -c.get('signal', {}).get('score', 0)))
    out = []
    for c in contexts:
        sig = c.get('signal', {})
        kws = tuple(sorted(sig.get('keywords', []) or []))
        layers = tuple(sorted(sig.get('layers', []) or []))
        idx = c.get('msg_index', 0)
        merged = False
        for prev in out[-3:]:
            psig = prev['signal']
            if (
                tuple(sorted(psig.get('keywords', []) or [])) == kws
                and tuple(sorted(psig.get('layers', []) or [])) == layers
                and abs(idx - prev.get('msg_index', 0)) <= CLUSTER_RADIUS
            ):
                prev['cluster_count'] = prev.get('cluster_count', 1) + 1
                psig['score'] = max(psig.get('score', 0), sig.get('score', 0))
                merged = True
                break
        if not merged:
            c['cluster_count'] = c.get('cluster_count', 1)
            out.append(c)
    return out


def _chronological_windows(contexts, window_size=30):
    """Split contexts into chronological windows, each <=window_size."""
    if not contexts:
        return []
    contexts.sort(key=lambda c: c.get('msg_index', 0))
    return [contexts[i:i + window_size] for i in range(0, len(contexts), window_size)]


def _thrashing_file_contexts(messages, signals_summary, top_n=15, min_edits=5):
    """Emit a context per heavily-thrashed file.

    Scoring: edit_count capped at 25 so a single hyper-thrashed file does not
    dominate the chronological sort.
    """
    out = []
    for tf in (signals_summary.get('thrashing_files') or [])[:top_n]:
        if tf.get('edit_count', 0) < min_edits:
            continue
        path = tf.get('file', '')
        anchor_idx = None
        for idx, m in enumerate(messages):
            text = _record_text_repr(m['record'])
            if path and path in text:
                anchor_idx = idx
                break
        if anchor_idx is None:
            continue
        start = max(0, anchor_idx - 3)
        end = min(len(messages), anchor_idx + 3)
        out.append({
            'signal': {
                'score': min(25, tf['edit_count']),
                'layers': ['thrashing_file'],
                'keywords': ['thrash'],
                'snippet': f"File {path} edited {tf['edit_count']} times in this session",
            },
            'msg_index': anchor_idx,
            'thrashing_file': path,
            'edit_count': tf['edit_count'],
            'cluster_count': tf['edit_count'],
            'messages': [
                {'line_num': messages[i]['line_num'], **summarize_message(messages[i]['record'])}
                for i in range(start, end)
            ],
        })
    return out


def _silent_gap_contexts(messages, gap_threshold=10, top_n=15):
    """Emit a context per long stretch of assistant turns without a user reply.

    These map to autonomous-mode runs where the user walked away while the
    agent thrashed - a distinct failure shape that user-correction signals miss.
    """
    out = []
    last_user_idx = -1
    gaps = []
    for idx, m in enumerate(messages):
        rec = m['record']
        if rec.get('type') != 'user':
            continue
        msg = rec.get('message') or {}
        content = msg.get('content', '')
        # skip tool-result echoes (those have list content with tool_result blocks)
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get('type') == 'tool_result' for b in content
        ):
            continue
        if last_user_idx >= 0 and (idx - last_user_idx) > gap_threshold:
            gaps.append((idx - last_user_idx, last_user_idx, idx))
        last_user_idx = idx
    gaps.sort(reverse=True)
    for span, start_idx, end_idx in gaps[:top_n]:
        mid = (start_idx + end_idx) // 2
        ctx_start = max(start_idx + 1, mid - 2)
        ctx_end = min(end_idx, mid + 3)
        if ctx_end <= ctx_start:
            continue
        out.append({
            'signal': {
                'score': min(15, span // 5),
                'layers': ['silent_user_gap'],
                'keywords': ['silent_gap'],
                'snippet': f"User silent across {span} assistant messages while agent worked autonomously",
            },
            'msg_index': mid,
            'gap_span': span,
            'cluster_count': 1,
            'messages': [
                {'line_num': messages[i]['line_num'], **summarize_message(messages[i]['record'])}
                for i in range(ctx_start, ctx_end)
            ],
        })
    return out


def _record_text_repr(record):
    """Best-effort text snapshot of a record for substring search."""
    msg = record.get('message')
    if not isinstance(msg, dict):
        return ''
    content = msg.get('content', '')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict):
                if b.get('type') == 'text':
                    out.append(b.get('text', ''))
                elif b.get('type') == 'tool_use':
                    out.append(json.dumps(b.get('input', {})))
                elif b.get('type') == 'tool_result':
                    out.append(str(b.get('content', ''))[:500])
        return ' '.join(out)
    return ''


def main():
    parser = argparse.ArgumentParser(description='Phase 2: Extract failure packets')
    parser.add_argument('--index', required=True, help='Phase 1 index file')
    parser.add_argument('--transcript-dir', required=True, help='Transcript directory')
    parser.add_argument('--output-dir', default='data/packets/', help='Output directory')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Read index
    entries = []
    with open(args.index, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    print(f"Processing {len(entries)} flagged sessions...")

    extracted = 0
    for i, entry in enumerate(entries):
        if (i + 1) % 50 == 0:
            print(f"  Processing {i+1}/{len(entries)}...", file=sys.stderr)

        result = extract_packet(entry, args.transcript_dir)
        if not result:
            continue
        packet, windows = result
        # Drop sessions with zero candidate contexts after augmentation
        if packet['_truncation_audit']['candidate_context_count'] == 0:
            continue

        sid = entry['session_id']
        n_windows = len(windows)
        for w_idx, window_contexts in enumerate(windows):
            sub = dict(packet)
            sub['failure_contexts'] = window_contexts
            sub['window_index'] = w_idx
            sub['total_windows'] = n_windows
            sub['retained_context_count'] = len(window_contexts)
            suffix = f"__W{w_idx:02d}" if n_windows > 1 else ""
            output_path = os.path.join(args.output_dir, f"{sid}{suffix}.json")
            with open(output_path, 'w') as out:
                json.dump(sub, out, indent=2, default=str)
            extracted += 1
            if w_idx == 0:
                aud = packet['_truncation_audit']
                cand = aud['candidate_context_count']
                clus = aud['clustered_context_count']
                if n_windows > 1 or clus < cand:
                    print(
                        f"  [{sid[:8]}] {cand} candidates -> {clus} clustered -> {n_windows} window(s)",
                        file=sys.stderr,
                    )

    print(f"\nResults:")
    print(f"  Index entries: {len(entries)}")
    print(f"  Packets extracted: {extracted}")
    print(f"  Output directory: {args.output_dir}")


if __name__ == '__main__':
    main()
