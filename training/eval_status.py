#!/usr/bin/env python3
"""One-line health report per eval sweep, read from results.jsonl.

Reads the results file, never the log. A previous run's monitoring was fooled by
`grep` buffering its output, which put the log 31 minutes behind reality and
raised a false alarm that a healthy sweep had hung. results.jsonl is appended
per task and is the only thing that is true at the moment you look at it.

Local (aggregate several boxes' pulled-down dirs):
    python training/eval_status.py outputs/eval/*/finetuned

On a box (single sweep):
    /workspace/venvs/eval/bin/python training/eval_status.py /workspace/eval/shopping/finetuned

Reports, per sweep: progress against the site's FULL official task count, the
success rate over that same denominator, errors, unparseable model responses,
throughput, and an ETA extrapolated from the tasks actually finished. `STALE`
means nothing has been appended for a while -- with ephemeral tunnels that is
the signal worth watching, and it is invisible in a success rate.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Official single-site task counts, from config_files/test.raw.json. Hardcoded so
# the status check needs no network and no WebArena checkout.
SITE_TASKS = {"reddit": 106, "shopping": 187, "shopping_admin": 182, "gitlab": 180}


def read_sweep(d: Path) -> dict | None:
    results = d / "results.jsonl"
    if not results.exists():
        return None
    rows: list[dict] = []
    for line in results.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    summary = {}
    sfile = d / "summary.json"
    if sfile.exists():
        try:
            summary = json.loads(sfile.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Pre-2026-08 summaries carry neither `site` nor `n_site_tasks`, and a dir may
    # be named for the model rather than the domain (`.../base`). Fall back
    # through: recorded site -> path -> recorded total -> rows seen, and label the
    # denominator so a guessed one is never mistaken for the official count.
    site = summary.get("site") or _guess_site(d)
    n_total = SITE_TASKS.get(site, 0) or int(summary.get("n_site_tasks") or 0) \
        or int(summary.get("n_tasks") or 0)
    denom_known = bool(SITE_TASKS.get(site)) or bool(summary.get("n_site_tasks"))
    scored = [r for r in rows if not r.get("error")]
    errored = [r for r in rows if r.get("error")]
    elapsed = [r.get("elapsed_s") or 0 for r in rows]
    return {
        "dir": d,
        "site": site or d.name,
        "n_total": n_total or len(rows),
        "denom_known": denom_known,
        "n_rows": len(rows),
        "n_scored": len(scored),
        "n_errored": len(errored),
        "n_success": sum(1 for r in rows if r.get("success")),
        "n_unparsed": sum(r.get("n_unparsed_llm", 0) or 0 for r in rows),
        "mean_s": (sum(elapsed) / len(elapsed)) if elapsed else 0.0,
        "age_s": time.time() - results.stat().st_mtime,
        "aborted": bool(summary.get("aborted_on_consecutive_errors")),
        "complete": bool(summary.get("complete")),
        "judge": summary.get("judge_model_override", ""),
    }


def _guess_site(d: Path) -> str:
    for part in reversed(d.resolve().parts):
        if part in SITE_TASKS:
            return part
    return ""


def fmt_eta(remaining: int, mean_s: float) -> str:
    if remaining <= 0:
        return "done"
    if mean_s <= 0:
        return "?"
    h, m = divmod(int(remaining * mean_s / 60), 60)
    return f"{h}h{m:02d}m"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", help="eval output dirs (each holds results.jsonl)")
    ap.add_argument("--stale-minutes", type=float, default=25.0,
                    help="flag a sweep whose results.jsonl has not grown in this long "
                         "(default 25; the slowest observed task took ~19 min)")
    args = ap.parse_args()

    sweeps = [s for s in (read_sweep(Path(d)) for d in args.dirs) if s]
    if not sweeps:
        print("no results.jsonl found in: " + ", ".join(args.dirs), file=sys.stderr)
        return 1

    print(f"{'site':<15} {'progress':>12} {'success':>14} {'err':>5} {'bad':>4} "
          f"{'s/task':>7} {'eta':>7}  state")
    worst = 0
    for s in sorted(sweeps, key=lambda x: x["site"]):
        remaining = max(0, s["n_total"] - s["n_rows"])
        rate = (s["n_success"] / s["n_total"]) if s["n_total"] else 0.0
        if s["aborted"]:
            state, code = "ABORTED (infra)", 3
        elif s["complete"]:
            state, code = "complete", 0
        elif s["age_s"] > args.stale_minutes * 60:
            state, code = f"STALE {int(s['age_s'] / 60)}m", 2
        else:
            state, code = "running", 0
        worst = max(worst, code)
        total = f"{s['n_total']}" + ("" if s["denom_known"] else "?")
        print(f"{s['site']:<15} {s['n_rows']:>5}/{total:<6} "
              f"{s['n_success']:>4}/{total:<5} {rate:>5.1%} "
              f"{s['n_errored']:>5} {s['n_unparsed']:>4} "
              f"{s['mean_s']:>7.0f} {fmt_eta(remaining, s['mean_s']):>7}  {state}")
    if any(not s["denom_known"] for s in sweeps):
        print("\n'?' marks a denominator inferred from the results file rather than "
              "the official per-site task count -- do not quote it as a WebArena score.")

    judges = {s["judge"] for s in sweeps if s["judge"]}
    if len(judges) > 1:
        # Different judges across domains would make the four numbers
        # incomparable, which is the whole point of running them.
        print(f"\nWARNING: sweeps used DIFFERENT judge models {sorted(judges)} -- "
              f"the per-domain numbers are not comparable.")
    elif judges:
        print(f"\njudge model: {judges.pop()} (a deviation from the published "
              f"evaluator -- disclose it)")
    unparsed = sum(s["n_unparsed"] for s in sweeps)
    if unparsed:
        print(f"unparseable model responses: {unparsed} -- inspect "
              f"traces/*.json -> llm_calls[].raw")
    return worst


if __name__ == "__main__":
    sys.exit(main())
