"""Replay segmentation over recorded episodes and compare old vs new behavior.

Baseline = URL-boundary cuts only (the old algorithm, tau disabled).
New      = candidate cuts (URL + axtree similarity) -> LLM cut points -> nav merge.

    python replay_segmentation.py outputs/wa_run_02/episodes --limit 50 --mock
    python replay_segmentation.py outputs/wa_run_02/episodes --limit 50   # real LLM

--mock uses MockLLM (echoes candidates; no key needed): it evaluates the
candidate/merge machinery but not LLM cut quality. Note: episodes recorded
before Step.url was persisted (e.g. run 02) have url="" for every step, so the
baseline there under-cuts (documented limitation); the axtree signal is exact.
"""
from __future__ import annotations

import argparse
import glob
import json
import os

from hsge.llm import MockLLM
from hsge.schema import Step
from hsge.segmentation import (
    _action_verb, _candidate_boundaries, _spans_from_cuts, segment_trajectory,
)
from run_webarena import _effective_llm_config, _load_config, _load_dotenv

_NAV = {"click", "goto", "go_back"}


def load_steps(ep_dir: str) -> list[Step]:
    steps = []
    for line in open(os.path.join(ep_dir, "episode.jsonl")):
        rec = json.loads(line)
        if rec.get("record_type") != "step":
            continue
        ax_rel = ((rec.get("observation") or {}).get("axtree_txt") or {}).get("path", "")
        ax_path = os.path.join(ep_dir, ax_rel) if ax_rel else ""
        axtree = open(ax_path).read() if ax_path and os.path.exists(ax_path) else ""
        steps.append(Step(action=rec.get("parsed_action") or "",
                          url=rec.get("url") or "",
                          obs_summary=rec.get("thought") or "", axtree=axtree))
    return steps


def successful_episodes(episodes_dir: str, limit: int) -> list[str]:
    out = []
    for ep in sorted(glob.glob(os.path.join(episodes_dir, "ep_*"))):
        meta_path = os.path.join(ep, "episode_meta.json")
        if not os.path.exists(meta_path):
            continue
        meta = json.load(open(meta_path))
        if (meta.get("outcome") or {}).get("success"):
            out.append(ep)
        if len(out) >= limit:
            break
    return out


def spans_metrics(all_spans: list[list[tuple[int, int]]],
                  all_steps: list[list[Step]]) -> dict:
    n_seg = one_step = nav_only = 0
    for spans, steps in zip(all_spans, all_steps):
        for a, b in spans:
            n_seg += 1
            if b - a == 1:
                one_step += 1
            if all(_action_verb(s.action) in _NAV for s in steps[a:b]):
                nav_only += 1
    return {"segments": n_seg,
            "avg_per_traj": n_seg / max(1, len(all_spans)),
            "pct_one_step": 100.0 * one_step / max(1, n_seg),
            "pct_nav_only": 100.0 * nav_only / max(1, n_seg)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes_dir")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--tau", type=float, default=0.6)
    ap.add_argument("--mock", action="store_true",
                    help="use MockLLM (no key; candidates+merge only)")
    args = ap.parse_args()

    _load_dotenv()
    if args.mock:
        llm = MockLLM()
    else:
        ns = argparse.Namespace(provider=None, model=None, base_url=None)
        cfg = _effective_llm_config(ns, _load_config(args.config)["llm"],
                                    "trajectory_segmenter")
        from hsge.backends import OpenAILLM
        print(f"[llm] provider={cfg['provider']} model={cfg['model']}")
        llm = OpenAILLM(model=cfg["model"], base_url=cfg["base_url"],
                        api_key=cfg["api_key"], temperature=cfg["temperature"])

    eps = successful_episodes(args.episodes_dir, args.limit)
    print(f"replaying {len(eps)} successful episodes from {args.episodes_dir}")
    all_steps, base_spans, new_spans, labels = [], [], [], set()
    for ep in eps:
        steps = load_steps(ep)
        if not steps:
            continue
        all_steps.append(steps)
        # baseline: URL cuts only (tau=-1 -> the axtree branch never fires)
        base_spans.append(_spans_from_cuts(
            _candidate_boundaries(steps, -1.0), len(steps)))
        subs = segment_trajectory(llm, steps, site=args.episodes_dir,
                                  task="replay", axtree_sim=args.tau)
        new_spans.append(_subs_to_spans(subs))
        labels.update(s.subgoal for s in subs)

    for name, m in (("baseline (URL only)", spans_metrics(base_spans, all_steps)),
                    ("new (v2)", spans_metrics(new_spans, all_steps))):
        print(f"\n{name}:")
        print(f"  segments={m['segments']}  avg/traj={m['avg_per_traj']:.2f}  "
              f"1-step={m['pct_one_step']:.1f}%  nav-only={m['pct_nav_only']:.1f}%")
    print(f"\nnew: {len(labels)} distinct subgoal labels")


def _subs_to_spans(subs) -> list[tuple[int, int]]:
    spans, pos = [], 0
    for s in subs:
        spans.append((pos, pos + len(s.steps)))
        pos += len(s.steps)
    return spans


if __name__ == "__main__":
    main()
