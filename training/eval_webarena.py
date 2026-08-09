#!/usr/bin/env python3
"""Evaluate an OpenAI-compatible endpoint on one official WebArena site subset.

Runs the WebArena tasks whose `sites == ["<site>"]` (single-site tasks only —
gitlab ~180, shopping ~187, reddit ~106 of the 812 test tasks) through
BrowserGym, so success is scored by the official evaluators — comparable to
published numbers. The agent is the repo's own `Solver`
(unchanged: same system prompt, axtree cap, history format the model was
fine-tuned on), driven through a thin `WebArenaBrowser` subclass that swaps
the open-ended exploration env for the scored `browsergym/webarena.<id>` task
env and accumulates its reward.

The Solver never executes its terminal `send_msg_to_user(...)` /
`report_infeasible(...)` action in the browser; here we replay that final
action into the env afterwards, because WebArena's string-match evaluators
read the answer from the chat.

Usage (on the vast.ai box, with vLLM already serving on localhost:8000):
    /workspace/venvs/eval/bin/python training/eval_webarena.py --site reddit \
        --site-url https://<your-tunnel> --out /workspace/eval/reddit/finetuned
    # quick smoke test:            ... --limit 3
    # explicit tasks:              ... --tasks 156,258
    # base model with thinking on: ... --keep-thinking   (not recommended)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

TEST_RAW_URL = ("https://raw.githubusercontent.com/web-arena-x/webarena/"
                "main/config_files/test.raw.json")

# WebArenaInstance requires all seven WA_* vars even for a single-site run;
# every site other than the one under test gets an unreachable dummy.
DUMMY_SITES = {
    "WA_GITLAB": "http://dummy.localhost:8023",
    "WA_SHOPPING": "http://dummy.localhost:7770",
    "WA_SHOPPING_ADMIN": "http://dummy.localhost:7780/admin",
    "WA_REDDIT": "http://dummy.localhost:9999",
    "WA_WIKIPEDIA": "http://dummy.localhost:8888",
    "WA_MAP": "http://dummy.localhost:3000",
    "WA_HOMEPAGE": "http://dummy.localhost:4399",
}
SITES = ("gitlab", "shopping", "shopping_admin", "reddit", "wikipedia", "map")


def set_wa_env(site: str, site_url: str) -> None:
    """Must run before importing browsergym.webarena."""
    os.environ[f"WA_{site.upper()}"] = site_url.rstrip("/")
    for key, val in DUMMY_SITES.items():
        os.environ.setdefault(key, val)
    os.environ.setdefault("WA_FULL_RESET", "")


def site_task_ids(site: str, cache: Path) -> list[int]:
    """Task ids whose only site is `site` (multi-site tasks are skipped)."""
    if not cache.exists():
        import requests
        resp = requests.get(TEST_RAW_URL, timeout=60)
        resp.raise_for_status()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(resp.text)
    configs = json.loads(cache.read_text())
    return sorted(c["task_id"] for c in configs if c.get("sites") == [site])


class NoThinkOpenAILLM:
    """OpenAILLM that asks vLLM to disable Qwen3.5's default thinking mode."""

    def __new__(cls, *, disable_thinking: bool, **kwargs):
        from hsge.backends import OpenAILLM

        class _LLM(OpenAILLM):
            def _create_with_retry(self, **ckwargs):
                if disable_thinking:
                    extra = ckwargs.setdefault("extra_body", {})
                    extra["chat_template_kwargs"] = {"enable_thinking": False}
                return super()._create_with_retry(**ckwargs)

        return _LLM(**kwargs)


def make_task_browser(task_id: int, headless: bool, timeout_ms: int):
    """WebArenaBrowser facade over the scored browsergym/webarena.<id> env."""
    import gymnasium as gym
    import browsergym.webarena  # noqa: F401  registers browsergym/webarena.<id>
    from browsergym.core.action.highlevel import HighLevelActionSet

    from hsge.webarena.browser import WebArenaBrowser

    class TaskBrowser(WebArenaBrowser):
        def __init__(self):  # deliberately does NOT call super().__init__
            self.action_set = HighLevelActionSet(
                subsets=["chat", "bid", "infeas", "nav", "tab"],
                strict=False, multiaction=False)
            self.env = gym.make(
                f"browsergym/webarena.{task_id}",
                headless=headless,
                timeout=timeout_ms,
                wait_for_user_message=False,
                action_mapping=self.action_set.to_python_code,
            )
            self._last_obs = None
            self.terminated = False
            self.reward = 0.0
            self.goal = ""

        def reset(self) -> dict:
            obs, _ = self.env.reset()
            self._last_obs = obs
            self.terminated = False
            goal = obs.get("goal") or ""
            if not goal and obs.get("goal_object"):
                goal = " ".join(part.get("text", "") for part in obs["goal_object"]
                                if isinstance(part, dict))
            self.goal = goal
            return self.observation()

        def act(self, action: str) -> dict:
            self._last_obs, reward, term, trunc, _ = self.env.step(action)
            self.reward += float(reward)
            self.terminated = bool(term or trunc)
            return self.observation()

    return TaskBrowser()


