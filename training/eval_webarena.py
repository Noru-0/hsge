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
import contextlib
import json
import os
import signal
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
    """OpenAILLM that disables Qwen3.5's thinking mode and records raw model I/O.

    The recording exists because `complete_json` degrades a malformed response to
    `{}` and reports it only on stderr, so the model's actual output never reaches
    any artifact. That is the one thing you cannot reconstruct afterwards, and it
    is exactly what a 0%-scoring sweep needs explained: a step that ends the
    episode because the model emitted `"action": "click('12\\xa0 Reviews')"` --
    invalid JSON, since JSON has no \\x escape -- is indistinguishable in
    results.jsonl from a step where the model deliberately stopped. That failure
    hit ~8% of episodes in a real smoke run.
    """

    def __new__(cls, *, disable_thinking: bool, **kwargs):
        from hsge.backends import OpenAILLM

        class _LLM(OpenAILLM):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.calls: list[dict] = []
                self._last: dict | None = None

            def _create_with_retry(self, **ckwargs):
                if disable_thinking:
                    extra = ckwargs.setdefault("extra_body", {})
                    extra["chat_template_kwargs"] = {"enable_thinking": False}
                t0 = time.time()
                msg = super()._create_with_retry(**ckwargs)
                choice = msg.choices[0]
                self._last = {
                    "llm_s": round(time.time() - t0, 2),
                    "finish_reason": getattr(choice, "finish_reason", None),
                    "raw": getattr(choice.message, "content", None),
                    "prompt_chars": sum(len(str(m.get("content", "")))
                                        for m in ckwargs.get("messages", [])),
                }
                return msg

            def complete_json(self, system, prompt, **kw):
                self._last = None
                out = super().complete_json(system, prompt, **kw)
                rec = dict(self._last or {"llm_s": None, "raw": None,
                                          "finish_reason": None, "prompt_chars": None})
                # An empty dict means complete_json could not use the response:
                # either unparseable JSON, a non-dict top-level value, or a
                # refusal/content-filter with content=None. `raw` tells them apart.
                rec["parsed_ok"] = bool(out)
                rec["action"] = out.get("action") if isinstance(out, dict) else None
                self.calls.append(rec)
                return out

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
            # WebArena's validate() runs on EVERY step, not once per episode, so
            # the per-step reward is free information: it shows whether the agent
            # ever satisfied the goal and then navigated away from it, which a
            # final reward of 0 hides completely.
            self.act_trace: list[dict] = []

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
            t0 = time.time()
            url_before = (self._last_obs or {}).get("url", "")
            try:
                self._last_obs, reward, term, trunc, _ = self.env.step(action)
            except Exception as e:
                self.act_trace.append({"action": action, "url_before": url_before,
                                       "act_s": round(time.time() - t0, 2),
                                       "raised": f"{type(e).__name__}: {e}"[:300]})
                raise
            self.reward += float(reward)
            self.terminated = bool(term or trunc)
            # last_action_error is BrowserGym's own record of an action that failed
            # inside the page (it never raises). Solver reacts to it, but nothing
            # persisted it, so a run of failed clicks looked identical to a run of
            # successful ones in the artifacts.
            self.act_trace.append({
                "action": action,
                "url_before": url_before,
                "url_after": self._last_obs.get("url", ""),
                "step_reward": float(reward),
                "cum_reward": self.reward,
                "terminated": self.terminated,
                "action_error": (self._last_obs.get("last_action_error") or "")[:300],
                "act_s": round(time.time() - t0, 2),
            })
            return self.observation()

    return TaskBrowser()


