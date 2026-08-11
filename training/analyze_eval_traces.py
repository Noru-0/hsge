#!/usr/bin/env python3
"""Classify why each eval episode failed, per domain.

The previous sweep scored 0% and nothing in the artifacts could say why: the
results file recorded an aggregate and a truncated last action, so "the model
never found the page", "it found the page and misread it", and "its output was
unparseable so the episode ended" were indistinguishable. The traces written by
`eval_webarena.py` carry three separate records per episode (Solver steps, raw
LLM calls, per-act browser results); this turns them into counts.

Each category maps to one concrete signal, never to a guess. An episode gets
every label that applies -- the causes overlap (a stuck loop is usually a run of
action errors) -- plus exactly one `primary` label, chosen by the priority order
in `_PRIORITY`, so the per-domain table sums to the episode count.

Two categories are worth the run on their own:

- `declared_done_without_acting`: one step, `send_msg_to_user`, no effective
  action. This is the failure mode the training data was full of -- 42% of
  trajectories in the pre-fix dataset were a single step, and 104
  zero-effective-action trajectories were dropped from the current one. Its rate
  here is the measurement that connects the dataset work to the eval result.
- `reached_goal_then_left`: some step scored a reward but the episode ended at 0.
  Only measurable because the per-step reward is now recorded (WebArena's
  validate() runs every step). If this is non-trivial, the step budget is
  penalising the model rather than measuring it.

Usage:
    python training/analyze_eval_traces.py outputs/eval/*/finetuned
    python training/analyze_eval_traces.py <dir> --examples 3   # show sample task ids
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

EFFECTIVE = ("click", "fill", "select_option", "press", "goto", "go_back",
             "new_tab", "tab_focus", "tab_close")
_GOTO_TARGET = re.compile(r"goto\(\s*['\"]([^'\"]*)['\"]")

# Most-specific first: the first label an episode matches becomes its `primary`.
# Ordering rationale: a mechanical defect in the agent's output (unparseable
# JSON, an off-site or invented URL) explains the episode better than the guard
# that eventually stopped it, and "declared done without acting" outranks
# "ran out of budget" because it never used the budget at all.
_PRIORITY = [
    "unparseable_output",
    "offsite_goto",
    "placeholder_goto",
    "declared_done_without_acting",
    "reached_goal_then_left",
    "stuck_loop",
    "reported_infeasible",
    "action_errors",
    "budget_exhausted",
    "unclassified",
]


def _verb(action: str) -> str:
    m = re.match(r"[a-z_]+", (action or "").strip())
    return m.group(0) if m else ""


def classify(trace: dict) -> set[str]:
    """Every failure signal present in one episode's trace."""
    labels: set[str] = set()
    steps = trace.get("steps") or []
    llm_calls = trace.get("llm_calls") or []
    acts = trace.get("act_trace") or []
    actions = [s.get("action") or "" for s in steps]

    if any(not c.get("parsed_ok", True) for c in llm_calls):
        labels.add("unparseable_output")

    for act in actions:
        target = _GOTO_TARGET.search(act)
        if not target:
            continue
        t = target.group(1)
        if urlsplit(t).netloc:
            # A goto whose target carries a host: WebArena ends the episode at
            # reward 0 the moment the agent leaves the instance.
            labels.add("offsite_goto")
        elif not t.startswith("/"):
            # Neither a host nor a path: an invented placeholder such as
            # goto('url_of_compare_products_page'), which resolves to a
            # meaningless URL rather than raising.
            labels.add("placeholder_goto")

    if any(a.get("action_error") for a in acts):
        labels.add("action_errors")

    # No action that could change the page or the site's state, and it ended by
    # telling the user it was done.
    effective = [a for a in actions if a.startswith(EFFECTIVE)]
    if not effective and actions and actions[-1].startswith("send_msg_to_user"):
        labels.add("declared_done_without_acting")

    if any(a.startswith("report_infeasible") for a in actions):
        labels.add("reported_infeasible")

    # Scored at some point, finished at zero.
    if (trace.get("reward") or 0) <= 0 and any((a.get("step_reward") or 0) > 0
                                               for a in acts):
        labels.add("reached_goal_then_left")

    if trace.get("stop_reason") == "stuck":
        labels.add("stuck_loop")
    else:
        # Same target, nothing moved, three times running: the shape the live
        # guard catches, recomputed here for episodes recorded before it existed.
        run = 0
        for a in acts:
            same = a.get("url_before") == a.get("url_after")
            run = run + 1 if same and a.get("action_error") else 0
            if run >= 3:
                labels.add("stuck_loop")
                break

    if trace.get("stop_reason") == "budget":
        labels.add("budget_exhausted")

    if not labels:
        labels.add("unclassified")
    return labels


