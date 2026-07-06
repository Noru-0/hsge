# Run/Node Timing & Error Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record wall-clock timing for the whole WebArena run and for each node, and a structured record of an unhandled exception (if the run stops that way), across `run_log.jsonl`, `nodes.json`, and `summary.json` — without changing the existing stop-on-exception control flow.

**Architecture:** A new `_now()` helper in `hsge/webarena/runtime.py` returns `(epoch, iso)` pairs. `WebArenaExplorer.run()`'s node loop is wrapped in `try/except Exception` so an unhandled exception is logged (with elapsed time and the node being processed) before it re-raises unchanged. Per-node start/duration is captured at the top/bottom of each loop iteration. `_dump_artifacts()` gains optional `status`/`ended_at_*`/`error` parameters so `summary.json` always reflects the run's current timing and status (`"running"` during the loop, `"done"` or `"error"` in the two final calls).

**Tech Stack:** Python standard library only (`time`, `datetime`) — no new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-06-run-node-timing-design.md`
- No change to control flow on the success path, and the run must still stop on an unhandled exception exactly as it does today (the exception must still propagate to the caller, `run_webarena.py`) — only a log record is added before that happens.
- No per-task (LOCAL/GOAL episode) timing — only run-level and node-level.
- No change to `run_webarena.py` — it doesn't currently wrap `explorer.run(...)` in try/except, and that stays unchanged.
- Timestamps are always recorded as **both** an epoch float (`*_epoch`) and an ISO 8601 string (`*_iso`), via the shared `_now()` helper — never one without the other.
- This is a single cohesive change to one file (`hsge/webarena/runtime.py`); do not split it across multiple commits/tasks — the `run()` reindent (wrapping the loop in `try`) and the `_dump_artifacts` signature change are interdependent and must land together.

---

### Task 1: Run/node timing + run_error logging in `runtime.py`

**Files:**
- Modify: `hsge/webarena/runtime.py`
- Test: `hsge/tests/test_run_timing.py` (new)

**Interfaces:**
- Produces: `_now() -> tuple[float, str]` (module-level function in `hsge/webarena/runtime.py`), `self.run_started_epoch: float`, `self.run_started_iso: str` (instance attributes set at the top of `run()`), and an updated `_dump_artifacts(self, task_stats, nodes_visited, duplicate_nodes, nodes_log, status="running", ended_at_epoch=None, ended_at_iso=None, error=None)` signature. Nothing outside this file consumes these — this task is self-contained.

- [ ] **Step 1: Add the `time`/`datetime` imports and the `_now()` helper**

In `hsge/webarena/runtime.py`, change the import block (currently lines 16-20):

```python
import base64
import hashlib
import json
import os
import re
```
to:
```python
import base64
import hashlib
import json
import os
import re
import time
from datetime import datetime
```

Then, right after the existing `_slug` function (currently lines 33-34):

```python
def _slug(name: str) -> str:
    return re.sub(r"\W+", "_", (name or "").strip().lower())[:24] or "op"
```

add:

```python
def _now() -> tuple[float, str]:
    """(epoch seconds, ISO 8601 string) pair -- used everywhere timing is recorded,
    so run_log.jsonl/nodes.json/summary.json all stay in the same two formats."""
    return time.time(), datetime.now().isoformat()
