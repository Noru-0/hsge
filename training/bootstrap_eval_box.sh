#!/usr/bin/env bash
# Bring one vast.ai box from bare image to a running WebArena eval sweep for ONE
# domain. Identical on all four boxes; only --site and --site-url differ.
#
#   bash training/bootstrap_eval_box.sh --site shopping \
#       --site-url https://<tunnel> --adapter /workspace/saves/qwen35-9b-lora-all
#
# Order matters, and every step gates the next: the expensive thing here is a
# six-hour sweep, and each of these has produced a silently wrong or wasted run
# before.
#   1. inputs present            (a typo'd --site-url would error every task)
#   2. venvs + base model        (vast_setup.sh eval; skips the train venv)
#   3. merge adapter             (peft; asserts the vision tower survived)
#   4. serve under supervisor    (stopasgroup, or restart orphans a writer)
#   5. endpoint answers          (before spending tasks on a dead server)
#   6. judge configured          (40 tasks score 0 without it, silently)
#   7. site reachable FROM HERE  (local reachability proves nothing)
#   8. smoke 3 tasks             (must yield a non-errored result)
#   9. full sweep under supervisor, only if 8 passed
#
# Re-runnable: every stage is idempotent, so re-running after a fix continues
# rather than starting over.
set -uo pipefail

SITE="" SITE_URL="" ADAPTER=/workspace/saves/qwen35-9b-lora-all
BASE_MODEL=/workspace/models/Qwen3.5-9B
MERGED=/workspace/models/Qwen3.5-9B-all
JUDGE_MODEL=gpt-4-turbo
SMOKE=3
NO_FULL=0

while [ $# -gt 0 ]; do
    case "$1" in
        --site)        SITE=$2; shift 2 ;;
        --site-url)    SITE_URL=$2; shift 2 ;;
        --adapter)     ADAPTER=$2; shift 2 ;;
        --judge-model) JUDGE_MODEL=$2; shift 2 ;;
        --smoke)       SMOKE=$2; shift 2 ;;
        --no-full)     NO_FULL=1; shift ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

REPO=/workspace/hsge
EVAL_PY=/workspace/venvs/eval/bin/python
SERVE_PY=/workspace/venvs/serve/bin/python
OUT=/workspace/eval/$SITE/finetuned
ENV_FILE=/workspace/.eval_env

die() { echo "FAIL [$1] $2" >&2; exit 1; }
step() { echo; echo "=== $* ==="; }

# --- 1. inputs -------------------------------------------------------------
step "1/9 inputs"
[ -n "$SITE" ] || die inputs "--site is required (reddit|shopping|shopping_admin|gitlab)"
[ -n "$SITE_URL" ] || die inputs "--site-url is required"
[ -d "$REPO" ] || die inputs "$REPO missing -- rsync the repo first"
[ -n "${OPENAI_API_KEY:-}" ] || die inputs \
    "OPENAI_API_KEY unset. 40 of the 655 tasks are scored by WebArena's LLM judge
    (shopping 15, shopping_admin 20, gitlab 5, reddit 0); without a key they error
    out and score 0 with no other symptom."
echo "site=$SITE url=$SITE_URL adapter=$ADAPTER judge=$JUDGE_MODEL"

# --- 2. venvs + base model -------------------------------------------------
step "2/9 environment (eval mode: no train venv)"
if [ ! -f /workspace/.setup_markers/eval_venv ] \
   || [ ! -f /workspace/.setup_markers/serve_venv ] \
   || [ ! -f /workspace/.setup_markers/model_download ]; then
    bash /workspace/vast_setup.sh eval 2>&1 | tail -20 \
        || die setup "vast_setup.sh eval failed -- see /workspace/setup.log"
fi
for m in serve_venv eval_venv model_download; do
    [ -f "/workspace/.setup_markers/$m" ] || die setup "stage '$m' did not complete"
done
echo "venvs + base model ready"

# --- 3. merge adapter ------------------------------------------------------
step "3/9 merge adapter"
if [ -f "$MERGED/config.json" ]; then
    echo "already merged: $MERGED"
else
    [ -f "$ADAPTER/adapter_model.safetensors" ] \
        || die merge "no adapter at $ADAPTER (rsync training/artifacts/for-eval-checkpoint-536/ there)"
    "$SERVE_PY" "$REPO/training/merge_lora_peft.py" "$BASE_MODEL" "$ADAPTER" "$MERGED" \
        || die merge "merge_lora_peft.py failed"
fi

# --- 4. serve --------------------------------------------------------------
step "4/9 serve under supervisor"
cat > /etc/supervisor/conf.d/vllm.conf <<EOF
[program:vllm]
command=bash $REPO/training/serve_vllm.sh $MERGED
autostart=true
autorestart=true
; supervisorctl restart kills the shell but NOT its python child, which leaves two
; servers on one port; stop/kill as a group so the whole tree goes.
stopasgroup=true
killasgroup=true
stdout_logfile=/workspace/vllm.log
redirect_stderr=true
EOF
supervisorctl reread >/dev/null 2>&1
supervisorctl update >/dev/null 2>&1
supervisorctl start vllm >/dev/null 2>&1
echo "vllm: $(supervisorctl status vllm 2>&1)"

