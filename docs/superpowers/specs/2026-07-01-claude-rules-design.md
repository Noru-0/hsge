# Design: `.claude/rules/` folder

Date: 2026-07-01

## Purpose

Split the existing `.claude/CLAUDE.md` into a short root file plus a set of
topic-scoped rule files under `.claude/rules/`, and add a general coding
behavior guideline that isn't specific to HSGE. `CLAUDE.md` stays the
auto-loaded entry point (Claude Code only auto-loads `CLAUDE.md`, not files
under `rules/`), so it must explicitly link to every file in `rules/`.

## File layout

```
.claude/
  CLAUDE.md          rewritten: short "what this is" + links to rules/
  rules/
    behavior.md       general coding behavior guidelines (not HSGE-specific)
    commands.md        how to run things, incl. conda env activation
    architecture.md   two-level graph, discovery pipeline, backends, WebArena runtime
    conventions.md    public API, determinism, requirements.txt policy
    docs.md           pointers to docs/*.md
```

## Content mapping

- **`rules/behavior.md`** — the 4-principle guideline supplied by the user
  verbatim (Think Before Coding, Simplicity First, Surgical Changes,
  Goal-Driven Execution). General-purpose, not HSGE-specific, included as-is.
- **`rules/commands.md`** — current CLAUDE.md `## Commands` section, copied
  as-is, plus one addition: the project runs in a conda environment named
  `go-browse`. Add `conda activate go-browse` as the first line of the
  command block, before `pip install numpy`.
- **`rules/architecture.md`** — current CLAUDE.md `## Architecture` section
  copied as-is (includes the WebArena runtime subsection — not split further,
  per user choice).
- **`rules/conventions.md`** — current CLAUDE.md `## Conventions` section
  copied as-is.
- **`rules/docs.md`** — current CLAUDE.md `## Docs` section copied as-is.

No content is reworded or reinterpreted during the split — only relocated,
to avoid introducing drift from the current CLAUDE.md.

## `CLAUDE.md` after the change

Keeps the header and `## What this is` section (project description +
"run everything from repo root" note) unchanged. Everything else is replaced
by a `## Rules` section listing links to each file in `rules/`.

## Out of scope

- No changes to `docs/*.md` reference docs themselves.
- No Cursor-style glob-conditional rule metadata (user declined that option).
- No further splitting of `architecture.md` into per-module files.
