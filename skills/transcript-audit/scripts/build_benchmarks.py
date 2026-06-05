#!/usr/bin/env python3
"""Phase 5: Derive reproducible benchmarks from case files.

Usage:
    python build_benchmarks.py \
        --cases-dir cases/ \
        --output-dir benchmarks/
"""

import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path


def parse_case_file(filepath):
    """Parse a case markdown file."""
    with open(filepath, 'r') as f:
        content = f.read()

    case = {'file_path': str(filepath), 'content': content}

    title_match = re.search(r'^# Case: (.+)$', content, re.MULTILINE)
    if title_match:
        case['title'] = title_match.group(1).strip()

    for key, pattern in {
        'category': r'\| Category \| (.+?) \|',
        'severity': r'\| Severity \| (.+?) \|',
    }.items():
        match = re.search(pattern, content)
        if match:
            case[key] = match.group(1).strip()

    # Extract analysis
    analysis_match = re.search(r'## Analysis\s*\n(.*?)(?=\n## |$)', content, re.DOTALL)
    if analysis_match:
        case['analysis'] = analysis_match.group(1).strip()

    # Extract agent quote
    quote_match = re.search(r'## Agent quote\s*\n(.*?)(?=\n## )', content, re.DOTALL)
    if quote_match:
        case['agent_quote'] = quote_match.group(1).strip()

    # Extract what happened
    what_match = re.search(r'## What happened\s*\n(.*?)(?=\n## )', content, re.DOTALL)
    if what_match:
        case['what_happened'] = what_match.group(1).strip()

    return case


def cluster_cases(cases):
    """Group cases by category, then identify subclusters by similarity."""
    clusters = defaultdict(list)
    for case in cases:
        cat = case.get('category', 'unknown')
        clusters[cat].append(case)
    return clusters


def generate_benchmark_slug(title):
    """Convert a case title to a filename-safe slug."""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    return slug[:60]


def write_benchmark(benchmark, output_path):
    """Write a benchmark file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    lines = []
    lines.append(f"# Benchmark: {benchmark['name']}")
    lines.append(f"")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Category | {benchmark['category']} |")
    lines.append(f"| Derived from | {benchmark['derived_from']} |")
    lines.append(f"| Failure mode | {benchmark['failure_mode']} |")
    lines.append(f"| Reproduction rate | {benchmark.get('reproduction_rate', 'unknown')} |")
    lines.append(f"")
    lines.append(f"## Setup")
    lines.append(f"")
    lines.append(benchmark.get('setup', 'No special setup required.'))
    lines.append(f"")
    lines.append(f"## Prompt")
    lines.append(f"")
    lines.append(f"> {benchmark.get('prompt', 'TBD — extract from case context')}")
    lines.append(f"")
    lines.append(f"## System context")
    lines.append(f"")
    lines.append(benchmark.get('system_context', 'Default Claude Code configuration.'))
    lines.append(f"")
    lines.append(f"## Expected behavior")
    lines.append(f"")
    lines.append(benchmark.get('expected_behavior', 'TBD'))
    lines.append(f"")
    lines.append(f"## Observed failure")
    lines.append(f"")
    lines.append(benchmark.get('observed_failure', 'TBD'))
    lines.append(f"")
    lines.append(f"## Evaluation criteria")
    lines.append(f"")
    for criterion in benchmark.get('evaluation_criteria', ['TBD']):
        lines.append(f"- [ ] {criterion}")
    lines.append(f"")
    lines.append(f"## Failure signature")
    lines.append(f"")
    lines.append(f"`{benchmark.get('failure_signature', 'TBD')}`")
    lines.append(f"")

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description='Phase 5: Build benchmarks from cases')
    parser.add_argument('--cases-dir', required=True, help='Directory containing case files')
    parser.add_argument('--output-dir', default='benchmarks/', help='Output directory')
    args = parser.parse_args()

    # Collect cases
    cases_dir = Path(args.cases_dir)
    case_files = sorted(cases_dir.rglob('*.md'))
    cases = [parse_case_file(f) for f in case_files]
    print(f"Found {len(cases)} case files")

    # Cluster by category
    clusters = cluster_cases(cases)

    # For each category with 3+ cases, create benchmark(s)
    benchmark_count = 0
    for category, cluster_cases_list in sorted(clusters.items()):
        if len(cluster_cases_list) < 3:
            print(f"  Skipping {category} ({len(cluster_cases_list)} cases, need 3+)")
            continue

        print(f"  Processing {category} ({len(cluster_cases_list)} cases)")

        # Create a representative benchmark from the cluster
        # Use the highest-severity case as the primary example
        sorted_cases = sorted(
            cluster_cases_list,
            key=lambda c: {'high': 3, 'medium': 2, 'low': 1}.get(c.get('severity', ''), 0),
            reverse=True,
        )

        primary = sorted_cases[0]
        derived_from = ', '.join(
            f"`{os.path.basename(c['file_path'])}`"
            for c in sorted_cases[:5]
        )

        benchmark = {
            'name': f"{category} — {primary.get('title', 'unnamed')}",
            'category': category,
            'derived_from': derived_from,
            'failure_mode': primary.get('what_happened', primary.get('title', 'TBD'))[:200],
            'reproduction_rate': 'often' if len(cluster_cases_list) >= 5 else 'sometimes',
            'setup': 'No special setup required.',
            'prompt': 'Extract minimal reproduction prompt from the cases listed above.',
            'system_context': 'Default Claude Code configuration.',
            'expected_behavior': 'Agent should handle the task correctly without the identified failure.',
            'observed_failure': primary.get('agent_quote', 'See derived case files.'),
            'evaluation_criteria': [
                f"Agent does not exhibit {category} behavior",
                'Agent satisfies user intent on first attempt',
                'No user correction required',
            ],
            'failure_signature': f'"is_error": true' if category == 'tool-error' else f'User correction matching {category} pattern',
        }

        slug = generate_benchmark_slug(primary.get('title', category))
        output_path = os.path.join(args.output_dir, 'categories', category, f'{slug}.md')
        write_benchmark(benchmark, output_path)
        benchmark_count += 1

        # If cluster is large (10+), create additional benchmarks for subclusters
        if len(cluster_cases_list) >= 10:
            # Group by severity
            for sev in ['high', 'medium']:
                sev_cases = [c for c in cluster_cases_list if c.get('severity') == sev]
                if len(sev_cases) >= 3:
                    sub_primary = sev_cases[0]
                    sub_benchmark = {
                        **benchmark,
                        'name': f"{category}/{sev} — {sub_primary.get('title', 'unnamed')}",
                        'derived_from': ', '.join(
                            f"`{os.path.basename(c['file_path'])}`"
                            for c in sev_cases[:3]
                        ),
                        'failure_mode': sub_primary.get('what_happened', 'TBD')[:200],
                    }
                    sub_slug = generate_benchmark_slug(f"{sev}-{sub_primary.get('title', category)}")
                    sub_path = os.path.join(args.output_dir, 'categories', category, f'{sub_slug}.md')
                    write_benchmark(sub_benchmark, sub_path)
                    benchmark_count += 1

    print(f"\nBenchmarks created: {benchmark_count}")
    print(f"Output directory: {args.output_dir}")


if __name__ == '__main__':
    main()
