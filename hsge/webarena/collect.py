"""Phase-2 collection loop: solve composer-generated tasks, verify, record.

INFO/NAV run before the MOD batch so read answers can't be dirtied by writes,
and the (slow) instance reset happens at most once, after all MODs. Re-running
is idempotent: task_ids that already have an episode on disk are skipped.
"""
from __future__ import annotations

import glob
import json
import os

from .digest import evidence_grounded
from .evaluator import evaluate, extract_answer
from .recording import record_episode


def top_k_skill_hints(embedder, skills: list[dict], intent: str, k: int = 3) -> str | None:
    texts = [f"{s['name']}: {s.get('description', '')}"
             for s in skills or [] if s.get("name")]
    if not texts:
        return None
    vecs = embedder.encode(texts + [intent])
    q = vecs[-1]
    scored = sorted(zip((float(v @ q) for v in vecs[:-1]), texts), reverse=True)
    return "\n".join(f"- {t}" for _, t in scored[:k])


class GenerationRunner:
    def __init__(self, browser_factory, solver, out_dir: str, embedder, kb,
                 judge_llm=None, discovery=None, root_url: str = "",
                 reset_fn=None, skill_hints: bool = True):
        self.browser_factory = browser_factory
        self.solver = solver
        self.out_dir = out_dir
        self.embedder = embedder
        self.kb = kb
        self.judge_llm = judge_llm
        self.discovery = discovery
        self.root_url = root_url
        self.reset_fn = reset_fn
        self.skill_hints = skill_hints
        os.makedirs(os.path.join(out_dir, "episodes"), exist_ok=True)
        # continue numbering after phase-1 episodes (never overwrite them)
        self.episode = len(glob.glob(os.path.join(out_dir, "episodes", "ep_*")))

    def _done_task_ids(self) -> set[str]:
        done = set()
        for p in glob.glob(os.path.join(self.out_dir, "episodes", "*", "episode_meta.json")):
            try:
                tid = json.load(open(p)).get("task_id")
            except Exception:
                continue
            if tid:
                done.add(tid)
        return done

    def _is_stale(self, task: dict, axtree: str) -> bool:
        """A single-hop INFO task's cited evidence may have been mutated by a
        later phase-1/phase-2 write to the same shared, mutable page since its
        digest was captured; re-check it's still literally on the live page
        before spending a solve+score on what would be a false failure."""
        if task.get("type") != "INFO" or (task.get("hops") or 1) > 1:
            return False
        for ref in task.get("answer_fact_refs") or []:
            evidence = self.kb.resolve_ref_evidence(ref)
            if evidence and not evidence_grounded(evidence, axtree):
                return True
        return False

    def _dump_stats(self, stats: dict):
        """Merge GEN stats into summary.json without clobbering phase-1 fields."""
        spath = os.path.join(self.out_dir, "summary.json")
        summary = {}
        if os.path.exists(spath):
            try:
                summary = json.load(open(spath))
            except Exception:
                summary = {}
        summary["gen"] = stats
        json.dump(summary, open(spath, "w"), indent=2)

    def run(self, tasks: list[dict]) -> dict:
        order = ([t for t in tasks if t.get("type") in ("INFO", "NAV")]
                 + [t for t in tasks if t.get("type") == "MOD"])
        done = self._done_task_ids()
        stats = {"attempted": 0, "verified": 0, "failed": 0, "errors": 0,
                 "stale_skipped": 0,
                 "by_type": {k: {"verified": 0, "failed": 0}
                             for k in ("INFO", "NAV", "MOD")}}
        ran_mod = False
        for task in order:
            if task["task_id"] in done:
                continue
            browser = self.browser_factory(task["start_url"])
            try:
                obs = browser.reset()
                if self._is_stale(task, obs.get("axtree", "")):
                    stats["stale_skipped"] += 1
                    self._dump_stats(stats)
                    continue
                stats["attempted"] += 1
                hints = (top_k_skill_hints(self.embedder, self.kb.skills, task["intent"])
                         if self.skill_hints else None)
                steps, obs_texts, shots, final_obs, _ = self.solver.solve(
                    browser, task["intent"], hints=hints)
                answer = extract_answer(steps)
                verified, details = evaluate(task, answer, final_obs.get("url", ""),
                                             browser, judge=self.judge_llm)
            except Exception as e:  # a dead episode must not kill the batch
                steps, obs_texts, shots = [], [], []
                answer, verified, details = "", False, {"error": str(e)}
                stats["errors"] += 1
            finally:
                browser.close()
            record_episode(
                self.out_dir, self.episode, task["intent"], steps, obs_texts, shots,
                verified, difficulty=int(task.get("hops") or 1), tag="GEN",
                extra_meta={"task_id": task["task_id"], "verified": verified,
                            "task_type": task.get("type"), "eval": task.get("eval"),
                            "answer": answer, "eval_details": details})
            self.episode += 1
            stats["verified" if verified else "failed"] += 1
            by = stats["by_type"].get(task.get("type"))
            if by is not None:
                by["verified" if verified else "failed"] += 1
            if task.get("type") == "MOD":
                ran_mod = True
            if verified and self.discovery:
                self.discovery.on_trajectory(steps, site=self.root_url,
                                             task=task["intent"])
            print(f"    [gen] {task['task_id']} {task.get('type')} "
                  f"verified={verified} steps={len(steps)}")
            self._dump_stats(stats)   # after every task: interrupt-safe snapshot
        if ran_mod and self.reset_fn:
            self.reset_fn()
        return stats
