#!/usr/bin/env python3
"""Phase 4: Synthesize case files into a comprehensive report.

Usage:
    python synthesize_report.py \
        --cases-dir cases/ \
        --index data/phase1_index.jsonl \
        --output REPORT.md
"""

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def parse_case_file(filepath):
    """Parse a case markdown file and extract structured fields."""
    with open(filepath, 'r') as f:
        content = f.read()

    case = {
        'file_path': str(filepath),
        'title': '',
        'session_id': '',
        'date': '',
        'model': '',
        'context_usage': '',
        'category': '',
        'severity': '',
        'git_branch': '',
        'what_happened': '',
        'agent_quote': '',
        'user_response': '',
        'code_paths': [],
        'analysis': '',
    }

    # Extract title
    title_match = re.search(r'^# Case: (.+)$', content, re.MULTILINE)
    if title_match:
        case['title'] = title_match.group(1).strip()

    # Extract table fields
    table_patterns = {
        'session_id': r'\| Session \| `(.+?)`',
        'date': r'\| Date \| (.+?) \|',
        'model': r'\| Model \| (.+?) \|',
        'context_usage': r'\| Context usage \| (.+?) \|',
        'category': r'\| Category \| (.+?) \|',
        'severity': r'\| Severity \| (.+?) \|',
        'git_branch': r'\| Git branch \| (.+?) \|',
    }
    for key, pattern in table_patterns.items():
        match = re.search(pattern, content)
        if match:
            case[key] = match.group(1).strip()

    # Extract sections
    sections = {
        'what_happened': r'## What happened\s*\n(.*?)(?=\n## )',
        'agent_quote': r'## Agent quote\s*\n(.*?)(?=\n## )',
        'user_response': r'## User response.*?\n(.*?)(?=\n## )',
        'analysis': r'## Analysis\s*\n(.*?)(?=\n## |$)',
    }
    for key, pattern in sections.items():
        match = re.search(pattern, content, re.DOTALL)
        if match:
            case[key] = match.group(1).strip()

    # Extract code paths
    code_paths = re.findall(r'^- `(.+?)`', content, re.MULTILINE)
    case['code_paths'] = code_paths

    return case


def parse_index_entry(entry):
    """Extract key stats from a phase1 index entry."""
    return {
        'session_id': entry.get('session_id', ''),
        'model': entry.get('model', ''),
        'total_score': entry.get('total_score', 0),
        'message_count': entry.get('message_count', 0),
        'human_message_count': entry.get('human_message_count', 0),
        'input_tokens': entry.get('total_input_tokens', 0),
        'output_tokens': entry.get('total_output_tokens', 0),
        'timestamp': entry.get('timestamp', ''),
    }


