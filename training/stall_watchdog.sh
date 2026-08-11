#!/usr/bin/env bash
# Restart evalsweep when it stops appending results.
#
# Why: a sweep can hang inside Playwright with no error and no log line -- a real
# reddit run sat 20 minutes on one task with an idle browser (no sockets, no CPU)
# and the main thread parked in ep_poll on the driver pipe. BrowserGym's 30s
# override bounds ACTIONS, not env setup, and eval_webarena.py's exit-3 guard
# counts consecutive ERRORS, which a hang never produces. So nothing noticed.
#
# Killing mid-task is safe: the task has no results.jsonl row yet, so resume
# re-runs it from scratch. Nothing partial is ever recorded.
set -uo pipefail
RESULTS=$1
STALL_S=${2:-1200}          # 20 min. Worst legitimate task ~9 min (16 steps x
                            # 30s action timeout + LLM + per-step validate()).
CHECK_S=60

while true; do
    sleep $CHECK_S
    state=$(supervisorctl status evalsweep 2>/dev/null | awk '{print $2}')
    # Only RUNNING is watched: EXITED/STOPPED means finished or deliberately
    # halted, and restarting either would loop against a dead sweep.
    [ "$state" = "RUNNING" ] || continue
    [ -f "$RESULTS" ] || continue
    age=$(( $(date +%s) - $(stat -c %Y "$RESULTS") ))
    if [ "$age" -gt "$STALL_S" ]; then
        echo "$(date -Is) STALL: no row appended for ${age}s (>${STALL_S}s) -- restarting evalsweep"
        supervisorctl restart evalsweep
        # Give the new process time to launch a browser and finish a task before
        # the next check, or a slow first task would trigger an immediate second
        # restart and livelock the sweep.
        sleep "$STALL_S"
    fi
done
