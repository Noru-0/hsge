#!/usr/bin/env bash
# Pull one eval box's results down and prove the copy is byte-exact before you
# destroy the box.
#
#   bash training/collect_eval_results.sh --host 1.2.3.4 --port 25639 --site shopping
#   bash training/collect_eval_results.sh ... --dest outputs/eval    # default
#
# A vast.ai box without a host volume loses everything on destroy, and a sweep's
# traces cannot be regenerated without re-running six hours. Two failure modes
# this guards:
#
#   1. Copying while the sweep is still writing. That happened with the training
#      artifacts: the first rsync raced the trainer's final write, so
#      eval_results.json was missing and all_results.json was stale, and only a
#      checksum comparison caught it. Here the script refuses to certify the copy
#      unless the sweep has stopped, and always verifies afterwards.
#   2. Trusting `rsync` exit 0 as proof. It is proof that rsync ran, not that the
#      two sides match; only comparing digests is.
set -uo pipefail

HOST="" PORT="" SITE="" DEST=outputs/eval FORCE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --host)  HOST=$2; shift 2 ;;
        --port)  PORT=$2; shift 2 ;;
        --site)  SITE=$2; shift 2 ;;
        --dest)  DEST=$2; shift 2 ;;
        --force) FORCE=1; shift ;;      # copy even if the sweep is still running
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done
[ -n "$HOST" ] && [ -n "$PORT" ] && [ -n "$SITE" ] \
    || { echo "usage: $0 --host H --port P --site SITE [--dest DIR] [--force]" >&2; exit 2; }

SSH="ssh -p $PORT -o BatchMode=yes -o ConnectTimeout=15 root@$HOST"
REMOTE=/workspace/eval/$SITE/finetuned
LOCAL=$DEST/$SITE/finetuned

echo "=== 1/4 is the sweep finished? ==="
STATUS=$($SSH 'supervisorctl status evalsweep 2>&1 | head -1' 2>&1 | tr -d '\r')
echo "  $STATUS"
case "$STATUS" in
    *RUNNING*)
        if [ "$FORCE" = 1 ]; then
            echo "  WARNING: still RUNNING and --force given -- this copy is a snapshot,"
            echo "  NOT a certified-complete result. Do not destroy the box on it."
        else
            echo "  REFUSING: the sweep is still writing. Wait for it, or pass --force"
            echo "  for an explicitly-uncertified snapshot." >&2
            exit 1
        fi
        ;;
    *EXITED*|*STOPPED*|*FATAL*) echo "  sweep is not running -- safe to copy" ;;
    *) echo "  could not read supervisor status; treating as unknown" ;;
esac

echo "=== 2/4 remote summary ==="
$SSH "cat $REMOTE/summary.json 2>/dev/null || echo '(no summary.json yet)'"

echo "=== 3/4 pull ==="
mkdir -p "$LOCAL"
rsync -az -e "ssh -p $PORT -o BatchMode=yes" \
    "root@$HOST:$REMOTE/" "$LOCAL/" || { echo "rsync failed" >&2; exit 1; }
# The sweep log lives outside the results dir; it is the only place the abort
# message and the per-task stderr survive.
rsync -az -e "ssh -p $PORT -o BatchMode=yes" \
    "root@$HOST:/workspace/eval_$SITE.log" "$DEST/$SITE/" 2>/dev/null \
    || echo "  (no /workspace/eval_$SITE.log)"
du -sh "$LOCAL"

echo "=== 4/4 verify byte-exact ==="
REMOTE_SUM=$($SSH "cd $REMOTE && find . -type f | sort | xargs md5sum | md5sum" 2>/dev/null \
    | grep -oE '^[a-f0-9]{32}')
LOCAL_SUM=$(cd "$LOCAL" && find . -type f | sort | xargs md5sum | md5sum | grep -oE '^[a-f0-9]{32}')
echo "  remote: ${REMOTE_SUM:-?}"
echo "  local : ${LOCAL_SUM:-?}"
if [ -n "$REMOTE_SUM" ] && [ "$REMOTE_SUM" = "$LOCAL_SUM" ]; then
    echo "  MATCH -- $SITE is safe to destroy"
else
    echo "  MISMATCH -- do NOT destroy the box; re-run this script" >&2
    exit 1
fi

echo
echo "next:"
echo "  python training/eval_status.py $LOCAL"
echo "  python training/analyze_eval_traces.py $LOCAL --examples 3"