```

- [ ] **Step 2: Extend `_dump_artifacts` with timing/status fields**

In `hsge/webarena/runtime.py`, the current method (lines 203-254) is:

```python
    # ---- persist the discovered skill library / operator graph / run stats ---
    def _dump_artifacts(self, task_stats: dict, nodes_visited: int, duplicate_nodes: int,
                        nodes_log: list):
        """Write what was actually learned to disk (not just stdout/run_log.jsonl).

        Called after every node so a run interrupted partway through (Ctrl+C,
        network hiccup, ...) still leaves a consistent, up-to-date snapshot --
        not just the final tally.
        """
        skills = [card.to_dict() for card in self.library.all_skills()]
        json.dump(skills, open(os.path.join(self.out_dir, "skills.json"), "w"), indent=2)

        operators = []
        for op in self.opgraph.ops.values():
            grounding = self.operator_grounding.get(op.name, {})
            operators.append({
                "name": op.name, "preconditions": sorted(op.preconditions),
                "effects": sorted(op.effects), "terminal": op.terminal,
                "precondition_labels": {p: self.registry.label(p)
                                        for p in sorted(op.preconditions)},
                "effect_labels": {e: self.registry.label(e)
                                  for e in sorted(op.effects)},
                "precondition_confirmed": grounding.get("precondition_accuracy", {}),
                "effect_confirmed": grounding.get("effect_accuracy", {}),
            })
        json.dump(operators, open(os.path.join(self.out_dir, "operators.json"), "w"), indent=2)

        # p0/p1/... are canonical predicate ids (see PredicateRegistry.canonical);
        # this is the id -> original NL text lookup so operators.json is legible.
        predicates = {f"p{cid}": label for cid, label in self.registry.labels.items()}
        json.dump(predicates, open(os.path.join(self.out_dir, "predicates.json"), "w"), indent=2)

        graph = {
            "states": sorted(self.graph.states),
            "trajectory_edges": {u: sorted(vs) for u, vs in self.graph.trajectory_edges.items()},
            "state_to_skill": {k: sorted(v) for k, v in self.graph.state_to_skill.items()},
            "skill_to_state": {k: sorted(v) for k, v in self.graph.skill_to_state.items()},
            "skill_to_skill": {k: sorted(v) for k, v in self.graph.skill_to_skill.items()},
        }
        json.dump(graph, open(os.path.join(self.out_dir, "graph.json"), "w"), indent=2)

        # per-node breakdown: which tasks ran at that node and whether they passed
        json.dump(nodes_log, open(os.path.join(self.out_dir, "nodes.json"), "w"), indent=2)

        summary = {
            "nodes_visited": nodes_visited,
            "duplicate_nodes_skipped": duplicate_nodes,
            "episodes": self.episode,
            "tasks": task_stats,
            "skills_discovered": len(skills),
            "operators_induced": len(operators),
        }
        json.dump(summary, open(os.path.join(self.out_dir, "summary.json"), "w"), indent=2)
```

Replace the method signature and the `summary` dict construction (everything else in the method body is unchanged):

```python
    # ---- persist the discovered skill library / operator graph / run stats ---
    def _dump_artifacts(self, task_stats: dict, nodes_visited: int, duplicate_nodes: int,
                        nodes_log: list, status: str = "running",
                        ended_at_epoch: float | None = None, ended_at_iso: str | None = None,
                        error: str | None = None):
        """Write what was actually learned to disk (not just stdout/run_log.jsonl).

        Called after every node so a run interrupted partway through (Ctrl+C,
        network hiccup, ...) still leaves a consistent, up-to-date snapshot --
        not just the final tally. `status`/`ended_at_*`/`error` are only non-default
        on the two final calls in run() (success or exception); every call during
        the loop leaves them at "running"/None so the on-disk summary always
        reflects the run's current state.
        """
        skills = [card.to_dict() for card in self.library.all_skills()]
        json.dump(skills, open(os.path.join(self.out_dir, "skills.json"), "w"), indent=2)

        operators = []
        for op in self.opgraph.ops.values():
            grounding = self.operator_grounding.get(op.name, {})
            operators.append({
                "name": op.name, "preconditions": sorted(op.preconditions),
                "effects": sorted(op.effects), "terminal": op.terminal,
                "precondition_labels": {p: self.registry.label(p)
                                        for p in sorted(op.preconditions)},
                "effect_labels": {e: self.registry.label(e)
                                  for e in sorted(op.effects)},
                "precondition_confirmed": grounding.get("precondition_accuracy", {}),
                "effect_confirmed": grounding.get("effect_accuracy", {}),
            })
        json.dump(operators, open(os.path.join(self.out_dir, "operators.json"), "w"), indent=2)

        # p0/p1/... are canonical predicate ids (see PredicateRegistry.canonical);
        # this is the id -> original NL text lookup so operators.json is legible.
        predicates = {f"p{cid}": label for cid, label in self.registry.labels.items()}
        json.dump(predicates, open(os.path.join(self.out_dir, "predicates.json"), "w"), indent=2)

        graph = {
            "states": sorted(self.graph.states),
            "trajectory_edges": {u: sorted(vs) for u, vs in self.graph.trajectory_edges.items()},
            "state_to_skill": {k: sorted(v) for k, v in self.graph.state_to_skill.items()},
            "skill_to_state": {k: sorted(v) for k, v in self.graph.skill_to_state.items()},
            "skill_to_skill": {k: sorted(v) for k, v in self.graph.skill_to_skill.items()},
        }
        json.dump(graph, open(os.path.join(self.out_dir, "graph.json"), "w"), indent=2)

        # per-node breakdown: which tasks ran at that node and whether they passed
        json.dump(nodes_log, open(os.path.join(self.out_dir, "nodes.json"), "w"), indent=2)

        summary = {
            "nodes_visited": nodes_visited,
            "duplicate_nodes_skipped": duplicate_nodes,
            "episodes": self.episode,
            "tasks": task_stats,
            "skills_discovered": len(skills),
            "operators_induced": len(operators),
            "status": status,
            "started_at_epoch": self.run_started_epoch,
            "started_at_iso": self.run_started_iso,
            "ended_at_epoch": ended_at_epoch,
            "ended_at_iso": ended_at_iso,
            "duration_sec": (ended_at_epoch - self.run_started_epoch) if ended_at_epoch else None,
            "error": error,
        }
        json.dump(summary, open(os.path.join(self.out_dir, "summary.json"), "w"), indent=2)
