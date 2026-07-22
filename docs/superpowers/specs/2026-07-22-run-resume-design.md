# Accurate resume for interrupted WebArena runs

**Date:** 2026-07-22
**Status:** approved, ready to implement

## Problem

`WebArenaExplorer.run()` is a long-lived frontier loop (potentially many hours,
hundreds of nodes, real API cost). If the process dies mid-run — hard kill, OOM,
power loss, or Ctrl-C — everything is lost: there is no way to continue where it
stopped. The per-node `*.json` artifacts are lossy summaries, not restorable
state, and the pending frontier is never persisted at all (`run_log.jsonl` records
only the *count* of URLs pushed per node, not which URLs), so the run cannot be
reconstructed from what is on disk today.

## Goal

Resume an interrupted run so it continues **as if never interrupted**: same
frontier (contents and pop order), same visited/dedup sets, and every discovered
skill / operator / predicate preserved exactly (including the numpy centroids in
the clustering state). Losing at most the single node in flight when the process
died is acceptable.

## Decisions (settled during brainstorming)

- **Interruption model:** must survive a hard kill (kill -9 / OOM / power loss),
  not just a graceful Ctrl-C. → checkpoint is written **atomically after every
  node**; a node interrupted mid-processing is redone from its start on resume.
- **Mechanism:** **pickle** a single in-memory state snapshot. Reconstructing the
  discovery objects (library + registry + opgraph, with numpy centroids) from
  JSON would need a lot of fragile custom (de)serialization; pickle restores them
  exactly with little code. Resume runs the *same code version* that wrote the
  checkpoint, so pickle's class-version fragility does not arise in practice.
- **Backends are not pickled.** LLM clients, the embedder, and `browser_factory`
  are unpicklable and are rebuilt at resume from config/`.env`/CLI, then
  re-injected into the unpickled objects.

## Architecture

New artifact: `<out_dir>/checkpoint.pkl`, written atomically (`checkpoint.pkl.tmp`
then `os.replace`) at every point `run()` currently calls `_dump_artifacts`
(after each completed node, on duplicate-content skip, on node-load error, on
`run_error`, and at clean `done`).

Resume is triggered by a new `--resume` flag on `run_webarena.py` pointing at the
same `--out` directory. The explorer is constructed normally (so all backends
exist), then `explorer.load_checkpoint(path)` overwrites its in-memory state and
re-injects the backends.

## Checkpointed state

A single pickled dict with two groups:

- **Loop state** (currently locals inside `run()`): `frontier` (the heapq list),
  `visited`, `queued`, `template_counts`, `seen_content`, the current `seq`
  counter value, `duplicate_nodes`, `node_errors`, `task_stats`, `nodes_log`,
  `self.episode`, `run_started_epoch`/`run_started_iso`.
- **Discovery state** (objects on `self`): `library`, `registry`, `opgraph`,
  `graph`, `discovery`, `_op_meta`, `_attempted_chains`, `operator_grounding`,
  and `explorer` (kept for its already-proposed-task memory so resume does not
  re-propose duplicates).

Pickle's memo preserves shared references (e.g. `discovery.library is
self.library`, `registry` referenced from `self`) — each object is stored once.

## Backend detach / re-inject (the error-prone part)

`_write_checkpoint()` wraps the dump:

```
saved = {}  # attr path -> backend object
detach: set to None, remembering the originals:
    library.llm, library.abstraction_llm, library.verification_llm, library.embedder
    registry.llm, registry.embedder
    discovery.segmentation_llm
    explorer.llm
try:
    pickle.dump(state, tmp); os.replace(tmp, checkpoint.pkl)
finally:
    restore every saved ref   # ALWAYS, so a failed dump never leaves the
                              # running run with a null backend
