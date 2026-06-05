# Case: Agent designed human-facing API when only LLMs use the framework

| Field | Value |
|-------|-------|
| Session | `683b95e9` |
| Date | 2026-04-11 14:22 UTC |
| Model | claude-sonnet-4-6 |
| Context usage | 45230 in / 12840 out / 38100 cache-read / 7200 cache-create |
| Category | user-intent-miss |
| Severity | medium |
| Git branch | main |

## What happened

The user asked the agent to design the API syntax for an LLM-oriented framework. The agent designed two syntax options (`a | b` pipe syntax vs `Sequential(a, b)` class syntax) and reasoned about which would be more intuitive for human developers. The user corrected that humans never write framework code — only LLMs do — making the entire human-ergonomics argument irrelevant.

## Agent quote

> Both syntaxes should exist: `a | b` as the default user-facing API for its expressiveness and Pythonic feel, and `Sequential(a, b)` only in internal implementation. The pipe syntax is more intuitive for developers who are familiar with Unix pipelines...

## User response

> no, human does not write a single line of framework-x code. also put this in readme

## Code paths touched

- `README.md` — API syntax documentation
- `docs/api-design.md` — design specification

## Analysis

The agent imported a standard software engineering assumption: API design should optimize for human developer experience. In this context, the framework's only consumers are LLMs, so the design criteria should be LLM-friendliness (unambiguous syntax, hard to hallucinate incorrectly, minimal state), not human ergonomics. The agent failed to internalize the project's unique constraint despite it being discussed earlier in the conversation. Category: user-intent-miss — the agent completed the task (API design) but optimized for the wrong audience.

## Source

Transcript: `683b95e9-xxxx.jsonl`
Lines: 450-520