def write_trace(out_dir: Path, task_id: int, goal: str, steps, reward: float,
                stop_reason: str) -> None:
    """Persist what the model actually did, step by step.

    results.jsonl only records the aggregate plus a truncated last_action, which
    is not enough to tell a model that never found the right page from one that
    found it and misread it. The axtree is deliberately left out -- it is ~6 kB
    per step and reproducible by replaying the task.
    """
    trace_dir = out_dir / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    (trace_dir / f"{task_id}.json").write_text(json.dumps({
        "task_id": task_id,
        "goal": goal,
        "reward": reward,
        "stop_reason": stop_reason,
        "steps": [{"i": i, "thought": s.obs_summary, "action": s.action, "url": s.url}
                  for i, s in enumerate(steps)],
    }, ensure_ascii=False, indent=1) + "\n")


def run_task(task_id: int, llm, max_steps: int, headless: bool,
             timeout_ms: int, out_dir: Path | None = None) -> dict:
    from hsge.webarena.agents import Solver

    browser = make_task_browser(task_id, headless, timeout_ms)
    t0 = time.time()
    try:
        browser.reset()
        solver = Solver(llm, max_steps=max_steps, vision=False)
        steps, _, _, _, _, infeasible, stop_reason = solver.solve(browser, browser.goal)
        # Deliver the terminal chat action to the env so the official
        # evaluator can score the answer.
        last_action = steps[-1].action if steps else ""
        if not browser.terminated and (last_action.startswith("send_msg_to_user")
                                       or last_action.startswith("report_infeasible")):
            try:
                browser.act(last_action)
            except Exception as e:  # answer delivery must never lose the episode
                print(f"    [eval] terminal action failed: {e}", file=sys.stderr)
        if out_dir is not None:
            write_trace(out_dir, task_id, browser.goal, steps, browser.reward,
                        stop_reason)
        return {
            "task_id": task_id,
            "goal": browser.goal,
            "reward": browser.reward,
            "success": browser.reward > 0,
            "infeasible_reported": infeasible,
            "stop_reason": stop_reason,
            "n_steps": len(steps),
            "last_action": last_action[:300],
            "elapsed_s": round(time.time() - t0, 1),
        }
    except Exception as e:
        return {
            "task_id": task_id,
            "goal": getattr(browser, "goal", ""),
            "reward": 0.0,
            "success": False,
            "error": f"{type(e).__name__}: {e}"[:500],
            "elapsed_s": round(time.time() - t0, 1),
        }
    finally:
        try:
            browser.env.close()
        except Exception:
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", default="gitlab", choices=SITES,
                    help="WebArena site to evaluate on (default: gitlab)")
    ap.add_argument("--site-url", default=None,
                    help="base URL of the site under test "
                         "(default: the site's own WA_* env var)")
    ap.add_argument("--gitlab-url", default=None,
                    help=argparse.SUPPRESS)  # back-compat alias for --site-url
    ap.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--model", default="qwen35-9b")
    ap.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", "EMPTY"))
    ap.add_argument("--out", required=True, help="output dir for results.jsonl")
    ap.add_argument("--tasks", default=None,
                    help="comma-separated task ids (default: all tasks of --site)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-steps", type=int, default=15)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--timeout-ms", type=int, default=30000)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--keep-thinking", action="store_true",
                    help="do not disable Qwen3.5's thinking mode")
    ap.add_argument("--no-resume", action="store_true",
                    help="re-run tasks already present in results.jsonl")
    args = ap.parse_args()

    site_url = (args.site_url or args.gitlab_url
                or os.environ.get(f"WA_{args.site.upper()}"))
    if not site_url:
        ap.error(f"--site-url (or WA_{args.site.upper()}) is required")
    set_wa_env(args.site, site_url)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"

    if args.tasks:
        task_ids = [int(t) for t in args.tasks.split(",")]
    else:
        task_ids = site_task_ids(args.site, out_dir.parent / "test.raw.json")
    if args.limit:
        task_ids = task_ids[:args.limit]

    done: set[int] = set()
    if results_path.exists() and not args.no_resume:
        for line in results_path.read_text().splitlines():
            try:
                done.add(json.loads(line)["task_id"])
            except Exception:
                pass
    todo = [t for t in task_ids if t not in done]
    print(f"{args.site} tasks: {len(task_ids)} selected, {len(done)} already done, "
          f"{len(todo)} to run -> {results_path}")

    llm = NoThinkOpenAILLM(disable_thinking=not args.keep_thinking,
                           model=args.model, base_url=args.base_url,
                           api_key=args.api_key, temperature=args.temperature)

    n_success = sum(1 for line in (results_path.read_text().splitlines()
                                   if results_path.exists() else [])
                    if json.loads(line).get("success"))
    for i, task_id in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] webarena.{task_id} ...", flush=True)
        result = run_task(task_id, llm, args.max_steps,
                          headless=not args.headed, timeout_ms=args.timeout_ms,
                          out_dir=out_dir)
        n_success += bool(result.get("success"))
        with open(results_path, "a") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
        status = "OK " if result.get("success") else ("ERR" if result.get("error") else "fail")
        print(f"    {status} reward={result.get('reward')} "
              f"steps={result.get('n_steps', '-')} {result.get('elapsed_s')}s"
              + (f" error={result['error'][:120]}" if result.get("error") else ""))

    total = len(done) + len(todo)
    summary = {"site": args.site, "model": args.model, "base_url": args.base_url,
               "n_tasks": total, "n_success": n_success,
               "success_rate": round(n_success / total, 4) if total else 0.0}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\nsuccess rate: {n_success}/{total} = {summary['success_rate']:.1%}")


if __name__ == "__main__":
    main()
