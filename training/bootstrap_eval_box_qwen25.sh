#!/usr/bin/env bash
# Bring one vast.ai box from bare image to a running WebArena eval sweep for ONE
# domain, evaluating the Qwen2.5-7B-Instruct finetune. Adapted from
# bootstrap_eval_box.sh (which targets Qwen3.5-9B): uses vast_setup_qwen25.sh
# (no Gated-DeltaNet/vision-tower packages), merge_lora_peft_qwen25.py (plain
# AutoModelForCausalLM, no vision-tower assertions), and serve_vllm_qwen25.sh
# (served name "qwen25-7b", template is the standard "qwen" ChatML -- no
# thinking-mode consideration).
#
#   bash training/bootstrap_eval_box_qwen25.sh --site shopping \
#       --site-url https://<tunnel> --adapter /workspace/saves/qwen25-7b-lora-merged-v1
#
# Baseline (untouched base model, no adapter, no merge):
#
#   bash training/bootstrap_eval_box_qwen25.sh --site shopping \
#       --site-url https://<tunnel> --base
#
# Same 9-gate order as bootstrap_eval_box.sh; see that script's header for the
# rationale of each gate.
set -uo pipefail

SITE="" SITE_URL="" ADAPTER=/workspace/saves/qwen25-7b-lora-merged-v1
BASE_MODEL=/workspace/models/Qwen2.5-7B-Instruct
MERGED=/workspace/models/Qwen2.5-7B-Instruct-merged-v1
JUDGE_MODEL=gpt-4-turbo
SMOKE=3
NO_FULL=0
BASE_ONLY=0

while [ $# -gt 0 ]; do
    case "$1" in
        --site)        SITE=$2; shift 2 ;;
        --site-url)    SITE_URL=$2; shift 2 ;;
        --adapter)     ADAPTER=$2; shift 2 ;;
        --judge-model) JUDGE_MODEL=$2; shift 2 ;;
        --smoke)       SMOKE=$2; shift 2 ;;
        --no-full)     NO_FULL=1; shift ;;
        --base)        BASE_ONLY=1; shift ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

if [ "$BASE_ONLY" = 1 ]; then
    VARIANT=base; SERVE_MODEL=$BASE_MODEL
else
    VARIANT=finetuned; SERVE_MODEL=$MERGED
fi

REPO=/workspace/hsge
EVAL_PY=/workspace/venvs/eval/bin/python
SERVE_PY=/workspace/venvs/serve/bin/python
OUT=/workspace/eval/$SITE/$VARIANT
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
if [ "$BASE_ONLY" = 1 ]; then
    echo "site=$SITE url=$SITE_URL variant=BASE (no adapter) judge=$JUDGE_MODEL"
else
    echo "site=$SITE url=$SITE_URL variant=finetuned adapter=$ADAPTER judge=$JUDGE_MODEL"
fi

# --- 2. venvs + base model -------------------------------------------------
step "2/9 environment (eval mode: no train venv)"
if [ ! -f /workspace/.setup_markers_qwen25/eval_venv ] \
   || [ ! -f /workspace/.setup_markers_qwen25/serve_venv ] \
   || [ ! -f /workspace/.setup_markers_qwen25/model_download ]; then
    bash /workspace/vast_setup_qwen25.sh eval 2>&1 | tail -20 \
        || die setup "vast_setup_qwen25.sh eval failed -- see /workspace/setup_qwen25.log"
fi
for m in serve_venv eval_venv model_download; do
    [ -f "/workspace/.setup_markers_qwen25/$m" ] || die setup "stage '$m' did not complete"
done
echo "venvs + base model ready"

# --- 3. merge adapter ------------------------------------------------------
step "3/9 merge adapter"
if [ "$BASE_ONLY" = 1 ]; then
    [ -f "$BASE_MODEL/config.json" ] \
        || die merge "no base model at $BASE_MODEL"
    echo "baseline run -- skipping merge, serving $BASE_MODEL untouched"
elif [ -f "$MERGED/config.json" ]; then
    echo "already merged: $MERGED"
else
    [ -f "$ADAPTER/adapter_model.safetensors" ] \
        || die merge "no adapter at $ADAPTER (rsync training/artifacts/qwen25-7b-lora-merged-v1/ there)"
    "$SERVE_PY" "$REPO/training/merge_lora_peft_qwen25.py" "$BASE_MODEL" "$ADAPTER" "$MERGED" \
        || die merge "merge_lora_peft_qwen25.py failed"
fi

# --- 4. serve --------------------------------------------------------------
step "4/9 serve under supervisor"
cat > /etc/supervisor/conf.d/vllm.conf <<EOF
[program:vllm]
command=bash $REPO/training/serve_vllm_qwen25.sh $SERVE_MODEL
autostart=true
autorestart=true
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
GEN=$(curl -sf http://127.0.0.1:8000/v1/chat/completions \
        -H 'Content-Type: application/json' \
        -d '{"model":"qwen25-7b","messages":[{"role":"user","content":"say ok"}],"max_tokens":5}' \
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
SMOKE_OUT=/workspace/eval/$SITE/smoke_$VARIANT
cd "$REPO"
"$EVAL_PY" -u training/eval_webarena.py --site "$SITE" --site-url "$SITE_URL" \
    --out "$SMOKE_OUT" --limit "$SMOKE" --variant "$VARIANT" --model qwen25-7b --trace-axtree 2>&1 | tail -25
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
exec $EVAL_PY -u training/eval_webarena.py --site $SITE --site-url $SITE_URL \\
    --out $OUT --variant $VARIANT --model qwen25-7b --trace-axtree
EOF
chmod +x /workspace/run_eval.sh
cat > /etc/supervisor/conf.d/evalsweep.conf <<EOF
[program:evalsweep]
command=bash /workspace/run_eval.sh
autostart=$([ "$NO_FULL" = 1 ] && echo false || echo true)
autorestart=unexpected
exitcodes=0,3
startsecs=30
stopasgroup=true
killasgroup=true
stdout_logfile=/workspace/eval_${SITE}_$VARIANT.log
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
echo "  tail -f /workspace/eval_${SITE}_$VARIANT.log"
echo "  $EVAL_PY $REPO/training/eval_status.py $OUT"