def write_trace(out_dir: Path, task_id: int, goal: str, steps, reward: float,
                stop_reason: str, llm_calls=None, act_trace=None,
                with_axtree: bool = False, extra: dict | None = None) -> None:
    """Persist everything needed to explain one episode without re-running it.

    results.jsonl records the aggregate plus a truncated last_action, which
    cannot distinguish a model that never found the right page from one that
    found it and misread it, nor either of those from a model whose output was
    unparseable. Three independent records are kept side by side:

    - `steps`    what the Solver accepted: thought + action + resulting URL.
    - `llm_calls` what the model actually emitted, including `raw` and
      `parsed_ok`, so a malformed response is visible instead of silently
      becoming an episode-ending empty action.
    - `act_trace` what the browser did with each action: per-step reward (the
      official evaluator runs every step), `action_error` when the action failed
      inside the page, and the URL either side of it.

    They are deliberately NOT zipped into one array: the three are not 1:1. A
    step can be dropped by the Solver, the end-of-episode wrap-up call produces
    an LLM call with no step, and the terminal chat action is replayed into the
    env after solving, producing an act with no step. Aligning them by index
    would invent a correspondence that does not exist; `n_steps`/`n_llm_calls`/
    `n_acts` are recorded so a mismatch is visible rather than hidden.

    The axtree is opt-in (`--trace-axtree`): ~6 kB per step, ~31 MB for a full
    187-task site. Worth it when the question is *why* the model misread a page,
    wasteful when it is merely *whether* it got there.
    """
    trace_dir = out_dir / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    step_rows = []
    for i, s in enumerate(steps):
        row = {"i": i, "thought": s.obs_summary, "action": s.action, "url": s.url}
        if with_axtree:
            row["axtree"] = s.axtree
        else:
            row["axtree_chars"] = len(s.axtree or "")
        step_rows.append(row)
    payload = {
        "task_id": task_id,
        "goal": goal,
        "reward": reward,
        "stop_reason": stop_reason,
        "n_steps": len(step_rows),
        "n_llm_calls": len(llm_calls or []),
        "n_acts": len(act_trace or []),
        "steps": step_rows,
        "llm_calls": list(llm_calls or []),
        "act_trace": list(act_trace or []),
    }
    payload.update(extra or {})
    (trace_dir / f"{task_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def write_summary(out_dir: Path, results_path: Path, args, task_ids: list[int],
                  aborted: bool = False) -> dict:
    """Recompute summary.json from results.jsonl and report it.

    Recomputed from the file rather than from an in-loop counter because the file
    is the one source that survives an interrupted sweep, and `prune_errored()`
    has already guaranteed one row per task_id. Called on the abort path too, so
    a sweep stopped by the consecutive-error guard still leaves a readable
    summary instead of a stale one from the previous invocation.

    Two denominators, both reported, because they answer different questions:
    `success_rate` is over the site's FULL official task set -- the figure
    comparable to published WebArena numbers -- while `success_rate_attempted` is
    over what actually got scored. They diverge whenever a sweep is incomplete,
    which is the expected case for four 6-hour sweeps behind ephemeral tunnels,
    and quoting only the attempted rate would flatter an unfinished run.
    """
    rows = [json.loads(line) for line in
            results_path.read_text(encoding="utf-8").splitlines() if line.strip()] \
        if results_path.exists() else []
    n_scored = sum(1 for r in rows if not r.get("error"))
    n_errored = sum(1 for r in rows if r.get("error"))
    n_success = sum(1 for r in rows if r.get("success"))
    n_site_tasks = len(task_ids)
    summary = {
        "site": args.site, "model": args.model, "base_url": args.base_url,
        # serve_vllm.sh deliberately serves every model under the same name
        # ("qwen35-9b") so eval commands don't change between runs -- which means
        # `model` above cannot tell a baseline apart from a finetuned run. Only
        # the output directory could, and that does not survive being copied or
        # quoted. Record it explicitly.
        "variant": args.variant,
        "n_site_tasks": n_site_tasks,
        "n_scored": n_scored,
        "n_errored": n_errored,
        "n_success": n_success,
        "success_rate": round(n_success / n_site_tasks, 4) if n_site_tasks else 0.0,
        "success_rate_attempted": round(n_success / n_scored, 4) if n_scored else 0.0,
        "complete": n_scored == n_site_tasks and n_errored == 0,
        "aborted_on_consecutive_errors": aborted,
        "judge_model_override": os.environ.get("WA_JUDGE_MODEL_OVERRIDE", ""),
        "n_unparsed_llm": sum(r.get("n_unparsed_llm", 0) or 0 for r in rows),
        "n_action_errors": sum(r.get("n_action_errors", 0) or 0 for r in rows),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                          encoding="utf-8")
    print(f"\nsuccess rate: {n_success}/{n_site_tasks} = {summary['success_rate']:.1%}"
          f"  (scored {n_scored}, errored {n_errored})")
    if summary["n_unparsed_llm"]:
        # A rising count means the endpoint or chat template regressed, not that
        # the model got worse -- worth seeing without opening a single trace.
        print(f"unparseable model responses: {summary['n_unparsed_llm']} "
              f"(see traces/*.json -> llm_calls[].raw)")
    if not summary["complete"]:
        print("INCOMPLETE: re-run the same command to finish; errored tasks are "
              "requeued automatically.")
    if summary["judge_model_override"]:
        print(f"NOTE: WebArena's LLM judge was overridden to "
              f"{summary['judge_model_override']!r} -- disclose this when reporting.")
    return summary