```

`browser_factory`, `solver`, and `operator_llm` are not pickled (browser_factory
is a lambda; solver holds no state worth restoring; operator_llm is a plain
backend) — they are rebuilt at resume.

`load_checkpoint(path)`:
1. `pickle.load` → state dict.
2. Overwrite the discovery objects onto `self` (`self.library`, `self.registry`,
   `self.opgraph`, `self.graph`, `self.discovery`, `self.explorer`, `self._op_meta`,
   `self._attempted_chains`, `self.operator_grounding`, `self.episode`).
3. Re-inject the backends the constructor already built (reverse of detach):
   `library.llm/.abstraction_llm/.verification_llm/.embedder`,
   `registry.llm` (= `self.operator_llm`), `registry.embedder`,
   `discovery.segmentation_llm`, `explorer.llm`.
4. Store the loop-state scalars on `self._resume_loop_state` for `run()` to pick up.

**Correctness constraint:** `registry.embedder` / `library.embedder` must be the
same embedder *model* as the original run (config `embedder.model`), or old
centroids and new vectors live in different spaces. Resume must use the original
config; log a warning if `embedder.model` differs from what the run started with
(store the model name in the checkpoint and compare).

## Log / artifact continuity + overwrite guard

- `run()` currently truncates `run_log.jsonl` at start (line 420). Change: only
  truncate on a **fresh** run; on resume, open it in **append** mode and emit a
  `run_resume` event (`resumed_from_nodes`, `frontier_size`), so the event stream
  stays continuous.
- The `*.json` snapshots are rewritten from in-memory state every node, so they
  continue correctly once state is restored — no special handling. `episodes/`
  and `node_state/` accumulate because `self.episode` / `node_index` are restored.
- **Overwrite guard** in `run_webarena.py`: if `<out_dir>/checkpoint.pkl` exists
  and `--resume` was NOT passed → error and stop ("checkpoint exists; pass
  --resume to continue or choose a new --out"), instead of today's silent
  `run_log.jsonl` truncation + overwrite. Conversely `--resume` with no
  checkpoint present → clear error.
- **Clean finish:** on `done`, leave `checkpoint.pkl` in place; resuming a done
  run sees an empty frontier / `max_nodes` reached and exits immediately. Raising
  `--max-nodes` on resume lets a finished-early run continue (max_nodes is read
  from CLI/config at resume, not from the checkpoint; `visited` is restored so
  counting continues from where it stopped).

## `run()` resume branch

At the top of `run()`: if `self._resume_loop_state` is set, initialize the loop
locals (`frontier`, `visited`, `queued`, `template_counts`, `seen_content`,
`seq` rebuilt from the saved count via `itertools.count(start)`, counters,
`task_stats`, `nodes_log`) from it and append to `run_log.jsonl`; otherwise the
existing fresh-start path runs unchanged. The rest of the loop body is untouched.

## Test plan (TDD, mock backends, no API key)

`hsge/tests/test_resume.py`, using the existing dry-run `_FakeBrowser` + `MockLLM`:

1. `test_checkpoint_roundtrip` — run a few mock nodes, `_write_checkpoint()`; a
   fresh explorer `load_checkpoint()`s and matches on `visited`, `queued`,
   `template_counts`, `seen_content`, `task_stats`, `episode`, library skill
   count, registry predicate count, opgraph op count, and the remaining frontier
   (same URLs and pop order).
2. `test_backends_reattached_and_runnable` — after `load_checkpoint`, backends are
   non-None and the explorer runs another node without error.
3. `test_detach_restore_is_reversible` — after `_write_checkpoint()`, the running
   explorer's backends are unchanged (try/finally restored them).
4. `test_resume_does_not_revisit_or_redo` — a URL already in `visited` is skipped
   after resume; no duplicate episode is produced.
5. `test_atomic_write_leaves_no_partial` — patch `pickle.dump` to raise mid-write;
   the previous `checkpoint.pkl` is intact and only `.tmp` is discarded.
6. `test_guard_refuses_overwrite_without_resume` — guard helper errors when a
   checkpoint exists without `--resume`, and when `--resume` is set with no
   checkpoint.

The full existing suite (145 tests) must stay green: the non-resume path is
behaviourally unchanged (`_resume_loop_state is None` → the old fresh-start path;
the guard only fires when a checkpoint file is present).

## Files touched

- `hsge/webarena/runtime.py` — `_write_checkpoint()`, `load_checkpoint()`, the
  resume branch in `run()`, and checkpoint calls alongside every `_dump_artifacts`.
- `run_webarena.py` — `--resume` flag, the overwrite guard, and calling
  `load_checkpoint` before `run()`.
- `hsge/tests/test_resume.py` — new.

No changes to `schema.py` / `library.py` / `predicate_registry.py`: detach/re-inject
is done in one place in `runtime.py` rather than adding `__getstate__` to the
production classes.