def primary(labels: set[str]) -> str:
    for name in _PRIORITY:
        if name in labels:
            return name
    return "unclassified"


def load_traces(d: Path) -> list[dict]:
    out = []
    for p in sorted((d / "traces").glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", help="eval output dirs (each holds traces/)")
    ap.add_argument("--examples", type=int, default=0,
                    help="print N example task ids per category")
    args = ap.parse_args()

    per_site_primary: dict[str, Counter] = defaultdict(Counter)
    per_site_any: dict[str, Counter] = defaultdict(Counter)
    per_site_n: Counter = Counter()
    per_site_ok: Counter = Counter()
    examples: dict[tuple[str, str], list[int]] = defaultdict(list)
    steps_by_outcome: dict[str, list[int]] = defaultdict(list)

    for d in map(Path, args.dirs):
        traces = load_traces(d)
        if not traces:
            print(f"(no traces in {d})")
            continue
        site = d.resolve().parent.name if d.name in ("finetuned", "base") else d.name
        for tr in traces:
            per_site_n[site] += 1
            if (tr.get("reward") or 0) > 0:
                per_site_ok[site] += 1
                steps_by_outcome["success"].append(tr.get("n_steps") or 0)
                continue
            labels = classify(tr)
            p = primary(labels)
            per_site_primary[site][p] += 1
            for lab in labels:
                per_site_any[site][lab] += 1
            steps_by_outcome["failure"].append(tr.get("n_steps") or 0)
            if len(examples[(site, p)]) < args.examples:
                examples[(site, p)].append(tr.get("task_id"))

    sites = sorted(per_site_n)
    if not sites:
        return 1

    print("episodes traced, and how the failures break down "
          "(primary cause, one per episode)\n")
    header = f"{'cause':<32}" + "".join(f"{s:>17}" for s in sites)
    print(header)
    print("-" * len(header))
    for name in _PRIORITY:
        if not any(per_site_primary[s].get(name) for s in sites):
            continue
        row = f"{name:<32}"
        for s in sites:
            n = per_site_primary[s].get(name, 0)
            fails = max(1, per_site_n[s] - per_site_ok[s])
            row += f"{n:>10} {n / fails:>5.0%}"
        print(row)
    print("-" * len(header))
    print(f"{'failed episodes':<32}" +
          "".join(f"{per_site_n[s] - per_site_ok[s]:>17}" for s in sites))
    print(f"{'succeeded':<32}" + "".join(f"{per_site_ok[s]:>17}" for s in sites))
    print(f"{'traced total':<32}" + "".join(f"{per_site_n[s]:>17}" for s in sites))

    print("\nsignals present ANYWHERE in a failed episode (categories overlap, "
          "so these do not sum)\n")
    print(header)
    print("-" * len(header))
    for name in _PRIORITY:
        if name == "unclassified" or not any(per_site_any[s].get(name) for s in sites):
            continue
        row = f"{name:<32}"
        for s in sites:
            n = per_site_any[s].get(name, 0)
            fails = max(1, per_site_n[s] - per_site_ok[s])
            row += f"{n:>10} {n / fails:>5.0%}"
        print(row)

    for key, kind in (("success", "successful"), ("failure", "failed")):
        vals = steps_by_outcome[key]
        if vals:
            vals = sorted(vals)
            print(f"\nsteps per {kind} episode: median {vals[len(vals) // 2]}, "
                  f"mean {sum(vals) / len(vals):.1f}, max {vals[-1]}")

    if args.examples:
        print("\nexample task ids")
        for (site, cause), ids in sorted(examples.items()):
            print(f"  {site:<16} {cause:<32} {ids}")

    print("\nRead these two first:")
    print("  declared_done_without_acting -- one step, send_msg_to_user, nothing "
          "touched. The pre-fix training set was 42% single-step trajectories and "
          "104 zero-effective-action ones were dropped from the current set, so "
          "this rate is what connects that work to this result.")
    print("  reached_goal_then_left -- a step scored but the episode ended at 0. "
          "If this is non-trivial, --max-steps is penalising the model rather "
          "than measuring it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
