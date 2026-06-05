#!/usr/bin/env python3
"""Phase 1: Scan Claude Code JSONL transcripts and produce a scored failure index.

Usage:
    python extract_signals.py \
        --transcript-dir ~/.claude/projects/<project>/ \
        --since 2026-04-03 \
        --until 2026-04-17 \
        --output data/phase1_index.jsonl
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path


# ============================================================================
# Layer 1: Explicit rejection/correction keywords
# ============================================================================
EXPLICIT_CORRECTION_RE = re.compile(
    r'\b('
    # Direct rejection
    r'no[,.\s!]|nope|wrong|incorrect|that\'s not|not right|not correct|'
    r'false|not true|untrue|inaccurate|'
    # Re-instruction
    r'I said|I meant|I told you|I asked|I wanted|what I want|'
    r'as I (?:said|mentioned|explained|asked)|'
    # Commands to stop/undo
    r'stop|don\'t|do not|shouldn\'t|should not|undo|revert|rollback|'
    r'go back|put it back|change it back|restore|'
    # Retry/redo
    r'try again|redo|start over|do it again|one more time|'
    # Frustration
    r'why did you|you forgot|that broke|doesn\'t work|not working|'
    r'still broken|still wrong|still not|'
    # Clarification signals
    r'I already|let me clarify|to be clear|to clarify|'
    r'what I actually|the point is|I need you to|just do|'
    r'please just|only do|focus on|'
    # Disagreement
    r'I disagree|that\'s unnecessary|don\'t need|not necessary|'
    r'(?:this is |that\'s |is )?unacceptable|not acceptable|'
    r'overkill|overcomplicated|over.?engineer|'
    # Missed context
    r'you missed|you ignored|you skipped|you didn\'t|'
    r'read (?:the|my)|look at|check (?:the|my)|see (?:the|my)'
    r')', re.IGNORECASE
)

# ============================================================================
# Layer 2: Outcome mismatch / state unchanged
# ============================================================================
OUTCOME_MISMATCH_RE = re.compile(
    r'\b('
    r'same error|same issue|same problem|same bug|'
    r'nothing happened|nothing changed|no change|no effect|no difference|'
    r'still (?:the same|happening|failing|broken|not|doesn\'t|won\'t)|'
    r'didn\'t (?:work|help|fix|change|do anything)|'
    r'not fixed|not resolved|not solved|'
    r'error (?:again|persists|remains|continues)|'
    r'back to square one|'
    # Failure declarations — all morphological forms (closing \b prevents
    # matching inside compound words like "failsafe")
    r'fail(?:s|ed|ing|ure|ures)?\b'
    r')', re.IGNORECASE
)

# ============================================================================
# Layer 3: Emotional / frustration signals
# ============================================================================
EMOTIONAL_RE = re.compile(
    r'(?:^|\s)('
    r'ugh|sigh|argh|hmm+|come on|seriously\??|'
    r'oh no|oh god|oh man|oh come on|oh my god|'
    r'what the|for real\??|really\??|'
    r'bruh|dude|yikes|facepalm|'
    r'\.{3,}'
    r')(?:\s|$|[,!?.])', re.IGNORECASE
)

# ============================================================================
# Layer 4: Quality / verbosity / scope feedback
# ============================================================================
QUALITY_RE = re.compile(
    r'\b('
    r'too (?:much|many|verbose|long|complex|complicated|detailed)|'
    r'way too|far too|excessively|'
    r'not (?:enough|detailed|complete|thorough|specific)|'
    r'too (?:simple|short|brief|basic|shallow)|'
    r'missing|incomplete|partial|'
    r'I only (?:asked|wanted|need)|nothing else|'
    r'that\'s all|'
    r'just do it|stop (?:asking|explaining|talking)|less talk|'
    r'don\'t (?:explain|ask|describe)|skip the|'
    r'get to the point|cut to|'
    r'didn\'t ask (?:for|you to)|I never (?:asked|said|wanted)|'
    r'where did .+ come from|why are you|why is there|'
    # Severity / quality escalations (the user is grading) — all morphological forms
    r'severe(?:ly)?|seriously (?:wrong|broken|off|bad|messed)|'
    r'(?:this|that|it) is serious|how serious|seriousness|'
    r'terribl[ey]|awful(?:ly)?|horribl[ey]|bad (?:idea|approach|fix)|'
    r'(?:this is|that is|is) banned|banned (?:word|phrase|pattern|behavior|vocab)|'
    r'(?:strictly|absolutely|completely) (?:wrong|banned|forbidden|prohibited)|'
    r'forbid(?:den|s|ding|de)?|prohibit(?:s|ed|ing)?'
    r')', re.IGNORECASE
)

# ============================================================================
# Layer 5: Polite corrections / hedged pushback / question-as-correction
# ============================================================================
POLITE_CORRECTION_RE = re.compile(
    r'\b('
    r'not quite|close but|almost but|sort of but|kind of but|'
    r'yes but|yeah but|ok but|right but|true but|'
    r'partially|half right|'
    r'did you (?:read|check|see|look|notice|consider|think about|forget|stop|even|notice)|'
    r'are you sure|have you (?:tried|checked|read|looked|considered|forgotten|stopped|even)|'
    r'are you (?:there|alive|still|actually|even|going|doing|making|listening|reading|paying attention|aware|stuck|done|finished|kidding|joking|reading|trying)|'
    r'what are you (?:doing|trying|even|thinking)|'
    r'shouldn\'t (?:it|we|you|this|that)|'
    r'wouldn\'t (?:it|we|this|that) be|'
    r'why (?:would|wouldn\'t|not|can\'t|don\'t) (?:you|we|it)|'
    r'how (?:is|does|would|could) that|'
    r'what about|what if|'
    r'instead of|rather than|'
    r'should be .{1,30} not|'
    r'use .{1,30} instead'
    r')', re.IGNORECASE
)

# ============================================================================
# Layer 6: Redirect / abandon / pivot signals
# ============================================================================
REDIRECT_RE = re.compile(
    r'\b('
    r'forget (?:it|that|this|about)|never mind|nevermind|'
    r'skip (?:it|that|this)|move on|moving on|'
    r'let\'s (?:try|do|go with|switch|move|just)|'
    r'different (?:approach|way|method|strategy)|'
    r'scratch that|disregard|ignore (?:that|this|what)|'
    r'on second thought|actually (?:let\'s|let me|I\'ll)|'
    r'can we just|let me (?:just|do|handle|take over)'
    r')', re.IGNORECASE
)

# ============================================================================
# Layer 7: Structural correction patterns
# ============================================================================
IMPERATIVE_RE = re.compile(
    r'^(use|do|make|change|set|put|move|add|remove|delete|fix|update|replace|'
    r'rename|keep|leave|drop|switch|try|run|read|check|look|write|create|'
    r'call|import|export|return|pass|send|get|fetch|load|save|open|close)\b',
    re.IGNORECASE
)

QUOTE_CORRECT_RE = re.compile(
    r'[`"\'].*[`"\'].*\b(?:should be|not|instead|change to|replace with|use)\b',
    re.IGNORECASE
)

CODE_BLOCK_RE = re.compile(r'```[\s\S]*?```|`[^`]+`')

NEGATION_START_RE = re.compile(
    r'^(no\b|not\b|don\'t|never|stop|wrong|nope|false)', re.IGNORECASE
)

ALL_CAPS_RE = re.compile(r'\b[A-Z]{3,}\b')

EMPHASIS_RE = re.compile(r'[!?]{2,}|!\?|\?!')

ERROR_PASTE_RE = re.compile(
    r'(Traceback|Error:|Exception:|FAILED|error\[|ERR!|panic:|FATAL|Segfault|'
    r'Cannot |Could not |Unable to |Permission denied|Connection refused|'
    r'404|500|502|503|timeout)',
    re.IGNORECASE
)

# ============================================================================
# Layer 8: Implicit correction
# ============================================================================
FILEPATH_RE = re.compile(
    r'[\w/.-]+\.(?:py|ts|tsx|js|jsx|md|json|yaml|yml|toml|cfg|sh)'
)

BARE_PATH_RE = re.compile(r'^\s*(/[\w/.-]+|https?://\S+)\s*$')

ALSO_RE = re.compile(r'^also\b', re.IGNORECASE)

# ============================================================================
# Assistant self-correction signals
# ============================================================================
SELF_CORRECTION_RE = re.compile(
    r'\b('
    r'mistake|my bad|I was wrong|I apologize|I misunderstood|'
    r'let me fix|let me correct|wrong (?:working directory|path|file|approach)|'
    r'I should have|I forgot to'
    r')', re.IGNORECASE
)

# Agent direction reversal
DIRECTION_REVERSAL_RE = re.compile(
    r'\b('
    r'different approach|let me try|instead|'
    r'actually, let me|on second thought|'
    r'that didn\'t work|let me reconsider'
    r')', re.IGNORECASE
)


def extract_text_from_content(content):
    """Extract plain text from message content (string or content block array)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get('type') == 'text':
                    texts.append(block.get('text', ''))
                elif block.get('type') == 'tool_result':
                    # Tool results may contain text
                    tc = block.get('content', '')
                    if isinstance(tc, str):
                        texts.append(tc)
                    elif isinstance(tc, list):
                        for tb in tc:
                            if isinstance(tb, dict) and tb.get('type') == 'text':
                                texts.append(tb.get('text', ''))
        return '\n'.join(texts)
    return ''