```

- [ ] **Step 3: Rewrite `run()` with start/end/error/per-node timing**

In `hsge/webarena/runtime.py`, replace the entire `run()` method (currently lines 256-393):

```python
    # ---- the loop ------------------------------------------------------------
    def run(self, root_url: str):
        open(os.path.join(self.out_dir, "run_log.jsonl"), "w").close()  # fresh log for this run
        frontier, visited = [(root_url, 0)], set()
        seen_content: set[str] = set()   # sha256 of a node's initial axtree
        duplicate_nodes = 0
        task_stats = {"LOCAL": {"success": 0, "fail": 0}, "GOAL": {"success": 0, "fail": 0}}
        nodes_log: list[dict] = []   # per-node record: url, tasks tried, pass/fail (-> nodes.json)
        if not self.terminal_goal:
            print("[goal] no terminal predicate for this run -> exploration-only "
                  "(skills/operators still discovered; goal composition disabled).")
        while frontier and len(visited) < self.max_nodes:
            url, depth = frontier.pop(0)
            if url in visited:
                continue
            visited.add(url)
            node_index = len(visited)
            browser = self.browser_factory(url)
            obs = browser.reset()

            # Two different URLs can render the same content (redirects, aliases,
            # already-authenticated login pages, ...). Skip re-exploring content
            # we've already proposed/solved tasks for -- it wastes a full batch of
            # explorer+solver LLM calls for zero new discovery.
            content_hash = hashlib.sha256(obs["axtree"].encode("utf-8")).hexdigest()
            if content_hash in seen_content:
                duplicate_nodes += 1
                print(f"[node {node_index}/{self.max_nodes}] {obs['url']} "
                      f"-- duplicate content of a visited page, skipping")
                self._log("node_duplicate_skip", index=node_index, url=obs["url"], depth=depth)
                nodes_log.append({"index": node_index, "url": obs["url"], "depth": depth,
                                   "duplicate": True, "tasks": [], "frontier_added": 0,
                                   "screenshot": None})
                browser.close()
                self._dump_artifacts(task_stats, len(visited) - duplicate_nodes,
                                      duplicate_nodes, nodes_log)
                continue
            seen_content.add(content_hash)

            print(f"[node {node_index}/{self.max_nodes}] {obs['url']} "
                  f"(depth={depth}, frontier={len(frontier)})")
            self._log("node_visit", index=node_index, url=obs["url"], depth=depth)
            node_rec = {"index": node_index, "url": obs["url"], "depth": depth,
                        "duplicate": False, "tasks": [], "frontier_added": 0, "screenshot": None}

            # one screenshot capture reused both for PageExplorer's vision input and
            # for the on-disk record of what the node looked like.
            node_screenshot_b64 = (browser.screenshot_b64(som=self.explorer.som)
                                    if self.explorer.vision else None)
            if node_screenshot_b64:
                node_dir = os.path.join(self.out_dir, "node_state")
                os.makedirs(node_dir, exist_ok=True)
                shotp = f"node_state/node_{node_index:04d}_screenshot.jpg"
                open(os.path.join(self.out_dir, shotp), "wb").write(
                    base64.b64decode(node_screenshot_b64))
                node_rec["screenshot"] = shotp

            # URLs actually loaded while solving become frontier candidates (the agent
            # navigates during tasks); open tabs are added too. Page hrefs are not in
            # the flattened axtree, so this visited-during-solving signal is what grows
            # the frontier -- same approach as go-browse's open_pages_urls tracking.
            seen_urls = set()

            # 1) local exploration
            for task in self.explorer.propose(obs, screenshot_b64=node_screenshot_b64):
                episode_id = f"ep_{self.episode:04d}"
                browser.reset()
                steps, obs_texts, obs_screenshots, final_obs, success = self.solver.solve(browser, task)
                self._record(task, steps, obs_texts, obs_screenshots, success, difficulty=1, tag="LOCAL")
                task_stats["LOCAL"]["success" if success else "fail"] += 1
                node_rec["tasks"].append({"episode": episode_id, "tag": "LOCAL", "task": task,
                                           "success": success, "steps": len(steps)})
                self._log("task_result", node_index=node_index, episode=episode_id, tag="LOCAL",
                           task=task, success=success, steps=len(steps))
                if success:
                    # only skills that recur enough to be admitted become operators
                    admitted = self.discovery.on_trajectory(steps, site=root_url, task=task)
                    for sid in admitted:
                        card = self._card_by_id(sid)
                        if card:
                            print(f"    [skill] admitted {card.skill_id} '{card.name}' "
                                  f"(members={len(card.member_ids)})")
                            self._log("skill_admitted", skill_id=card.skill_id, name=card.name,
                                       members=len(card.member_ids))
                        self._promote_skill_to_operator(sid)
                seen_urls.update(st.url for st in steps)
                seen_urls.add(final_obs.get("url", ""))
                print(f"    local: {task[:50]!r} success={success} steps={len(steps)}")

            # 2) goal-conditioned composed task (once a plan to the goal exists)
            gt = self._goal_task()
            if gt:
                episode_id = f"ep_{self.episode:04d}"
                browser.reset()
                steps, obs_texts, obs_screenshots, final_obs, success = self.solver.solve(
                    browser, gt["goal"], goal_predicate=self.terminal_goal)
                self._record(gt["goal"], steps, obs_texts, obs_screenshots, success,
                             difficulty=gt["difficulty"], tag="GOAL")
                task_stats["GOAL"]["success" if success else "fail"] += 1
                node_rec["tasks"].append({"episode": episode_id, "tag": "GOAL", "task": gt["goal"],
                                           "success": success, "steps": len(steps)})
                self._log("task_result", node_index=node_index, episode=episode_id, tag="GOAL",
                           task=gt["goal"], success=success, steps=len(steps), chain=gt["chain"])
                seen_urls.update(st.url for st in steps)
                print(f"    GOAL chain={gt['chain']} verified={success} steps={len(steps)}")

            # 3) expand frontier (bounded by max_depth) with pages seen while solving
            if depth < self.max_depth:
                seen_urls.update(browser.links())
                new_links = [link for link in sorted(seen_urls)
                             if self._admit_url(link, visited)]
                frontier.extend((link, depth + 1) for link in new_links)
                node_rec["frontier_added"] = len(new_links)
                if new_links:
                    print(f"    frontier: +{len(new_links)} new url(s)")
                    self._log("frontier_expand", node_index=node_index, added=len(new_links))
            browser.close()

            nodes_log.append(node_rec)
            nodes_visited = len(visited) - duplicate_nodes
            self._dump_artifacts(task_stats, nodes_visited, duplicate_nodes, nodes_log)

        nodes_visited = len(visited) - duplicate_nodes
        print(f"\ndone: {nodes_visited} nodes ({duplicate_nodes} duplicate skipped), "
              f"{self.episode} episodes, "
              f"{len(self.library.all_skills())} skills, {len(self.opgraph.ops)} operators")
        print(f"  tasks: LOCAL success={task_stats['LOCAL']['success']} "
              f"fail={task_stats['LOCAL']['fail']}  "
              f"GOAL success={task_stats['GOAL']['success']} fail={task_stats['GOAL']['fail']}")
        print(f"trajectories under {self.out_dir}/episodes  "
              f"(feed to build_sft_dataset.py)")
        print(f"per-run log/artifacts (run_log.jsonl, nodes.json, skills.json, "
              f"operators.json, predicates.json, graph.json, summary.json) under {self.out_dir}")
        self._log("run_summary", nodes_visited=nodes_visited, duplicate_nodes_skipped=duplicate_nodes,
                   episodes=self.episode, tasks=task_stats,
                   skills_discovered=len(self.library.all_skills()),
                   operators_induced=len(self.opgraph.ops))
