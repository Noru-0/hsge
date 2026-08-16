#!/usr/bin/env bash
# Auto-recovery watchdog for run_webarena.py.
#
# Root cause of the hangs this guards against (see .claude/memory/bugs.md,
# "run_webarena.py hangs indefinitely mid-run, immune to SIGINT"): a Playwright
# sync-API call blocked in native/C IPC with the Node driver or Chromium
# subprocess has no top-level timeout, so the process can freeze forever with
# 0% CPU. It survives SIGINT (KeyboardInterrupt only fires at a Python
# bytecode boundary, never reached). We cannot fix the root cause without a
# native stack trace (py-spy/lldb both require elevated permissions this
# sandbox doesn't have), so this script is the practical mitigation: watch
# run_log.jsonl's mtime, and if it goes stale while the process is still
# alive, SIGKILL (never caught, works even mid-blocking-syscall) and relaunch
# with --resume. This automates exactly the manual recovery already done 3x
# by hand for outputs/wa_run_21_reddit.
#
# Usage:
#   scripts/watchdog_webarena.sh <site> <out_dir> [max_nodes] [stall_secs] [target_success]
#
# Example:
#   scripts/watchdog_webarena.sh reddit outputs/wa_run_21_reddit 500 1800 500
#
# Runs in the foreground; wrap with nohup/background if you want it detached.
# Requires: conda env `go-browse` active (or activate it before running).

set -uo pipefail

SITE="${1:?usage: watchdog_webarena.sh <site> <out_dir> [max_nodes] [stall_secs] [target_success]}"
OUT_DIR="${2:?usage: watchdog_webarena.sh <site> <out_dir> [max_nodes] [stall_secs] [target_success]}"
MAX_NODES="${3:-500}"
STALL_SECS="${4:-1800}"      # 30 min: matches the manual threshold used so far
TARGET_SUCCESS="${5:-500}"
POLL_SECS=120

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

WATCHDOG_LOG="${OUT_DIR}/watchdog.log"
mkdir -p "$OUT_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$WATCHDOG_LOG"
}

total_success() {
    python3 - "$OUT_DIR/summary.json" <<'PY' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print(0)
    raise SystemExit
t = d.get("tasks", {})
print(sum(t.get(k, {}).get("success", 0) for k in ("LOCAL", "UNPREFIXED", "GOAL")))
PY
}

run_status() {
    python3 - "$OUT_DIR/summary.json" <<'PY' 2>/dev/null
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("status", "running"))
except Exception:
    print("running")
PY
}

launch() {
    local resume_flag=""
    if [ -f "${OUT_DIR}/checkpoint.pkl" ]; then
        resume_flag="--resume"
    fi
    log "launching: python run_webarena.py --site $SITE --max-nodes $MAX_NODES --out $OUT_DIR $resume_flag"
    nohup python run_webarena.py --site "$SITE" --max-nodes "$MAX_NODES" --out "$OUT_DIR" $resume_flag \
        >> "${OUT_DIR}/watchdog_stdout.log" 2>&1 &
    PID=$!
    log "started PID $PID"
}

launch
RESTARTS=0

while true; do
    sleep "$POLL_SECS"

    if ! kill -0 "$PID" 2>/dev/null; then
        status=$(run_status)
        succ=$(total_success)
        if [ "$status" = "done" ]; then
            log "process exited, status=done, total_success=$succ -- finished cleanly."
            exit 0
        fi
        log "process $PID died unexpectedly (status=$status, success=$succ). Relaunching once; " \
            "if this repeats it's likely a real error (credit/quota/config), not a hang -- check ${OUT_DIR}.log."
        launch
        RESTARTS=$((RESTARTS + 1))
        continue
    fi

    succ=$(total_success)
    if [ "$succ" -ge "$TARGET_SUCCESS" ]; then
        log "reached target ($succ >= $TARGET_SUCCESS success). Stopping PID $PID."
        kill "$PID" 2>/dev/null
        exit 0
    fi

    log_file="${OUT_DIR}/run_log.jsonl"
    if [ ! -f "$log_file" ]; then
        continue
    fi
    last_mtime=$(stat -f "%m" "$log_file" 2>/dev/null || stat -c "%Y" "$log_file" 2>/dev/null)
    now=$(date +%s)
    gap=$((now - last_mtime))

    if [ "$gap" -ge "$STALL_SECS" ]; then
        RESTARTS=$((RESTARTS + 1))
        log "STALL DETECTED: run_log.jsonl untouched for ${gap}s (>= ${STALL_SECS}s), PID $PID still alive with frozen CPU. This is restart #${RESTARTS}."
        log "last run_log events before kill:"
        tail -3 "$log_file" | tee -a "$WATCHDOG_LOG"
        log "SIGKILL-ing PID $PID (SIGINT/SIGTERM don't work on this hang -- see bugs.md)."
        kill -9 "$PID" 2>/dev/null
        sleep 3
        launch
    fi
done