def has_tool_use(content):
    """Check if content contains tool_use blocks."""
    if isinstance(content, list):
        return any(
            isinstance(b, dict) and b.get('type') == 'tool_use'
            for b in content
        )
    return False


def extract_tool_targets(content):
    """Extract (tool_name, target) pairs from tool_use blocks."""
    targets = []
    if not isinstance(content, list):
        return targets
    for block in content:
        if isinstance(block, dict) and block.get('type') == 'tool_use':
            name = block.get('name', '')
            inp = block.get('input', {})
            # Extract target based on tool type
            target = ''
            if name in ('Read', 'Edit', 'Write'):
                target = inp.get('file_path', '')
            elif name == 'Bash':
                target = inp.get('command', '')[:100]
            elif name == 'Grep':
                target = inp.get('pattern', '')
            elif name == 'Glob':
                target = inp.get('pattern', '')
            targets.append((name, target))
    return targets


def has_is_error(content):
    """Check if content contains tool_result with is_error: true."""
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get('is_error'):
                    return True
                # Check nested content
                nested = block.get('content', '')
                if isinstance(nested, str) and '<tool_use_error>' in nested:
                    return True
    return False


def get_ngrams(text, n=3):
    """Get set of n-grams from text."""
    words = text.lower().split()
    if len(words) < n:
        return set()
    return {tuple(words[i:i+n]) for i in range(len(words) - n + 1)}