```

with:

```python
    # ---- the loop ------------------------------------------------------------
    def run(self, root_url: str):
        open(os.path.join(self.out_dir, "run_log.jsonl"), "w").close()  # fresh log for this run
        self.run_started_epoch, self.run_started_iso = _now()
        self._log("run_start", started_at_epoch=self.run_started_epoch,
                   started_at_iso=self.run_started_iso)
        frontier, visited = [(root_url, 0)], set()
        seen_content: set[str] = set()   # sha256 of a node's initial axtree
        duplicate_nodes = 0
        task_stats = {"LOCAL": {"success": 0, "fail": 0}, "GOAL": {"success": 0, "fail": 0}}
        nodes_log: list[dict] = []   # per-node record: url, tasks tried, pass/fail (-> nodes.json)
        # updated at the top of each iteration; used by the except block below so an
        # exception raised before any node completes still reports a sensible value.
        current_node_index, current_node_url = None, None
        if not self.terminal_goal:
            print("[goal] no terminal predicate for this run -> exploration-only "
                  "(skills/operators still discovered; goal composition disabled).")
        try:
            while frontier and len(visited) < self.max_nodes:
                url, depth = frontier.pop(0)
                if url in visited:
                    continue
                visited.add(url)
                node_index = len(visited)
                current_node_index, current_node_url = node_index, url
                node_start_epoch, node_start_iso = _now()
                browser = self.browser_factory(url)
                obs = browser.reset()

                # Two different URLs can render the same content (redirects, aliases,
                # already-authenticated login pages, ...). Skip re-exploring content
                # we've already proposed/solved tasks for -- it wastes a full batch of
                # explorer+solver LLM calls for zero new discovery.
                content_hash = hashlib.sha256(obs["axtree"].encode("utf-8")).hexdigest()
                if content_hash in seen_content:
                    duplicate_nodes += 1
                    print(f"[node {node_index}/{self.max_nodes}] {obs['url']} "
                          f"-- duplicate content of a visited page, skipping")
                    node_duration = time.time() - node_start_epoch
                    self._log("node_duplicate_skip", index=node_index, url=obs["url"], depth=depth,
                               started_at_epoch=node_start_epoch, started_at_iso=node_start_iso)
                    nodes_log.append({"index": node_index, "url": obs["url"], "depth": depth,
                                       "duplicate": True, "tasks": [], "frontier_added": 0,
                                       "screenshot": None,
                                       "started_at_epoch": node_start_epoch,
                                       "started_at_iso": node_start_iso,
                                       "duration_sec": node_duration})
                    self._log("node_done", index=node_index, duration_sec=node_duration)
                    browser.close()
                    self._dump_artifacts(task_stats, len(visited) - duplicate_nodes,
                                          duplicate_nodes, nodes_log)
                    continue
                seen_content.add(content_hash)

                print(f"[node {node_index}/{self.max_nodes}] {obs['url']} "
                      f"(depth={depth}, frontier={len(frontier)})")
                self._log("node_visit", index=node_index, url=obs["url"], depth=depth,
                           started_at_epoch=node_start_epoch, started_at_iso=node_start_iso)
                node_rec = {"index": node_index, "url": obs["url"], "depth": depth,
                            "duplicate": False, "tasks": [], "frontier_added": 0, "screenshot": None}

                # one screenshot capture reused both for PageExplorer's vision input and
                # for the on-disk record of what the node looked like.
                node_screenshot_b64 = (browser.screenshot_b64(som=self.explorer.som)
                                        if self.explorer.vision else None)
                if node_screenshot_b64:
                    node_dir = os.path.join(self.out_dir, "node_state")
                    os.makedirs(node_dir, exist_ok=True)
                    shotp = f"node_state/node_{node_index:04d}_screenshot.jpg"
                    open(os.path.join(self.out_dir, shotp), "wb").write(
                        base64.b64decode(node_screenshot_b64))
                    node_rec["screenshot"] = shotp

                # URLs actually loaded while solving become frontier candidates (the agent
                # navigates during tasks); open tabs are added too. Page hrefs are not in
                # the flattened axtree, so this visited-during-solving signal is what grows
                # the frontier -- same approach as go-browse's open_pages_urls tracking.
                seen_urls = set()

                # 1) local exploration
                for task in self.explorer.propose(obs, screenshot_b64=node_screenshot_b64):
                    episode_id = f"ep_{self.episode:04d}"
                    browser.reset()
                    steps, obs_texts, obs_screenshots, final_obs, success = self.solver.solve(browser, task)
                    self._record(task, steps, obs_texts, obs_screenshots, success, difficulty=1, tag="LOCAL")
                    task_stats["LOCAL"]["success" if success else "fail"] += 1
                    node_rec["tasks"].append({"episode": episode_id, "tag": "LOCAL", "task": task,
                                               "success": success, "steps": len(steps)})
                    self._log("task_result", node_index=node_index, episode=episode_id, tag="LOCAL",
                               task=task, success=success, steps=len(steps))
                    if success:
                        # only skills that recur enough to be admitted become operators
                        admitted = self.discovery.on_trajectory(steps, site=root_url, task=task)
                        for sid in admitted:
                            card = self._card_by_id(sid)
                            if card:
                                print(f"    [skill] admitted {card.skill_id} '{card.name}' "
                                      f"(members={len(card.member_ids)})")
                                self._log("skill_admitted", skill_id=card.skill_id, name=card.name,
                                           members=len(card.member_ids))
                            self._promote_skill_to_operator(sid)
                    seen_urls.update(st.url for st in steps)
                    seen_urls.add(final_obs.get("url", ""))
                    print(f"    local: {task[:50]!r} success={success} steps={len(steps)}")

                # 2) goal-conditioned composed task (once a plan to the goal exists)
                gt = self._goal_task()
                if gt:
                    episode_id = f"ep_{self.episode:04d}"
                    browser.reset()
                    steps, obs_texts, obs_screenshots, final_obs, success = self.solver.solve(
                        browser, gt["goal"], goal_predicate=self.terminal_goal)
                    self._record(gt["goal"], steps, obs_texts, obs_screenshots, success,
                                 difficulty=gt["difficulty"], tag="GOAL")
                    task_stats["GOAL"]["success" if success else "fail"] += 1
                    node_rec["tasks"].append({"episode": episode_id, "tag": "GOAL", "task": gt["goal"],
                                               "success": success, "steps": len(steps)})
                    self._log("task_result", node_index=node_index, episode=episode_id, tag="GOAL",
                               task=gt["goal"], success=success, steps=len(steps), chain=gt["chain"])
                    seen_urls.update(st.url for st in steps)
                    print(f"    GOAL chain={gt['chain']} verified={success} steps={len(steps)}")

                # 3) expand frontier (bounded by max_depth) with pages seen while solving
                if depth < self.max_depth:
                    seen_urls.update(browser.links())
                    new_links = [link for link in sorted(seen_urls)
                                 if self._admit_url(link, visited)]
                    frontier.extend((link, depth + 1) for link in new_links)
                    node_rec["frontier_added"] = len(new_links)
                    if new_links:
                        print(f"    frontier: +{len(new_links)} new url(s)")
                        self._log("frontier_expand", node_index=node_index, added=len(new_links))
                browser.close()

                node_duration = time.time() - node_start_epoch
                node_rec["started_at_epoch"] = node_start_epoch
                node_rec["started_at_iso"] = node_start_iso
                node_rec["duration_sec"] = node_duration
                nodes_log.append(node_rec)
                self._log("node_done", index=node_index, duration_sec=node_duration)
                nodes_visited = len(visited) - duplicate_nodes
                self._dump_artifacts(task_stats, nodes_visited, duplicate_nodes, nodes_log)
        except Exception as e:
            ended_epoch, ended_iso = _now()
            duration_sec = ended_epoch - self.run_started_epoch
            self._log("run_error", started_at_epoch=self.run_started_epoch,
                       started_at_iso=self.run_started_iso,
                       ended_at_epoch=ended_epoch, ended_at_iso=ended_iso,
                       duration_sec=duration_sec, error=str(e), error_type=type(e).__name__,
                       last_node_index=current_node_index, last_node_url=current_node_url)
            nodes_visited = len(visited) - duplicate_nodes
            self._dump_artifacts(task_stats, nodes_visited, duplicate_nodes, nodes_log,
                                  status="error", ended_at_epoch=ended_epoch, ended_at_iso=ended_iso,
                                  error=str(e))
            raise

        nodes_visited = len(visited) - duplicate_nodes
        print(f"\ndone: {nodes_visited} nodes ({duplicate_nodes} duplicate skipped), "
              f"{self.episode} episodes, "
              f"{len(self.library.all_skills())} skills, {len(self.opgraph.ops)} operators")
        print(f"  tasks: LOCAL success={task_stats['LOCAL']['success']} "
              f"fail={task_stats['LOCAL']['fail']}  "
              f"GOAL success={task_stats['GOAL']['success']} fail={task_stats['GOAL']['fail']}")
        print(f"trajectories under {self.out_dir}/episodes  "
              f"(feed to build_sft_dataset.py)")
        print(f"per-run log/artifacts (run_log.jsonl, nodes.json, skills.json, "
              f"operators.json, predicates.json, graph.json, summary.json) under {self.out_dir}")
        ended_epoch, ended_iso = _now()
        duration_sec = ended_epoch - self.run_started_epoch
        self._log("run_summary", nodes_visited=nodes_visited, duplicate_nodes_skipped=duplicate_nodes,
                   episodes=self.episode, tasks=task_stats,
                   skills_discovered=len(self.library.all_skills()),
                   operators_induced=len(self.opgraph.ops),
                   started_at_epoch=self.run_started_epoch, started_at_iso=self.run_started_iso,
                   ended_at_epoch=ended_epoch, ended_at_iso=ended_iso, duration_sec=duration_sec)
        self._dump_artifacts(task_stats, nodes_visited, duplicate_nodes, nodes_log,
                              status="done", ended_at_epoch=ended_epoch, ended_at_iso=ended_iso,
                              error=None)
