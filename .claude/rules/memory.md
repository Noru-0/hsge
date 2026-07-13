# Project memory (`.claude/memory/`)

Two append-style logs live in `.claude/memory/`:

- [memory/changelog.md](../memory/changelog.md) — every finished change: **when**
  (date + time), **which file(s)**, **what** was changed.
- [memory/bugs.md](../memory/bugs.md) — every bug: status (open/fixed), where it
  was found, symptom, root cause, fix.

## Rules

1. **Read both files at the start of a session** (or before starting any code
   change) — they are the quickest way to know what recently changed and which
   bugs are open or were already fixed (don't re-fix or re-introduce them).
2. **After finishing and verifying a change**, append an entry to
   `changelog.md` under today's date heading (create the heading if missing,
   newest day first). Get the real timestamp with `date "+%Y-%m-%d %H:%M"` —
   never guess the time. One entry per coherent change, same granularity as a
   commit; include the commit hash when the change is committed.
3. **When a bug is found**, add it to the *Open* section of `bugs.md` — even if
   it won't be fixed right away. **When it's fixed**, move the entry to *Fixed*,
   fill in cause/fix, and set the fixed timestamp.
4. These updates are part of finishing a task — do them without being asked,
   in the same turn as the change itself. Include the memory files in the same
   commit as the change they describe.
5. Both files are in English (repo convention) and are committed to git.