def ngram_overlap(set_a, set_b):
    """Compute Jaccard-like overlap between two n-gram sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    smaller = min(len(set_a), len(set_b))
    return intersection / smaller if smaller > 0 else 0.0


def score_user_message(text, prev_assistant_text_len=0, msg_index=0,
                       user_message_lengths=None, prior_user_ngrams=None,
                       session_has_errors=False):
    """Score a user message across all 8 detection layers. Returns (score, matched_layers, keywords)."""
    score = 0
    matched_layers = []
    keywords = []

    # Skip tool_result-only messages (these are system, not human)
    # The caller should handle this

    # Layer 1: Explicit rejection
    matches = EXPLICIT_CORRECTION_RE.findall(text)
    if matches:
        score += 2 * len(matches)
        matched_layers.append('L1_explicit')
        keywords.extend(matches)

    # Layer 2: Outcome mismatch
    matches = OUTCOME_MISMATCH_RE.findall(text)
    if matches:
        score += 3 * len(matches)
        matched_layers.append('L2_outcome')
        keywords.extend(matches)

    # Layer 3: Emotional
    matches = EMOTIONAL_RE.findall(text)
    if matches:
        score += 1 * len(matches)
        matched_layers.append('L3_emotional')
        keywords.extend(matches)

    # Layer 4: Quality/scope
    matches = QUALITY_RE.findall(text)
    if matches:
        score += 2 * len(matches)
        matched_layers.append('L4_quality')
        keywords.extend(matches)

    # Layer 5: Polite/hedged
    matches = POLITE_CORRECTION_RE.findall(text)
    if matches:
        score += 2 * len(matches)
        matched_layers.append('L5_polite')
        keywords.extend(matches)

    # Layer 6: Redirect/abandon
    matches = REDIRECT_RE.findall(text)
    if matches:
        score += 2 * len(matches)
        matched_layers.append('L6_redirect')
        keywords.extend(matches)

    # Layer 7: Structural patterns
    l7_score = 0

    # Short imperative after long assistant response
    if len(text) < 100 and prev_assistant_text_len > 500:
        if IMPERATIVE_RE.search(text):
            l7_score += 2
            matched_layers.append('L7_imperative')

    # Quote-and-correct
    if QUOTE_CORRECT_RE.search(text):
        l7_score += 2
        matched_layers.append('L7_quote_correct')

    # Code block provided (user takeover signal)
    if CODE_BLOCK_RE.search(text):
        if session_has_errors:
            l7_score += 2
            matched_layers.append('L7_code_block')

    # Negation start
    if NEGATION_START_RE.search(text):
        l7_score += 2
        matched_layers.append('L7_negation_start')

    # ALL CAPS frustration
    caps_matches = ALL_CAPS_RE.findall(text)
    # Filter common acronyms
    real_caps = [m for m in caps_matches if m not in (
        'API', 'URL', 'HTML', 'CSS', 'JSON', 'SQL', 'HTTP', 'HTTPS',
        'SSH', 'CLI', 'GUI', 'SDK', 'IDE', 'EOF', 'NULL', 'TRUE', 'FALSE',
        'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS',
        'README', 'TODO', 'FIXME', 'NOTE', 'HACK', 'XXX',
        'NPM', 'PIP', 'GIT', 'ENV', 'AWS', 'GCP', 'LLM', 'LLMs',
        'YAML', 'TOML', 'CSV', 'PDF', 'PNG', 'JPG', 'SVG',
        'UTF', 'ASCII', 'CORS', 'CSRF', 'JWT', 'OAuth', 'RBAC',
    )]
    if real_caps:
        l7_score += 1
        matched_layers.append('L7_caps')

    # Emphasis punctuation
    if EMPHASIS_RE.search(text):
        l7_score += 1
        matched_layers.append('L7_emphasis')

    # Error paste
    if ERROR_PASTE_RE.search(text):
        l7_score += 2
        matched_layers.append('L7_error_paste')

    # Short terse message
    if len(text) < 30 and msg_index > 5:
        l7_score += 1
        matched_layers.append('L7_terse')

    score += l7_score

    # Layer 8: Implicit correction
    l8_score = 0

    if BARE_PATH_RE.search(text):
        l8_score += 1
        matched_layers.append('L8_bare_path')

    if ALSO_RE.search(text):
        l8_score += 1
        matched_layers.append('L8_also')

    # Re-explanation via n-gram overlap
    if prior_user_ngrams:
        current_ngrams = get_ngrams(text)
        if current_ngrams:
            for prev_idx, prev_ngrams in prior_user_ngrams.items():
                if msg_index - prev_idx > 3:
                    overlap = ngram_overlap(current_ngrams, prev_ngrams)
                    if overlap > 0.30:
                        l8_score += 1
                        matched_layers.append('L8_reexplanation')
                        break

    score += l8_score

    # Escalating frustration: message shorter than previous user messages
    if user_message_lengths and len(user_message_lengths) >= 2:
        if all(len(text) < prev_len for prev_len in user_message_lengths[-2:]):
            if score > 0:  # Only if there's already some correction signal
                score += 2
                matched_layers.append('L_escalating')

    return score, matched_layers, keywords


def process_session(filepath, since_dt=None, until_dt=None):
    """Process a single JSONL transcript file and extract signals."""
    session_id = Path(filepath).stem
    is_subagent = '/subagents/' in str(filepath)

    # Session-level accumulators
    signals = {
        'tool_errors': 0,
        'user_interruptions': 0,
        'permission_blocks': 0,
        'file_too_large': 0,
        'file_not_found': 0,
        'edit_failures': 0,
        'self_corrections': 0,
        'user_corrections': [],  # list of (msg_index, score, layers, keywords, text_snippet)
        'correction_loops': 0,
        'repeated_corrections': 0,
        'escalating_frustration': 0,
        'direction_reversals': 0,
        'thrashing_files': [],
        'user_takeovers': 0,
        'abandoned_approaches': 0,
        'silent_user_gaps': 0,
        'compaction_events': 0,
    }

    metadata = {
        'session_id': session_id,
        'file_path': str(filepath),
        'is_subagent': is_subagent,
        'model': None,
        'timestamp': None,
        'slug': None,
        'git_branch': None,
        'total_input_tokens': 0,
        'total_output_tokens': 0,
        'total_cache_read_tokens': 0,
        'total_cache_creation_tokens': 0,
        'message_count': 0,
        'human_message_count': 0,
        'first_user_prompt': '',
    }

    # Sliding window state
    files_touched = Counter()
    tool_targets = Counter()
    user_message_lengths = []
    prior_user_ngrams = {}
    session_has_errors = False
    msg_index = 0
    last_user_msg_index = -1
    prev_assistant_text_len = 0
    consecutive_assistant_msgs = 0
    recent_corrections = deque(maxlen=15)
    recent_correction_keywords = deque(maxlen=15)
    approach_tool_count = 0

    first_timestamp = None

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line_num, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                rec_type = record.get('type', '')

                # Extract timestamp for date filtering
                ts = record.get('timestamp')
                if ts and first_timestamp is None:
                    first_timestamp = ts
                    try:
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        if since_dt and dt < since_dt:
                            return None  # Too old
                        if until_dt and dt > until_dt:
                            return None  # Too new
                        metadata['timestamp'] = ts
                    except (ValueError, AttributeError):
                        pass

                # Extract session metadata
                if record.get('slug') and not metadata['slug']:
                    metadata['slug'] = record['slug']
                if record.get('gitBranch') and not metadata['git_branch']:
                    metadata['git_branch'] = record['gitBranch']

                # Check for compaction
                if rec_type == 'system':
                    sys_text = str(record.get('message', ''))
                    if 'compact' in sys_text.lower() or 'compress' in sys_text.lower():
                        signals['compaction_events'] += 1

                # Process user messages
                if rec_type == 'user':
                    msg = record.get('message', {})
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get('role', '')
                    content = msg.get('content', '')

                    if role == 'user':
                        metadata['message_count'] += 1

                        # Check if this is a human message (text) vs tool_result
                        text = extract_text_from_content(content)

                        # Check for tool_result with is_error
                        if has_is_error(content if isinstance(content, list) else []):
                            signals['tool_errors'] += 1
                            session_has_errors = True

                            # Check specific error types
                            error_text = text.lower()
                            if 'requires approval' in error_text or 'permission' in error_text:
                                signals['permission_blocks'] += 1
                            if 'exceeds maximum allowed tokens' in error_text:
                                signals['file_too_large'] += 1
                            if 'enoent' in error_text or 'no such file' in error_text:
                                signals['file_not_found'] += 1
                            if 'old_string' in error_text or 'edit failed' in error_text or 'not unique' in error_text:
                                signals['edit_failures'] += 1

                        # Check for user interruption
                        if '[Request interrupted by user]' in text:
                            signals['user_interruptions'] += 1

                        # Determine if this is a human-authored message
                        is_human_text = False
                        if isinstance(content, str) and content.strip():
                            is_human_text = True
                        elif isinstance(content, list):
                            # Has at least one text block that's not a tool_result
                            for block in content:
                                if isinstance(block, dict):
                                    if block.get('type') == 'text' and block.get('text', '').strip():
                                        is_human_text = True
                                        break

                        if is_human_text and text.strip():
                            metadata['human_message_count'] += 1

                            if not metadata['first_user_prompt']:
                                metadata['first_user_prompt'] = text[:500]

                            # Score the user message
                            correction_score, matched_layers, keywords = score_user_message(
                                text,
                                prev_assistant_text_len=prev_assistant_text_len,
                                msg_index=msg_index,
                                user_message_lengths=user_message_lengths,
                                prior_user_ngrams=prior_user_ngrams,
                                session_has_errors=session_has_errors,
                            )

                            if correction_score >= 1:
                                snippet = text[:200].replace('\n', ' ')
                                signals['user_corrections'].append({
                                    'msg_index': msg_index,
                                    'line_num': line_num,
                                    'score': correction_score,
                                    'layers': matched_layers,
                                    'keywords': keywords[:10],
                                    'snippet': snippet,
                                })
                                recent_corrections.append(msg_index)
                                recent_correction_keywords.append(set(kw.lower() for kw in keywords))

                                # Check for correction loop
                                if len(recent_correction_keywords) >= 2:
                                    current_kws = recent_correction_keywords[-1]
                                    for prev_kws in list(recent_correction_keywords)[:-1]:
                                        if current_kws & prev_kws:  # Any overlap
                                            signals['correction_loops'] += 1
                                            break

                            # Track for conversational patterns
                            user_message_lengths.append(len(text))
                            prior_user_ngrams[msg_index] = get_ngrams(text)

                            # Check silent user gap
                            if consecutive_assistant_msgs >= 5:
                                signals['silent_user_gaps'] += 1

                            consecutive_assistant_msgs = 0
                            last_user_msg_index = msg_index

                        msg_index += 1

                # Process assistant messages
                elif rec_type == 'assistant':
                    msg = record.get('message', {})
                    if not isinstance(msg, dict):
                        continue

                    metadata['message_count'] += 1
                    consecutive_assistant_msgs += 1

                    # Extract model
                    if msg.get('model') and not metadata['model']:
                        metadata['model'] = msg['model']

                    # Extract token usage
                    usage = msg.get('usage', {})
                    if usage:
                        metadata['total_input_tokens'] += usage.get('input_tokens', 0)
                        metadata['total_output_tokens'] += usage.get('output_tokens', 0)
                        metadata['total_cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)
                        metadata['total_cache_creation_tokens'] += usage.get('cache_creation_input_tokens', 0)

                    content = msg.get('content', '')
                    text = extract_text_from_content(content)

                    prev_assistant_text_len = len(text)

                    # Check self-corrections
                    if SELF_CORRECTION_RE.search(text):
                        signals['self_corrections'] += 1

                    # Check direction reversals
                    if DIRECTION_REVERSAL_RE.search(text) and approach_tool_count >= 3:
                        signals['direction_reversals'] += 1
                        approach_tool_count = 0

                    # Track tool calls for thrashing
                    if has_tool_use(content if isinstance(content, list) else []):
                        approach_tool_count += 1
                        targets = extract_tool_targets(
                            content if isinstance(content, list) else []
                        )
                        for tool_name, target in targets:
                            if tool_name in ('Edit', 'Write') and target:
                                files_touched[target] += 1
                            tool_targets[(tool_name, target)] += 1

                    msg_index += 1

    except Exception as e:
        print(f"  Error processing {filepath}: {e}", file=sys.stderr)
        return None

    if first_timestamp is None:
        return None

    # Post-processing: conversational pattern signals

    # Repeated corrections in window
    correction_indices = [c['msg_index'] for c in signals['user_corrections']]
    for i in range(len(correction_indices)):
        window_count = sum(
            1 for j in range(i+1, len(correction_indices))
            if correction_indices[j] - correction_indices[i] <= 15
        )
        if window_count >= 1:  # 2+ corrections in 15-message window
            signals['repeated_corrections'] += 1
            break  # Count once per session

    # Thrashing detection
    for fpath, count in files_touched.items():
        if count >= 3:
            signals['thrashing_files'].append({'file': fpath, 'edit_count': count})

    # Compute total score
    total_score = 0
    total_score += signals['tool_errors'] * 3
    total_score += signals['user_interruptions'] * 5
    total_score += signals['permission_blocks'] * 1
    total_score += signals['file_too_large'] * 2
    total_score += signals['file_not_found'] * 1
    total_score += signals['edit_failures'] * 2
    total_score += signals['self_corrections'] * 2
    total_score += sum(c['score'] for c in signals['user_corrections'])
    total_score += signals['correction_loops'] * 8
    total_score += signals['repeated_corrections'] * 6
    total_score += signals['direction_reversals'] * 4
    total_score += len(signals['thrashing_files']) * 4
    total_score += signals['silent_user_gaps'] * 2
    total_score += signals['compaction_events'] * 1

    # Serialize user_corrections for output
    result = {
        **metadata,
        'signals': {
            'tool_errors': signals['tool_errors'],
            'user_interruptions': signals['user_interruptions'],
            'permission_blocks': signals['permission_blocks'],
            'file_too_large': signals['file_too_large'],
            'file_not_found': signals['file_not_found'],
            'edit_failures': signals['edit_failures'],
            'self_corrections': signals['self_corrections'],
            'user_correction_count': len(signals['user_corrections']),
            'user_corrections': signals['user_corrections'],
            'correction_loops': signals['correction_loops'],
            'repeated_corrections': signals['repeated_corrections'],
            'escalating_frustration': signals['escalating_frustration'],
            'direction_reversals': signals['direction_reversals'],
            'thrashing_files': signals['thrashing_files'],
            'user_takeovers': signals['user_takeovers'],
            'abandoned_approaches': signals['abandoned_approaches'],
            'silent_user_gaps': signals['silent_user_gaps'],
            'compaction_events': signals['compaction_events'],
        },
        'total_score': total_score,
    }

    return result


def find_jsonl_files(transcript_dir):
    """Find all .jsonl files recursively, including subagent directories."""
    transcript_dir = Path(transcript_dir)
    files = []
    for p in transcript_dir.rglob('*.jsonl'):
        files.append(p)
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def main():
    parser = argparse.ArgumentParser(description='Phase 1: Extract failure signals from transcripts')
    parser.add_argument('--transcript-dir', required=True, help='Directory containing JSONL files')
    parser.add_argument('--since', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--until', help='End date (YYYY-MM-DD)')
    parser.add_argument('--output', default='data/phase1_index.jsonl', help='Output index file')
    parser.add_argument('--min-score', type=int, default=1, help='Minimum score to include in output')
    args = parser.parse_args()

    since_dt = None
    until_dt = None
    if args.since:
        since_dt = datetime.strptime(args.since, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    if args.until:
        until_dt = datetime.strptime(args.until, '%Y-%m-%d').replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )

    print(f"Scanning {args.transcript_dir} for JSONL files...")
    files = find_jsonl_files(args.transcript_dir)
    print(f"Found {len(files)} JSONL files")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)

    total = 0
    flagged = 0
    skipped = 0
    errors = 0

    with open(args.output, 'w') as out:
        for i, filepath in enumerate(files):
            if (i + 1) % 100 == 0:
                print(f"  Processing {i+1}/{len(files)}...", file=sys.stderr)

            result = process_session(filepath, since_dt, until_dt)

            if result is None:
                skipped += 1
                continue

            total += 1

            if result['total_score'] >= args.min_score:
                flagged += 1
                out.write(json.dumps(result, default=str) + '\n')

    print(f"\nResults:")
    print(f"  Total files scanned: {len(files)}")
    print(f"  Sessions in date range: {total}")
    print(f"  Skipped (out of range or error): {skipped}")
    print(f"  Flagged (score >= {args.min_score}): {flagged}")
    print(f"  Output: {args.output}")


if __name__ == '__main__':
    main()
