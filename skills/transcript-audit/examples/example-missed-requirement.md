# Case: Agent missed a core goal discussed in conversation

| Field | Value |
|-------|-------|
| Session | `683b95e9` |
| Date | 2026-04-11 16:45 UTC |
| Model | claude-sonnet-4-6 |
| Context usage | 52600 in / 15300 out / 43200 cache-read / 9400 cache-create |
| Category | user-intent-miss |
| Severity | medium |
| Git branch | main |

## What happened

The user asked the agent to write documentation listing the project's core goals. The agent wrote two goals: (1) agents can implement orchestration patterns easily, (2) the orchestration system can self-evolve. The user then added a third goal that had been discussed in conversation but wasn't elevated to goal status by the agent: the framework's syntax should be LLM-friendly so that LLMs are unlikely to make mistakes even given their tendency to hallucinate.

## Agent quote

> Here's the updated README with the two core goals:
> 1. Agents can implement orchestration patterns easily using the DSL
> 2. The agent orchestration system can self-evolve its own patterns

## User response

> Then, add a third goal: 3. The syntax and constructs of framework-x should be very friendly to LLMs and LLMs are hard to make mistakes in writing framework-x code even with their nature of hallucination and under-reasoning.

## Code paths touched

- `README.md` — project documentation with goals section

## Analysis

The agent captured the explicit goals but missed an implicit one that had been discussed earlier in the conversation. The LLM-friendliness requirement was treated as a design principle rather than a primary success metric. This is a context-attention failure: the agent processed the explicit instruction ("write the goals") but didn't scan the conversation history for discussed-but-not-formalized requirements. In long conversations, context decay means earlier discussion topics lose salience even when they're highly relevant. The fix is explicit requirement gathering: before writing a goals section, the agent should have scanned the conversation for all discussed objectives and confirmed the list with the user.

## Source

Transcript: `683b95e9-xxxx.jsonl`
Lines: 520-560