def n_llm_judged_tasks(site: str, cache: Path, task_ids: list[int]) -> int:
    """How many of `task_ids` are scored by WebArena's LLM judge.

    `llm_fuzzy_match` calls OpenAI, so those tasks need a real `OPENAI_API_KEY`;
    without one it raises, BrowserGym's `validate()` only catches AssertionError,
    and the task is recorded as errored -- a silent guaranteed 0. Counted per
    site because it is wildly uneven: shopping 15, shopping_admin 20, gitlab 5,
    reddit 0, so a keyless reddit sweep is perfectly valid while a keyless
    shopping sweep understates by up to 8%.

    `fuzzy_match: "N/A"` does NOT count: WebArena special-cases it to an exact
    match on the string "N/A" and never calls the model. 70 of the 655 tasks
    carry the key; only 40 actually reach the judge.
    """
    configs = json.loads(cache.read_text()) if cache.exists() else []
    wanted = set(task_ids)
    n = 0
    for c in configs:
        if c.get("task_id") not in wanted:
            continue
        ref = (c.get("eval") or {}).get("reference_answers") or {}
        if not isinstance(ref, dict) or "fuzzy_match" not in ref:
            continue
        vals = ref["fuzzy_match"]
        vals = vals if isinstance(vals, list) else [vals]
        if any(str(v).strip() != "N/A" for v in vals):
            n += 1
    return n


def prune_errored(results_path: Path) -> tuple[set[int], int]:
    """Rewrite results.jsonl keeping only rows that actually scored a task, and
    return (completed task ids, number of errored rows dropped).

    A row carrying `error` is an infrastructure failure -- a Cloudflare tunnel
    blip, a vLLM restart, a Playwright navigation timeout -- not a judgement
    about the model. Treating it as "done" (which is what building the resume
    set from every row did) turns one blip into a permanent 0. On a sweep this
    long, run through quick tunnels, that is not hypothetical: 55 of 180 rows in
    `training/artifacts/eval_results/base/results.jsonl` carry `error`.

    The exception is `timed_out`, which is kept and never retried. Requeueing
    assumes the next attempt might score; a task that hangs *deterministically*
    breaks that assumption and livelocks the sweep instead, since a hang writes
    no row and resume therefore puts it straight back at the head of the queue.
    reddit burned ~35 minutes and three attempts on webarena.724 that way before
    it was excluded by hand. The row is still `error`, so the task counts as
    unscored rather than as a 0 -- and it can be re-run deliberately with
    `--tasks` once whatever hangs is understood.

    Rewriting rather than merely skipping matters because results.jsonl is
    append-only: leaving the errored row in place and re-running the task would
    append a SECOND row for the same task_id, and both `total` and the success
    count are computed over rows, so every retry would quietly corrupt the
    denominator. Rewriting keeps the file at exactly one row per task_id.
    """
    rows: dict[int, dict] = {}
    n_errored = 0
    for line in results_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            task_id = row["task_id"]
        except Exception:
            continue                      # unparseable line: drop, nothing to keep
        if row.get("error") and not row.get("timed_out"):
            n_errored += 1
            rows.pop(task_id, None)       # a later clean row wins; a later error clears
            continue
        rows[task_id] = row               # last clean row for a task wins
    if n_errored:
        results_path.replace(results_path.with_suffix(".jsonl.bak"))
        with open(results_path, "w", encoding="utf-8") as f:
            for task_id in sorted(rows):
                f.write(json.dumps(rows[task_id], ensure_ascii=False) + "\n")
    return set(rows), n_errored


class TaskTimeout(Exception):
    """One task exceeded its wall-clock budget (see `--task-timeout-s`)."""


@contextlib.contextmanager
def _wall_clock_budget(seconds: int):
    """Raise `TaskTimeout` in this thread after `seconds`; 0 disables.

    SIGALRM rather than a watchdog thread because the hang being bounded is a
    *blocking* one -- the main thread parked in `ep_poll` on Playwright's driver
    pipe, with an idle browser and no CPU. A thread could observe that but not
    interrupt it. Under PEP 475 the interrupted syscall runs Python-level signal
    handlers before retrying, so raising here propagates out of the blocked call.

    Main-thread only, which is where the sweep's task loop runs.
    """
    if not seconds:
        yield
        return

    def _fire(signum, frame):
        raise TaskTimeout(f"no progress for {seconds}s")

    prev = signal.signal(signal.SIGALRM, _fire)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prev)