def main():
    parser = argparse.ArgumentParser(description='Phase 4: Synthesize report')
    parser.add_argument('--cases-dir', required=True, help='Directory containing case files')
    parser.add_argument('--index', help='Phase 1 index file (for overall stats)')
    parser.add_argument('--output', default='REPORT.md', help='Output report file')
    args = parser.parse_args()

    # Collect all case files
    cases_dir = Path(args.cases_dir)
    case_files = sorted(cases_dir.rglob('*.md'))
    cases = [parse_case_file(f) for f in case_files]

    print(f"Found {len(cases)} case files")

    # Load index for overall stats
    index_entries = []
    if args.index and os.path.exists(args.index):
        with open(args.index, 'r') as f:
            for line in f:
                if line.strip():
                    index_entries.append(json.loads(line))
        print(f"Loaded {len(index_entries)} index entries")

    # Compute statistics
    total_sessions = len(index_entries)
    flagged_sessions = sum(1 for e in index_entries if e.get('total_score', 0) >= 1)
    total_cases = len(cases)

    # Category breakdown
    category_counts = Counter(c['category'] for c in cases if c['category'])
    severity_counts = Counter(c['severity'] for c in cases if c['severity'])

    # Model breakdown — normalize model strings
    def normalize_model(m):
        if not m:
            return ''
        m = m.strip('`').strip()
        # Strip synthetic markers and parenthetical notes
        m = re.sub(r'\s*\(synthetic\)', '', m)
        m = re.sub(r'\s*\(initial\).*', '', m)
        m = m.strip()
        if m == '<synthetic>' or not m:
            return ''
        return m

    model_counts = Counter()
    for c in cases:
        nm = normalize_model(c.get('model', ''))
        if nm:
            model_counts[nm] += 1
    model_total = Counter()
    for e in index_entries:
        nm = normalize_model(e.get('model', ''))
        if nm:
            model_total[nm] += 1

    # Temporal trends
    date_counts = Counter()
    for c in cases:
        date_str = c['date']
        if date_str:
            try:
                d = date_str.split(' ')[0]  # YYYY-MM-DD
                date_counts[d] += 1
            except (ValueError, IndexError):
                pass

    # Token usage patterns
    token_stats = {
        'high_context_failures': 0,  # cases from sessions with >100k input tokens
        'low_context_failures': 0,
    }
    session_token_map = {}
    for e in index_entries:
        sid = e.get('session_id', '')
        session_token_map[sid] = e.get('total_input_tokens', 0)

    for c in cases:
        sid = c['session_id']
        tokens = session_token_map.get(sid, 0)
        if tokens > 100000:
            token_stats['high_context_failures'] += 1
        else:
            token_stats['low_context_failures'] += 1

    # Top failure patterns (group by category + common keywords in analysis)
    category_examples = defaultdict(list)
    for c in cases:
        cat = c['category']
        if cat:
            category_examples[cat].append(c)

    # Generate report
    report = []
    report.append(f"# Claude Code Failure Analysis Report")
    report.append(f"")
    report.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    timestamps = sorted(e['timestamp'][:10] for e in index_entries if e.get('timestamp'))
    if timestamps:
        report.append(f"**Date range**: {timestamps[0]} to {timestamps[-1]}")
    report.append(f"")

    # Summary
    report.append(f"## Summary Statistics")
    report.append(f"")
    report.append(f"| Metric | Value |")
    report.append(f"|--------|-------|")
    report.append(f"| Sessions analyzed | {total_sessions} |")
    report.append(f"| Sessions flagged (score >= 1) | {flagged_sessions} |")
    report.append(f"| True positive cases | {total_cases} |")
    report.append(f"| Failure rate | {total_cases / max(total_sessions, 1) * 100:.1f}% |")
    report.append(f"")

    # Category breakdown
    report.append(f"## Failures by Category")
    report.append(f"")
    report.append(f"| Category | Count | % of total |")
    report.append(f"|----------|-------|-----------|")
    for cat, count in category_counts.most_common():
        pct = count / max(total_cases, 1) * 100
        report.append(f"| {cat} | {count} | {pct:.1f}% |")
    report.append(f"")

    # Severity breakdown
    report.append(f"## Failures by Severity")
    report.append(f"")
    report.append(f"| Severity | Count | % of total |")
    report.append(f"|----------|-------|-----------|")
    for sev, count in severity_counts.most_common():
        pct = count / max(total_cases, 1) * 100
        report.append(f"| {sev} | {count} | {pct:.1f}% |")
    report.append(f"")

    # Model breakdown
    report.append(f"## Failures by Model")
    report.append(f"")
    report.append(f"| Model | Failures | Total sessions | Failure rate |")
    report.append(f"|-------|----------|----------------|-------------|")
    for model in sorted(set(list(model_counts.keys()) + list(model_total.keys()))):
        failures = model_counts.get(model, 0)
        total = model_total.get(model, 0)
        rate = failures / max(total, 1) * 100
        report.append(f"| {model} | {failures} | {total} | {rate:.1f}% |")
    report.append(f"")

    # Context usage correlation
    report.append(f"## Context Usage Patterns")
    report.append(f"")
    report.append(f"| Context level | Failure count |")
    report.append(f"|---------------|--------------|")
    report.append(f"| High (>100k input tokens) | {token_stats['high_context_failures']} |")
    report.append(f"| Normal (<=100k input tokens) | {token_stats['low_context_failures']} |")
    report.append(f"")

    # Temporal trends
    report.append(f"## Temporal Trends")
    report.append(f"")
    report.append(f"| Date | Failures |")
    report.append(f"|------|---------|")
    for date in sorted(date_counts.keys()):
        report.append(f"| {date} | {date_counts[date]} |")
    report.append(f"")

    # Top failure patterns by category
    report.append(f"## Top Failure Patterns")
    report.append(f"")
    for cat, examples in sorted(category_examples.items(), key=lambda x: -len(x[1])):
        report.append(f"### {cat} ({len(examples)} cases)")
        report.append(f"")
        # Show top 3 examples
        for ex in examples[:3]:
            rel_path = os.path.relpath(ex['file_path'], os.path.dirname(args.output))
            report.append(f"- [{ex['title']}]({rel_path})")
            if ex['what_happened']:
                report.append(f"  {ex['what_happened'][:200]}")
        if len(examples) > 3:
            report.append(f"- ... and {len(examples) - 3} more")
        report.append(f"")

    # Full case index
    report.append(f"## Full Case Index")
    report.append(f"")
    report.append(f"| Date | Case | Category | Severity | Model |")
    report.append(f"|------|------|----------|----------|-------|")
    for c in sorted(cases, key=lambda x: x['date']):
        rel_path = os.path.relpath(c['file_path'], os.path.dirname(args.output))
        title_link = f"[{c['title'][:60]}]({rel_path})"
        report.append(f"| {c['date'][:10]} | {title_link} | {c['category']} | {c['severity']} | {c['model'][:20] if c['model'] else ''} |")
    report.append(f"")

    # Write report
    with open(args.output, 'w') as f:
        f.write('\n'.join(report))

    print(f"Report written to {args.output}")
    print(f"Total cases: {total_cases}")
    print(f"Categories: {dict(category_counts)}")
    print(f"Severities: {dict(severity_counts)}")


if __name__ == '__main__':
    main()