```

- [ ] **Step 4: Write the failing test for the error path**

Create `hsge/tests/test_run_timing.py`:

```python
"""run() must log timing (start/end/per-node duration) and, on an unhandled
exception, a run_error record with elapsed time and which node it happened on
-- while still re-raising the exception exactly as before (the run stops the
same way; only a log record is added first)."""

import json

import pytest

from hsge.llm import HashingEmbedder
from hsge.webarena.runtime import WebArenaExplorer


class _NeverCalledLLM:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        raise AssertionError("LLM must not be called before the browser factory raises")


def _raising_browser_factory(url):
    raise RuntimeError("boom")


def test_run_logs_run_error_and_reraises(tmp_path):
    explorer = WebArenaExplorer(
        browser_factory=_raising_browser_factory,
        llm=_NeverCalledLLM(),
        embedder=HashingEmbedder(),
        out_dir=str(tmp_path),
        allow_pattern=".*",
    )

    with pytest.raises(RuntimeError, match="boom"):
        explorer.run("http://example.com")

    log_records = [json.loads(line) for line in open(tmp_path / "run_log.jsonl")]
    events = [r["event"] for r in log_records]
    assert "run_start" in events
    assert "run_error" in events

    start_rec = next(r for r in log_records if r["event"] == "run_start")
    assert isinstance(start_rec["started_at_epoch"], float)
    assert isinstance(start_rec["started_at_iso"], str)

    error_rec = next(r for r in log_records if r["event"] == "run_error")
    assert error_rec["error"] == "boom"
    assert error_rec["error_type"] == "RuntimeError"
    assert error_rec["last_node_index"] == 1
    assert error_rec["last_node_url"] == "http://example.com"
    assert error_rec["duration_sec"] >= 0

    summary = json.load(open(tmp_path / "summary.json"))
    assert summary["status"] == "error"
    assert summary["error"] == "boom"
    assert summary["duration_sec"] >= 0
    assert summary["ended_at_epoch"] is not None
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_run_timing.py -v`
Expected: FAIL — `_dump_artifacts()` / `run()` don't yet have the `status`/timing fields, or `run_log.jsonl` doesn't yet contain `run_start`/`run_error` (whichever the current code hits first; since Steps 1-3 haven't been applied yet in a from-scratch TDD run, this should fail with an `AssertionError` on a missing event or a `KeyError`/`AttributeError` if `self.run_started_epoch` doesn't exist yet).

- [ ] **Step 6: Apply Steps 1-3 above if not already applied, then run the test again**

Run: `PYTHONPATH=. python -m pytest hsge/tests/test_run_timing.py -v`
Expected: PASS

- [ ] **Step 7: Run the full test suite to confirm no regressions**

Run: `PYTHONPATH=. python -m pytest hsge/tests/ -q`
Expected: PASS (all tests, including the pre-existing 44 plus this new one)

- [ ] **Step 8: Manual smoke test of the success path**

Run: `PYTHONPATH=. python run_webarena.py --dry-run --out /tmp/wa_timing --max-nodes 2`

```bash
python -c "
import json
log = [json.loads(l) for l in open('/tmp/wa_timing/run_log.jsonl')]
events = [r['event'] for r in log]
print('run_start' in events, 'node_done' in events, 'run_summary' in events)
summary = json.load(open('/tmp/wa_timing/summary.json'))
print(summary['status'], summary['duration_sec'] is not None, summary['error'])
"
```
Expected: prints `True True True` then `done True None`.

- [ ] **Step 9: Commit**

```bash
git add hsge/webarena/runtime.py hsge/tests/test_run_timing.py
git commit -m "$(cat <<'EOF'
Add run/node timing and run_error logging to the WebArena runtime

