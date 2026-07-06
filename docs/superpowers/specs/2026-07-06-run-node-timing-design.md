# Run/Node Timing & Error Logging Design

Date: 2026-07-06

## Problem

`WebArenaExplorer.run()` in `hsge/webarena/runtime.py` has no timing
information at all: no record of when a run started, when it ended, how long
each node took, or when/why an unhandled exception stopped the run early.
`run_log.jsonl`, `nodes.json`, and `summary.json` all lack timestamps.

## Goal

Add wall-clock timing for the whole run and for each node, and a record of
an unhandled exception (if the run stops that way), without changing the
run's control flow: it must still stop on an unhandled exception exactly as
it does today (propagate to the caller) — only logging is added before that
happens.

## Design

### 1. Timestamp helper

New module-level `_now() -> tuple[float, str]` in `runtime.py`:

```python
def _now() -> tuple[float, str]:
    """(epoch seconds, ISO 8601 string) pair, used everywhere timing is recorded."""
    return time.time(), datetime.now().isoformat()
```

Requires new imports `import time` and `from datetime import datetime`.

### 2. Run-level timing

- At the top of `run()`, capture `self.run_started_epoch, self.run_started_iso = _now()` and log a new event: `self._log("run_start", started_at_epoch=self.run_started_epoch, started_at_iso=self.run_started_iso)`.
- The existing `while frontier and len(visited) < self.max_nodes:` loop is wrapped in `try/except Exception`. Track `current_node_index`/`current_node_url` (updated at the top of each iteration, `None` before the loop starts) so an exception raised before any node is visited still reports sensible (`None`) values instead of crashing the error handler itself.
- **On success** (loop exits normally): compute `ended_epoch, ended_iso = _now()`, `duration_sec = ended_epoch - self.run_started_epoch`; add these three fields to the existing `run_summary` log call; make one additional `_dump_artifacts(..., status="done", ended_at_epoch=ended_epoch, ended_at_iso=ended_iso, error=None)` call so `summary.json`'s final on-disk state reflects the completed run (all the calls to `_dump_artifacts` inside the loop already gave live snapshots with `status="running"`).
- **On exception**: compute `ended_epoch, ended_iso = _now()`, `duration_sec = ended_epoch - self.run_started_epoch`; log a new event `self._log("run_error", started_at_epoch=..., started_at_iso=..., ended_at_epoch=ended_epoch, ended_at_iso=ended_iso, duration_sec=duration_sec, error=str(e), error_type=type(e).__name__, last_node_index=current_node_index, last_node_url=current_node_url)`; call `_dump_artifacts(..., status="error", ended_at_epoch=ended_epoch, ended_at_iso=ended_iso, error=str(e))`; then `raise` (re-raise unchanged — the caller, `run_webarena.py`, sees the same exception it does today).

### 3. `_dump_artifacts` timing fields

`_dump_artifacts(self, task_stats, nodes_visited, duplicate_nodes, nodes_log, status="running", ended_at_epoch=None, ended_at_iso=None, error=None)` — new trailing keyword-only-by-convention params, all optional so every existing call site inside the loop (which doesn't know final timing yet) keeps working unchanged. The `summary` dict gains:

```python
summary = {
    ...  # existing fields unchanged
    "status": status,                        # "running" | "done" | "error"
    "started_at_epoch": self.run_started_epoch,
    "started_at_iso": self.run_started_iso,
    "ended_at_epoch": ended_at_epoch,         # None until run finishes/errors
    "ended_at_iso": ended_at_iso,
    "duration_sec": (ended_at_epoch - self.run_started_epoch) if ended_at_epoch else None,
    "error": error,                            # None unless status == "error"
}
```

### 4. Per-node timing

- At the top of each loop iteration (right after `url, depth = frontier.pop(0)`), capture `node_start_epoch, node_start_iso = _now()`; update `current_node_index`/`current_node_url` for the exception handler.
- `node_visit` and `node_duplicate_skip` log calls gain `started_at_epoch=node_start_epoch, started_at_iso=node_start_iso`.
- At the end of node handling — both the duplicate-skip early-`continue` path and the normal end-of-iteration path — compute `node_duration = time.time() - node_start_epoch` and:
  - add `started_at_epoch`, `started_at_iso`, `duration_sec` to the `node_rec`/duplicate-node dict that goes into `nodes_log` (→ persisted in `nodes.json`)
  - log a new event `self._log("node_done", index=node_index, duration_sec=node_duration)` (→ `run_log.jsonl`)

## Non-goals

- No change to control flow on the success path, and no change to the "stop on unhandled exception" behavior — only a log record is added before the exception propagates.
- No per-task (LOCAL/GOAL episode) timing — only run-level and node-level, per the request.
- No change to `run_webarena.py`'s handling of `explorer.run(...)` (it doesn't currently wrap the call in try/except; that's unchanged).

## Testing

- Manual check: `python run_webarena.py --dry-run --out /tmp/wa_timing --max-nodes 2`, then inspect `run_log.jsonl` for `run_start`, `node_done`, `run_summary` events with timing fields, and `summary.json` for `status`/`started_at_*`/`ended_at_*`/`duration_sec`.
- Manual error-path check: temporarily force an exception inside the loop (e.g. monkeypatch `browser_factory` to raise) and confirm a `run_error` event appears in `run_log.jsonl` and `summary.json` shows `status: "error"` with a non-null `error` field, and that the exception still propagates (script still exits non-zero).