def run_task(task_id: int, llm, max_steps: int, headless: bool,
             timeout_ms: int, out_dir: Path | None = None,
             with_axtree: bool = False, task_timeout_s: int = 0) -> dict:
    from hsge.webarena.agents import Solver

    browser = make_task_browser(task_id, headless, timeout_ms)
    t0 = time.time()
    if hasattr(llm, "calls"):
        llm.calls.clear()                      # per-task, not per-sweep
    steps: list = []
    terminal_delivery = ""
    try:
        # The budget covers everything that touches the browser -- env setup
        # included, which is where the observed hang was and which BrowserGym's
        # own 30s action timeout does not bound. Tracing and the return value
        # are built after the alarm is cleared.
        with _wall_clock_budget(task_timeout_s):
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
                    terminal_delivery = "delivered"
                except Exception as e:  # answer delivery must never lose the episode
                    terminal_delivery = f"failed: {type(e).__name__}: {e}"[:300]
                    print(f"    [eval] terminal action failed: {e}", file=sys.stderr)
            else:
                terminal_delivery = ("already_terminated" if browser.terminated
                                     else "not_a_terminal_action")
        if out_dir is not None:
            write_trace(out_dir, task_id, browser.goal, steps, browser.reward,
                        stop_reason, llm_calls=getattr(llm, "calls", None),
                        act_trace=getattr(browser, "act_trace", None),
                        with_axtree=with_axtree,
                        extra={"terminal_delivery": terminal_delivery,
                               "max_steps": max_steps})
        return {
            "task_id": task_id,
            "goal": browser.goal,
            "reward": browser.reward,
            "success": browser.reward > 0,
            "infeasible_reported": infeasible,
            "stop_reason": stop_reason,
            "n_steps": len(steps),
            # Counted here because it is the cheapest sweep-wide health signal:
            # a rising unparseable rate means the endpoint or template regressed,
            # not that the model got worse.
            "n_unparsed_llm": sum(1 for c in getattr(llm, "calls", [])
                                  if not c.get("parsed_ok")),
            "n_action_errors": sum(1 for a in getattr(browser, "act_trace", [])
                                   if a.get("action_error")),
            "terminal_delivery": terminal_delivery,
            "last_action": last_action[:300],
            "elapsed_s": round(time.time() - t0, 1),
        }
    except Exception as e:
        # An errored task is the case most in need of a trace, so write one here
        # too -- partial steps and the raw LLM calls are what explain the failure.
        if out_dir is not None:
            try:
                write_trace(out_dir, task_id, getattr(browser, "goal", ""), steps,
                            getattr(browser, "reward", 0.0), "error",
                            llm_calls=getattr(llm, "calls", None),
                            act_trace=getattr(browser, "act_trace", None),
                            with_axtree=with_axtree,
                            extra={"error": f"{type(e).__name__}: {e}"[:500],
                                   "terminal_delivery": terminal_delivery})
            except Exception:
                pass                            # tracing must never mask the real error
        return {
            "task_id": task_id,
            "goal": getattr(browser, "goal", ""),
            "reward": 0.0,
            "success": False,
            "error": f"{type(e).__name__}: {e}"[:500],
            # Distinguishes "retry this" from "this hangs" -- prune_errored()
            # requeues the first and keeps the second.
            "timed_out": isinstance(e, TaskTimeout),
            "n_steps": len(steps),
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
    ap.add_argument("--variant", default="",
                    help="which model this run measures: 'base' or 'finetuned'. "
                         "Recorded in summary.json; does not affect the run.")
    ap.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", "EMPTY"))
    ap.add_argument("--out", required=True, help="output dir for results.jsonl")
    ap.add_argument("--tasks", default=None,
                    help="comma-separated task ids (default: all tasks of --site)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-steps", type=int, default=15)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--timeout-ms", type=int, default=30000)
    ap.add_argument("--task-timeout-s", type=int, default=900, metavar="S",
                    help="abandon a task after S seconds of wall clock and record "
                         "it as timed out (0 disables). Bounds a hang that no "
                         "other guard catches: --timeout-ms bounds one ACTION and "
                         "--max-consecutive-errors counts errors, but a task "
                         "parked in Playwright produces neither. Default 900s is "
                         "~3x the longest legitimate task measured (304s, p95 170s). "
                         "A timed-out task is never retried -- see prune_errored()")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--keep-thinking", action="store_true",
                    help="do not disable Qwen3.5's thinking mode")
    ap.add_argument("--no-resume", action="store_true",
                    help="re-run tasks already present in results.jsonl")
    ap.add_argument("--allow-missing-judge-key", action="store_true",
                    help="run even when the site has llm_fuzzy_match tasks and "
                         "OPENAI_API_KEY is unset (those tasks will score 0)")
    ap.add_argument("--trace-axtree", action="store_true",
                    help="also store each step's accessibility tree in the trace "
                         "(~6 kB/step; needed to tell 'never found the page' from "
                         "'found it and misread it')")
    ap.add_argument("--max-consecutive-errors", type=int, default=5, metavar="N",
                    help="stop with exit code 3 after N tasks in a row error out "
                         "(0 disables). Distinguishes dead infrastructure from a "
                         "weak model: a dropped tunnel would otherwise burn the "
                         "whole sweep producing error rows")
    args = ap.parse_args()

    site_url = (args.site_url or args.gitlab_url
                or os.environ.get(f"WA_{args.site.upper()}"))
    if not site_url:
        ap.error(f"--site-url (or WA_{args.site.upper()}) is required")
    set_wa_env(args.site, site_url)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"

    cache = out_dir.parent / "test.raw.json"
    if args.tasks:
        task_ids = [int(t) for t in args.tasks.split(",")]
        site_task_ids(args.site, cache)          # ensure the cache exists for the check below
    else:
        task_ids = site_task_ids(args.site, cache)
    if args.limit:
        task_ids = task_ids[:args.limit]

    n_judged = n_llm_judged_tasks(args.site, cache, task_ids)
    if n_judged and not os.environ.get("OPENAI_API_KEY"):
        msg = (f"{n_judged} of the {len(task_ids)} selected {args.site} tasks are scored "
               f"by WebArena's LLM judge (llm_fuzzy_match), which needs OPENAI_API_KEY "
               f"in the environment. Without it every one of them errors out and scores "
               f"0 with no other symptom.")
        if not args.allow_missing_judge_key:
            raise SystemExit(f"ERROR: {msg}\nSet OPENAI_API_KEY, or pass "
                             f"--allow-missing-judge-key to accept the skew knowingly.")
        print(f"WARNING: {msg}\nProceeding because --allow-missing-judge-key was given; "
              f"the reported success rate is a LOWER BOUND.")

    done: set[int] = set()
    n_requeued = 0
    if results_path.exists() and not args.no_resume:
        done, n_requeued = prune_errored(results_path)
        if n_requeued:
            print(f"requeued {n_requeued} errored task(s) from a previous run "
                  f"(kept a .bak); they will be retried")
    todo = [t for t in task_ids if t not in done]
    print(f"{args.site} tasks: {len(task_ids)} selected, {len(done)} already done, "
          f"{len(todo)} to run -> {results_path}")

    llm = NoThinkOpenAILLM(disable_thinking=not args.keep_thinking,
                           model=args.model, base_url=args.base_url,
                           api_key=args.api_key, temperature=args.temperature)

    n_success = sum(1 for line in (results_path.read_text().splitlines()
                                   if results_path.exists() else [])
                    if json.loads(line).get("success"))
    n_consecutive_errors = 0
    for i, task_id in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] webarena.{task_id} ...", flush=True)
        result = run_task(task_id, llm, args.max_steps,
                          headless=not args.headed, timeout_ms=args.timeout_ms,
                          out_dir=out_dir, with_axtree=args.trace_axtree,
                          task_timeout_s=args.task_timeout_s)
        n_success += bool(result.get("success"))
        with open(results_path, "a") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
        status = "OK " if result.get("success") else ("ERR" if result.get("error") else "fail")
        # Running tally on every line: with four sweeps in flight the cheapest
        # health check is `tail -1` on each log, and it must be self-contained.
        print(f"    {status} reward={result.get('reward')} "
              f"steps={result.get('n_steps', '-')} {result.get('elapsed_s')}s "
              f"| {n_success}/{len(done) + i} so far"
              + (f" error={result['error'][:120]}" if result.get("error") else ""))

        # A run of errors means the site, the tunnel or the endpoint is gone --
        # tasks then fail in seconds and the sweep would chew through the whole
        # list writing error rows. They would all be requeued on the next run, so
        # nothing is lost, but hours are. Exit 3 so the supervisor and the status
        # script can tell "infrastructure down" from "model scored badly".
        n_consecutive_errors = n_consecutive_errors + 1 if result.get("error") else 0
        if args.max_consecutive_errors and n_consecutive_errors >= args.max_consecutive_errors:
            print(f"\nABORT: {n_consecutive_errors} tasks in a row errored -- treating "
                  f"this as infrastructure failure, not a model result. Last error: "
                  f"{result.get('error')}\nCheck the site/tunnel and re-run the same "
                  f"command; errored tasks are requeued automatically.", file=sys.stderr)
            write_summary(out_dir, results_path, args, task_ids, aborted=True)
            raise SystemExit(3)

    write_summary(out_dir, results_path, args, task_ids)


if __name__ == "__main__":
    main()