# --- 5. endpoint -----------------------------------------------------------
step "5/9 wait for the endpoint"
for _ in $(seq 1 60); do
    if curl -sf http://127.0.0.1:8000/v1/models >/dev/null 2>&1; then break; fi
    sleep 10
done
curl -sf http://127.0.0.1:8000/v1/models >/dev/null 2>&1 \
    || die serve "endpoint never came up -- tail /workspace/vllm.log"
# Prove it actually generates: vLLM has reached READY and then died on the first
# real request before (a JIT kernel compile failing under a mismatched toolkit).
GEN=$(curl -sf http://127.0.0.1:8000/v1/chat/completions \
        -H 'Content-Type: application/json' \
        -d '{"model":"qwen35-9b","messages":[{"role":"user","content":"say ok"}],"max_tokens":5}' \
        2>&1) || die serve "endpoint is up but the first completion failed: $GEN"
echo "endpoint generates ok"

# --- 6. judge --------------------------------------------------------------
step "6/9 configure the WebArena judge"
"$EVAL_PY" "$REPO/training/patch_webarena_judge.py" --model "$JUDGE_MODEL" 2>&1 | tail -8
cat > "$ENV_FILE" <<EOF
export OPENAI_API_KEY=$OPENAI_API_KEY
export WEBARENA_EVAL_MODEL=$JUDGE_MODEL
export WA_JUDGE_MODEL_OVERRIDE=$JUDGE_MODEL
EOF
chmod 600 "$ENV_FILE"
# shellcheck disable=SC1090
. "$ENV_FILE"
"$EVAL_PY" "$REPO/training/patch_webarena_judge.py" --model "$JUDGE_MODEL" --check \
    || die judge "judge still not configured"

# --- 7. site reachable from HERE ------------------------------------------
step "7/9 site reachable from this box"
CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$SITE_URL" 2>&1)
case "$CODE" in
    2*|3*) echo "$SITE_URL -> HTTP $CODE" ;;
    *) die reachability "$SITE_URL returned '$CODE' FROM THIS BOX. Local reachability
    proves nothing -- the tunnel must be reachable from here." ;;
esac

# --- 8. smoke --------------------------------------------------------------
step "8/9 smoke test ($SMOKE tasks)"
mkdir -p "$OUT"
SMOKE_OUT=/workspace/eval/$SITE/smoke
cd "$REPO"
"$EVAL_PY" -u training/eval_webarena.py --site "$SITE" --site-url "$SITE_URL" \
    --out "$SMOKE_OUT" --limit "$SMOKE" --trace-axtree 2>&1 | tail -25
SMOKE_OK=$("$EVAL_PY" - "$SMOKE_OUT/results.jsonl" <<'PY'
import json, sys
try:
    rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
except Exception:
    print(0); raise SystemExit
print(sum(1 for r in rows if not r.get("error")))
PY
)
[ "${SMOKE_OK:-0}" -ge 1 ] \
    || die smoke "all $SMOKE smoke tasks errored -- fix that before spending six hours.
    See $SMOKE_OUT/results.jsonl and $SMOKE_OUT/traces/*.json (llm_calls[].raw shows
    exactly what the model emitted)."
echo "smoke: $SMOKE_OK/$SMOKE tasks scored without error"

# --- 9. full sweep ---------------------------------------------------------
if [ "$NO_FULL" = 1 ]; then
    step "9/9 registering the sweep but NOT starting it (--no-full)"
else
    step "9/9 full sweep under supervisor"
fi
cat > /workspace/run_eval.sh <<EOF
#!/usr/bin/env bash
set -uo pipefail
. $ENV_FILE
cd $REPO
# -u so the log is not buffered: a buffered log once ran 31 minutes behind and
# triggered a false alarm that the sweep had hung.
exec $EVAL_PY -u training/eval_webarena.py --site $SITE --site-url $SITE_URL \\
    --out $OUT --trace-axtree
EOF
chmod +x /workspace/run_eval.sh
cat > /etc/supervisor/conf.d/evalsweep.conf <<EOF
[program:evalsweep]
command=bash /workspace/run_eval.sh
autostart=$([ "$NO_FULL" = 1 ] && echo false || echo true)
; exit 0 = finished, exit 3 = aborted on consecutive errors (infrastructure, not
; the model). Neither should be restarted: 3 in a loop would spin against a dead
; tunnel. Anything else is a crash and is worth one restart.
autorestart=unexpected
exitcodes=0,3
startsecs=30
stopasgroup=true
killasgroup=true
stdout_logfile=/workspace/eval_$SITE.log
redirect_stderr=true
EOF
supervisorctl reread >/dev/null 2>&1
supervisorctl update >/dev/null 2>&1
if [ "$NO_FULL" = 1 ]; then
    echo "registered, not started. Start it with: supervisorctl start evalsweep"
else
    supervisorctl start evalsweep >/dev/null 2>&1
fi
echo "evalsweep: $(supervisorctl status evalsweep 2>&1)"
echo
echo "READY. Watch it with:"
echo "  tail -f /workspace/eval_$SITE.log"
echo "  $EVAL_PY $REPO/training/eval_status.py $OUT"
