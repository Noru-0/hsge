# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

HSGE (Hierarchical Skill-Graph Exploration) is a research scaffold for web agents
that discover **reusable, verified skills** during exploration and **compose** them
into long-horizon tasks. The default configuration runs entirely on **deterministic
mock backends** — no API keys, GPU, or live browser required. Real backends
(LLM, embedder, WebArena browser) are subclass swaps, not rewrites.

Run everything from the repo root (the directory containing `hsge/`).

## Rules

- [rules/behavior.md](rules/behavior.md) — general coding behavior guidelines
- [rules/commands.md](rules/commands.md) — how to run things (incl. conda env)
- [rules/architecture.md](rules/architecture.md) — module map & data flow
- [rules/conventions.md](rules/conventions.md) — repo conventions
- [rules/docs.md](rules/docs.md) — pointers to docs/