run() now logs run_start/run_summary/run_error events (epoch + ISO
timestamps) and per-node started_at/duration_sec in both run_log.jsonl and
nodes.json. summary.json gains status/started_at/ended_at/duration_sec/error
fields. The node loop is wrapped in try/except so an unhandled exception is
logged (with elapsed time and which node it happened on) before it
re-raises unchanged -- the run still stops exactly as it did before.
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage:** `_now()` helper (spec §1) → Step 1. Run-level start/summary/error timing (spec §2) → Steps 1 and 3 (the `try/except` wrapper, `run_start`/`run_error`/`run_summary` logging). `_dump_artifacts` status/timing fields (spec §3) → Step 2. Per-node `started_at_*`/`duration_sec` in `nodes.json` and the new `node_done` event (spec §4) → Step 3. Non-goals (unchanged control flow, no per-task timing, no `run_webarena.py` change) are respected — the `except` block still ends in `raise`, and no other file is touched.
- **Placeholder scan:** none — every step has complete, runnable code and exact expected output.
- **Type consistency:** `_now()` returns `tuple[float, str]` everywhere it's used (`run_started_epoch`/`iso`, `node_start_epoch`/`iso`, `ended_epoch`/`iso`) — matches spec's `(epoch seconds, ISO 8601 string)` pair exactly. `_dump_artifacts`'s new params (`status`, `ended_at_epoch`, `ended_at_iso`, `error`) match both call sites added in Step 3 (the `except` block and the final success-path call) and the existing in-loop calls (which omit them, taking the defaults).
