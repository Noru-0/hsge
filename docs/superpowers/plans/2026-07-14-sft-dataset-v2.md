# SFT Dataset v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gap between HSGE's collected trajectories and SOTA SFT practice: make `build_sft_dataset.py`'s prompt byte-for-byte consistent with the live Solver, add cross-step linkage (trajectory/step metadata, outcome+thought history, segmentation-derived subgoals), filter false-positive "success" episodes with an LLM judge, and re-annotate thoughts into a structured state/subgoal/reflection/completion-check template — all without inventing a live inference-time dependency the collection pipeline can't supply itself.

**Architecture:** Six tasks, strictly ordered (each depends on the previous landing first):
1. `hsge/webarena/agents.py` / `browser.py` — runtime action space (`press`, tab ops) and axtree-truncation hygiene. This runs first because Task 2 imports the runtime's system prompt verbatim.
2. `build_sft_dataset.py` — core rewrite: import `SOLVER_SYS` instead of duplicating it, add URL + outcome/thought-annotated history (via a new shared `step_outcome` extracted from `Solver.solve`), strip `[INFO]/[NAV]/[MOD]` goal tags, add `trajectory_id`/`step_index`/`total_steps` per example, exclude steps whose action errored at collection time from both targets and history.
3. `build_sft_dataset.py` — include `infeasible` episodes (teaches `report_infeasible` as a real target, not just a runtime-only escape hatch).
4. `judge_episodes.py` (new) — LLM judge re-checks every declared-success episode against its final state; `build_sft_dataset.py` gets `--require-judge`.
5. `reannotate_thoughts.py` (new) — rewrites `thought` → `thought_v2` per step using (a) an offline replay of the existing `segment_trajectory()` for subgoal text and segment-boundary detection (no new inference-time dependency: the subgoal only ever appears in the assistant *target*, never the prompt) and (b) one LLM call per step for a terse state assessment + reflection-on-the-prior-action + (final step only) a completion check.
6. Integration: stats reporting, `.claude/rules/architecture.md` + changelog updates, and a real-data smoke test against a copy of `outputs/wa_run_09`.

Subgoal/operator text lives in the assistant target (Task 5), never in the user prompt — an earlier version of this plan considered putting `CURRENT SUBGOAL:` in the input, but that would require a retrieval/grounding pipeline at inference time that doesn't exist; putting it in the target lets the fine-tuned model learn to *generate* subgoal-aware reasoning without any new serving-time dependency. Predicates-as-input + retrieval is explicitly deferred (see Global Constraints).

**Tech Stack:** Python 3.10+, no new dependencies (`openai`, `browsergym-core` already in `requirements.txt`; `browsergym-core==0.13.3` is confirmed installed in the `go-browse` conda env and its `HighLevelActionSet` action subsets were inspected directly to ground this plan's action-space claims). Tests follow the repo's standalone-or-pytest pattern (`if __name__ == "__main__":` runner + pytest-compatible).

## Global Constraints

- Run everything from the repo root; activate the conda env first: `conda activate go-browse`.
- All code/comments/commit messages in English.
- Commit after each task; end commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` (exact trailer).
- Mock pipeline stays deterministic; the full suite (`python -m pytest hsge/tests/ -q`) must be green at the end of every task.
- **`hsge.webarena.agents.SOLVER_SYS`/`ACTIONS_DOC` become the single source of truth for the action-space text.** `build_sft_dataset.py` imports `SOLVER_SYS` directly (`from hsge.webarena.agents import SOLVER_SYS as SYSTEM`) — it must never hold its own copy of the action list again. This is what makes "parity" permanent instead of a one-time sync.
- **`step_outcome(pre_url, pre_axtree, url, axtree) -> str`** (added to `hsge/webarena/agents.py` in Task 2) is the single source of truth for "what happened after this action" — used by the live `Solver.solve`, `build_sft_dataset.py`, and `reannotate_thoughts.py`. Never reimplement the url/axtree comparison inline a second time.
- **New offline scripts (`judge_episodes.py`, `reannotate_thoughts.py`) are additive/non-destructive.** They only ADD fields to existing `episode_meta.json` (`outcome.judge_verified`, `outcome.judge_reason`) / `episode.jsonl` (`thought_v2` per step record) — they never remove or overwrite `success`, `thought`, or any other original field. Re-running either script is idempotent (last write wins, no accumulation). This keeps the original collection artifact intact as the audit trail.
- **Backward compatibility:** `build_sft_dataset.py` must keep working on OLD run dirs that have none of the new fields — no `judge_verified` (only matters if `--require-judge` is passed), no `thought_v2` (falls back to `thought`), no `trajectory_id`/tag-stripping issues (these are unconditional and don't depend on new upstream fields).
- **No new AGENT_ROLES entries in `run_webarena.py`.** `judge_episodes.py` / `reannotate_thoughts.py` are standalone offline scripts (same pattern as the existing `replay_segmentation.py`): they resolve their own LLM via `run_webarena._effective_llm_config(ns, cfg["llm"], "<role>")` with new role strings `"episode_judge"` / `"thought_reannotator"` that don't need to be registered in `AGENT_ROLES` — that tuple only drives the *live* `WebArenaExplorer`'s agent roster, and `_effective_llm_config` doesn't validate its `role` argument against it.
- **`build_sft_dataset.py` never calls an LLM.** It stays a pure data transformation (parity/history/tags/metadata/filtering). All LLM-backed enrichment (judging, re-annotation, segmentation) lives in the two new standalone scripts that run *before* it, consistent with the existing separation between collection (`run_webarena.py`) and dataset assembly.
- **Known, accepted gap:** the live Solver's `LAST ACTION ERROR: <text>` prompt line is NOT reconstructed offline. The raw exception text is only ever inlined as a suffix on `obs_summary` (`"... [action error: ...]"`), not persisted as its own field, so recovering it verbatim would be lossy guesswork. Task 2 instead **excludes** the errored step from becoming a training target or entering later steps' history (see `_is_error_step`) — the recovery step right after it is still a valid target, just without a fabricated error line in its prompt.
- **`hsge/webarena/browser.py` changes (Task 1: `filter_visible_only=True`, `"tab"` action subset) are not unit-testable** — they require a live Playwright/BrowserGym page. Verify them manually: `python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2` only exercises wiring (the dry run uses `_FakeBrowser`, not `WebArenaBrowser`); if you have a live WebArena instance, `python run_webarena.py --read-only --max-nodes 1 --max-steps 3` and eyeball `outputs/<run>/episodes/ep_0000/page_state/step_000_axtree.txt` for length/content.
- **Explicitly out of scope** (do not implement, note as future work in Task 6's doc update instead): (a) predicates/operators as *input* to the Solver prompt (would need a retrieval/grounding pipeline at serving time — no such pipeline exists); (b) multi-turn trajectory packing (one training example per whole trajectory instead of per step) — a real gain but a bigger, separate architectural change; (c) DAgger-style on-policy correction data; (d) adding `scroll`/`hover`/`goto`-restriction changes — `scroll` dispatches a wheel event but does not change what `flatten_axtree_to_str` returns (BrowserGym's axtree is not viewport-scoped), so it would not fix the truncation problem Task 1 addresses differently (visible-only filtering + an explicit truncation marker).

---

### Task 1: Runtime action space — `press`, tab ops, axtree truncation hygiene

**Files:**
- Modify: `hsge/webarena/agents.py` (`ACTIONS_DOC`, `SOLVER_SYS`, new `_AXTREE_CAP`/`_cap_axtree`, `PageExplorer.propose`, `Solver.solve`)
- Modify: `hsge/webarena/browser.py` (`HighLevelActionSet` subsets, `observation()`)
- Test: `hsge/tests/test_solver.py`, `hsge/tests/test_page_explorer.py`

**Interfaces:**
- Produces: `hsge.webarena.agents._cap_axtree(axtree: str) -> str` and module constant `_AXTREE_CAP = 6000` — Task 2 does not touch these but must not reintroduce a raw `[:6000]` slice anywhere in `build_sft_dataset.py`.
- `ACTIONS_DOC` now documents `press('bid','key_comb')`, `new_tab()`, `tab_focus(index)`, `tab_close()` in addition to the existing 7 actions.

- [ ] **Step 1: Write the failing tests**

In `hsge/tests/test_solver.py`, add the import and new tests (append at the end of the file, after the existing test functions but before any `if __name__ ==` block if present — check the file first; there is none per the existing content, so just append):

```python
from hsge.webarena.agents import ACTIONS_DOC, _AXTREE_CAP, _cap_axtree


def test_actions_doc_documents_press_and_tab_ops():
    assert "press(" in ACTIONS_DOC
    assert "new_tab()" in ACTIONS_DOC
    assert "tab_focus(" in ACTIONS_DOC
    assert "tab_close()" in ACTIONS_DOC


def test_cap_axtree_passes_short_text_through_unchanged():
    assert _cap_axtree("short tree") == "short tree"


def test_cap_axtree_marks_truncation_and_preserves_prefix():
    long_tree = "x" * (_AXTREE_CAP + 500)
    capped = _cap_axtree(long_tree)
    assert capped.startswith("x" * 100)
    assert "TRUNCATED" in capped
    assert "500" in capped   # reports how many chars were cut


def test_cap_axtree_handles_empty_and_none():
    assert _cap_axtree("") == ""
    assert _cap_axtree(None) == ""
```

In `hsge/tests/test_page_explorer.py`, append:

```python
class _PromptCapturingLLM:
    def __init__(self):
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        return {"tasks": []}


def test_propose_truncates_long_axtree_with_marker():
    llm = _PromptCapturingLLM()
    explorer = PageExplorer(llm)
    long_axtree = "y" * 7000

    explorer.propose({"url": "http://x", "axtree": long_axtree})

    assert "TRUNCATED" in llm.prompts[0]
    assert len(llm.prompts[0]) < 7000 + 200   # not the raw 7000 chars plus a small prompt overhead
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_solver.py hsge/tests/test_page_explorer.py -q`
Expected: FAIL — `ImportError: cannot import name '_cap_axtree'` / `AssertionError` on the ACTIONS_DOC content checks.

- [ ] **Step 3: Implement the action-space and truncation changes**

In `hsge/webarena/agents.py`, replace `ACTIONS_DOC`:

```python
ACTIONS_DOC = ("Allowed actions (return exactly one): click('bid'), "
               "fill('bid','text'), select_option('bid','opt'), "
               "press('bid','key_comb') -- e.g. press('12','Enter') to submit a "
               "search box or form when there is no separate submit button, "
               "goto('url'), go_back(), new_tab(), tab_focus(index), tab_close(), "
               "send_msg_to_user('done message'), "
               "report_infeasible('reason') -- report_infeasible ONLY when the "
               "task cannot be done on this site/page.")
```

Add the truncation helper right after `READONLY_NOTE` (before `class PageExplorer`):

```python
_AXTREE_CAP = 6000


def _cap_axtree(axtree: str) -> str:
    """Truncate axtree text to _AXTREE_CAP chars, appending an explicit
    marker when content was cut. Silently chopping the tree would let the
    model mistake a truncated view for the complete page; the marker at
    least tells it more content exists. Note: there is no scroll action
    that would change what flatten_axtree_to_str returns here -- BrowserGym's
    axtree is not viewport-scoped, so scrolling wouldn't fix truncation
    (see WebArenaBrowser.observation() for the filter_visible_only change
    that reduces how often this cap is even hit)."""
    text = axtree or ""
    if len(text) <= _AXTREE_CAP:
        return text
    return text[:_AXTREE_CAP] + f"\n... [TRUNCATED: {len(text) - _AXTREE_CAP} more characters not shown]"
```

In `PageExplorer.propose`, replace the prompt line:

```python
        prompt = f"URL: {obs['url']}\n\nPAGE:\n{_cap_axtree(obs['axtree'])}"
```

In `Solver.solve`, replace both occurrences of `obs['axtree'][:6000]` (main loop prompt and the wrap-up prompt) with `_cap_axtree(obs['axtree'])`. The two lines become:

```python
            prompt = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n"
                      + ("\n".join(recent) or "(none)")
                      + (f"\n\nLAST ACTION ERROR: {last_error}" if last_error else "")
                      + repeat_warning
                      + f"\n\nURL: {obs['url']}\n\nPAGE:\n{_cap_axtree(obs['axtree'])}")
```

and, in the wrap-up block:

```python
            wrap_prompt = (f"GOAL: {goal}\n\nACTIONS TAKEN:\n"
                           + ("\n".join(recent) or "(none)")
                           + f"\n\nURL: {obs['url']}\n\nPAGE:\n{_cap_axtree(obs['axtree'])}"
                           + "\n\nYour action budget is exhausted. If the goal has "
                             "ALREADY been achieved (e.g. you are on the requested "
                             "page), call send_msg_to_user('done: ...') NOW. If the "
                             "goal cannot be achieved, call report_infeasible('why'). "
                             "Answer with one of those two actions only.")
```

In `hsge/webarena/browser.py`, change the action set:

```python
        self.action_set = HighLevelActionSet(
            subsets=["chat", "bid", "infeas", "nav", "tab"], strict=False, multiaction=False)
```

and `observation()`'s `flatten_axtree_to_str` call:

```python
    def observation(self) -> dict:
        from browsergym.utils.obs import flatten_axtree_to_str
        obs = self._last_obs or {}
        try:
            axtree = flatten_axtree_to_str(
                obs["axtree_object"], filter_visible_only=True,
                extra_properties=obs.get("extra_element_properties"))
        except Exception:
            axtree = ""
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest hsge/tests/test_solver.py hsge/tests/test_page_explorer.py -q`
Expected: all pass, including the 7 new tests.

- [ ] **Step 5: Run the full suite and the dry run**

Run: `python -m pytest hsge/tests/ -q` — Expected: all pass (no regressions; `browser.py` isn't exercised by the mock/dry-run pipeline).
Run: `python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2` — Expected: completes normally (dry-run wiring only, `_FakeBrowser` doesn't use `browser.py`'s action set).

- [ ] **Step 6: Commit**

```bash
git add hsge/webarena/agents.py hsge/webarena/browser.py \
        hsge/tests/test_solver.py hsge/tests/test_page_explorer.py
git commit -m "Runtime: document press/tab actions, cap axtree with a truncation marker

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `build_sft_dataset.py` — prompt parity, URL, outcome+thought history, tag stripping, trajectory metadata

**Files:**
- Modify: `hsge/webarena/agents.py` (extract `step_outcome`, use it in `Solver.solve`)
- Modify: `build_sft_dataset.py` (rewrite `episode_to_examples`, `load_episodes`, `main`)
- Test: Create `hsge/tests/test_build_sft_dataset.py`; `hsge/tests/test_solver.py` must still pass unchanged (behavior-preserving refactor)

**Interfaces:**
- Produces: `hsge.webarena.agents.step_outcome(pre_url: str, pre_axtree: str, url: str, axtree: str) -> str` — returns `"now at <url>"` / `"page changed"` / `"no change"`, identical semantics to the code it replaces.
- Produces: `build_sft_dataset.SYSTEM` — now `SOLVER_SYS` imported, not a duplicate string.
- Produces: `build_sft_dataset.episode_to_examples(goal: str, steps: list[dict], episode_dir: str, difficulty: int, trajectory_id: str) -> list[dict]` — each example dict gains `trajectory_id: str`, `step_index: int` (the raw `step["index"]` from the jsonl record), `total_steps: int` (`len(steps)`, raw count including any excluded error steps).
- Produces: `build_sft_dataset.load_episodes(path: str)` now yields `(goal, steps, episode_dir, trajectory_id, difficulty, success)` — 6-tuple (was 5).

- [ ] **Step 1: Write the failing tests**

Create `hsge/tests/test_build_sft_dataset.py`:

```python
"""build_sft_dataset.py: prompt parity with the live Solver, outcome- and
prior-thought-annotated history, GOAL tag stripping, trajectory/step
metadata, and exclusion of steps whose action errored at collection time.

Run:  python -m pytest hsge/tests/test_build_sft_dataset.py -q
 (or) PYTHONPATH=. python hsge/tests/test_build_sft_dataset.py
"""
import json
import os
import tempfile

from build_sft_dataset import SYSTEM, episode_to_examples
from hsge.webarena.agents import SOLVER_SYS


def _write_axtree(ep_dir, index, text):
    os.makedirs(os.path.join(ep_dir, "page_state"), exist_ok=True)
    rel = f"page_state/step_{index:03d}_axtree.txt"
    open(os.path.join(ep_dir, rel), "w").write(text)
    return rel


def _step(ep_dir, index, url, axtree, thought, action):
    rel = _write_axtree(ep_dir, index, axtree)
    return {"record_type": "step", "index": index, "url": url,
            "action": json.dumps({"thought": thought, "action": action}),
            "parsed_action": action, "thought": thought,
            "observation": {"axtree_txt": {"path": rel}}}


def test_system_prompt_is_imported_from_solver_not_duplicated():
    assert SYSTEM is SOLVER_SYS
    assert "report_infeasible" in SYSTEM
    assert "go_back" in SYSTEM


def test_goal_tag_is_stripped_but_rest_of_text_preserved():
    ep_dir = tempfile.mkdtemp()
    steps = [_step(ep_dir, 0, "http://x/wiki", "[1] heading 'Wiki'",
                   "arrived", "send_msg_to_user('done')")]

    examples = episode_to_examples("[MOD] Edit the page by clicking 'Edit page'",
                                    steps, ep_dir, difficulty=1, trajectory_id="ep_0000")

    assert examples[0]["messages"][1]["content"].startswith(
        "GOAL: Edit the page by clicking 'Edit page'")


def test_history_carries_outcome_annotation_matching_solver_format():
    ep_dir = tempfile.mkdtemp()
    steps = [
        _step(ep_dir, 0, "http://x/", "[24] link 'Wiki'", "go to wiki", "click('24')"),
        _step(ep_dir, 1, "http://x/wiki", "[7] heading 'Wiki'", "arrived",
             "send_msg_to_user('done')"),
    ]

    examples = episode_to_examples("go to the wiki page", steps, ep_dir,
                                    difficulty=1, trajectory_id="ep_0000")

    assert "- click('24') -> now at http://x/wiki" in examples[1]["messages"][1]["content"]


def test_current_page_prompt_includes_url():
    ep_dir = tempfile.mkdtemp()
    steps = [_step(ep_dir, 0, "http://x/wiki", "[7] heading 'Wiki'",
                   "arrived", "send_msg_to_user('done')")]

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=1, trajectory_id="ep_0000")

    assert "URL: http://x/wiki" in examples[0]["messages"][1]["content"]


def test_trajectory_and_step_metadata_present():
    ep_dir = tempfile.mkdtemp()
    steps = [
        _step(ep_dir, 0, "http://x/", "ax0", "t0", "click('1')"),
        _step(ep_dir, 1, "http://x/2", "ax1", "t1", "send_msg_to_user('done')"),
    ]

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=3,
                                    trajectory_id="ep_0042")

    assert [e["trajectory_id"] for e in examples] == ["ep_0042", "ep_0042"]
    assert [e["step_index"] for e in examples] == [0, 1]
    assert all(e["total_steps"] == 2 for e in examples)
    assert all(e["difficulty"] == 3 for e in examples)


def test_error_step_excluded_from_targets_and_from_later_history():
    ep_dir = tempfile.mkdtemp()
    steps = [
        _step(ep_dir, 0, "http://x/", "ax0",
             "clicking the submit button [action error: element not found]",
             "click('999')"),
        _step(ep_dir, 1, "http://x/", "ax0", "recovered, clicking something else",
             "click('1')"),
    ]

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=1,
                                    trajectory_id="ep_0000")

    targets = [e["step_index"] for e in examples]
    assert 0 not in targets
    assert 1 in targets
    step1_prompt = next(e for e in examples if e["step_index"] == 1)["messages"][1]["content"]
    assert "click('999')" not in step1_prompt


def test_history_window_capped_at_six_matching_solver():
    ep_dir = tempfile.mkdtemp()
    steps = [_step(ep_dir, i, f"http://x/{i}", f"ax{i}", f"t{i}", f"click('{i}')")
            for i in range(8)]
    steps.append(_step(ep_dir, 8, "http://x/8", "ax8", "done", "send_msg_to_user('done')"))

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=1,
                                    trajectory_id="ep_0000")

    last_prompt = examples[-1]["messages"][1]["content"]
    assert "click('0')" not in last_prompt
    assert "click('1')" not in last_prompt
    assert "click('2') ->" in last_prompt
    assert "click('7') ->" in last_prompt


def test_prefers_thought_v2_over_thought_when_present():
    ep_dir = tempfile.mkdtemp()
    rec = _step(ep_dir, 0, "http://x/wiki", "ax", "original thought",
               "send_msg_to_user('done')")
    rec["thought_v2"] = "State: on the wiki page. original thought"

    examples = episode_to_examples("goal", [rec], ep_dir, difficulty=1,
                                    trajectory_id="ep_0000")

    assistant = json.loads(examples[0]["messages"][2]["content"])
    assert assistant["thought"] == "State: on the wiki page. original thought"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_build_sft_dataset.py -q`
Expected: FAIL — `episode_to_examples()` doesn't accept `trajectory_id`, `SYSTEM` is not `SOLVER_SYS`, etc.

- [ ] **Step 3: Extract `step_outcome` in `hsge/webarena/agents.py`**

Add, right after `_cap_axtree` (Task 1's addition):

```python
def step_outcome(pre_url: str, pre_axtree: str, url: str, axtree: str) -> str:
    """Human-readable result of one action: shared by the live Solver prompt
    and the offline SFT dataset builder / thought re-annotator so all three
    describe trajectory history identically."""
    if url != pre_url:
        return f"now at {url}"
    if axtree != pre_axtree:
        return "page changed"
    return "no change"
```

In `Solver.solve`, replace:

```python
            history.append(action)
            if obs["url"] != pre_url:
                outcomes.append(f"now at {obs['url']}")
            elif obs["axtree"] != pre_axtree:
                outcomes.append("page changed")
            else:
                outcomes.append("no change")
            progressed.append(obs["url"] != pre_url or obs["axtree"] != pre_axtree)
```

with:

```python
            history.append(action)
            outcomes.append(step_outcome(pre_url, pre_axtree, obs["url"], obs["axtree"]))
            progressed.append(obs["url"] != pre_url or obs["axtree"] != pre_axtree)
```

Run: `python -m pytest hsge/tests/test_solver.py -q` — Expected: all still pass (pure refactor, no behavior change; `test_history_lines_carry_outcome_annotations` specifically exercises this code path).

- [ ] **Step 4: Rewrite `build_sft_dataset.py`**

Replace the file's imports and `SYSTEM` constant:

```python
from __future__ import annotations

import glob
import json
import os
import sys

from hsge.webarena.agents import PageExplorer, SOLVER_SYS, step_outcome

SYSTEM = SOLVER_SYS

_HISTORY_WINDOW = 6  # matches Solver.solve's history[-6:] window exactly
_TAG_RE = PageExplorer._TAG_RE  # reuse the same "[INFO]/[NAV]/[MOD] " stripper
```

Add the two small helpers right after `_difficulty`:

```python
def _strip_tag(goal: str) -> str:
    """Drop a leading [INFO]/[NAV]/[MOD] classification tag from a goal string.
    Those tags come from PageExplorer's task proposals (see agents.py); a real
    WebArena eval goal never carries one, so leaving it in would teach the
    model to expect a prefix that won't be there at inference time."""
    return _TAG_RE.sub("", goal or "").strip()


def _is_error_step(thought: str) -> bool:
    """A step whose recorded thought carries the '[action error: ...]' suffix
    Solver.solve appends when browser.act() raised (see agents.py::Solver.solve)
    -- the *next* LLM call saw the error and picked a different action, so this
    exact action was never added to Solver.solve's own `history`/`outcomes`
    either. It must not become an imitation target (it's the mistake, not the
    recovery) or appear in a later step's history."""
    return "[action error:" in (thought or "")
```

Replace `episode_to_examples`:

```python
def episode_to_examples(goal: str, steps: list[dict], episode_dir: str,
                        difficulty: int, trajectory_id: str) -> list[dict]:
    goal = _strip_tag(goal)
    axtrees = [_read_axtree(episode_dir, step) for step in steps]
    urls = [step.get("url", "") for step in steps]
    thoughts = [step.get("thought_v2") or step.get("thought", "") for step in steps]
    total_steps = len(steps)

    history: list[str] = []   # outcome-annotated "- action -> outcome" lines
    examples = []
    for k, step in enumerate(steps):
        target_action = step.get("parsed_action") or ""
        if not target_action:
            continue
        thought = thoughts[k]
        if _is_error_step(step.get("thought", "")):
            continue
        assistant = json.dumps({"thought": thought, "action": target_action})
        hist_block = "\n".join(history[-_HISTORY_WINDOW:]) or "(none)"
        obs_block = axtrees[k] if axtrees[k] else "[accessibility tree omitted]"
        user = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n{hist_block}\n\n"
                f"URL: {urls[k]}\n\nPAGE:\n{obs_block}")
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
                {"role": "assistant", "content": assistant},
            ],
            "trajectory_id": trajectory_id,
            "step_index": step.get("index", k),
            "total_steps": total_steps,
            "difficulty": difficulty,
            "axtree_loaded": bool(axtrees[k]),
        })
        is_terminal = (target_action.startswith("send_msg_to_user")
                      or target_action.startswith("report_infeasible"))
        if not is_terminal and k + 1 < len(steps):
            outcome = step_outcome(urls[k], axtrees[k], urls[k + 1], axtrees[k + 1])
            history.append(f"- {target_action} -> {outcome}")
    return examples
```

Replace `load_episodes`:

```python
def load_episodes(path: str):
    """Yield (goal, steps, episode_dir, trajectory_id, difficulty, success) tuples."""
    if os.path.isfile(path) and path.endswith(".json"):
        d = json.load(open(path))
        em = d.get("episode_meta", d)
        ti = d.get("task_info", {})
        steps = d.get("steps") or []
        success = em.get("outcome", {}).get("success", False)
        trajectory_id = os.path.splitext(os.path.basename(path))[0]
        yield (em.get("goal", ""), steps, os.path.dirname(path), trajectory_id,
              _difficulty(ti, em), success)
        return
    for meta_path in glob.glob(os.path.join(path, "**", "episode_meta.json"), recursive=True):
        ep_dir = os.path.dirname(meta_path)
        em = json.load(open(meta_path))
        jl = os.path.join(ep_dir, "episode.jsonl")
        steps = [json.loads(l) for l in open(jl)] if os.path.exists(jl) else []
        ti_path = os.path.join(ep_dir, "..", "..", "task_info.json")
        ti = json.load(open(ti_path)) if os.path.exists(ti_path) else {}
        success = em.get("outcome", {}).get("success", False)
        trajectory_id = os.path.basename(ep_dir)
        yield em.get("goal", ""), steps, ep_dir, trajectory_id, _difficulty(ti, em), success
```

Update `main()`'s loop to unpack the new tuple shape and pass `trajectory_id`:

```python
    all_examples, n_ep, n_kept = [], 0, 0
    for goal, steps, ep_dir, trajectory_id, diff, success in load_episodes(src):
        n_ep += 1
        if not success:                              # only train on successes
            continue
        n_kept += 1
        all_examples += episode_to_examples(goal, steps, ep_dir, diff, trajectory_id)
```

(the rest of `main()` — sorting, writing, the stats print — is unchanged for this task).

- [ ] **Step 5: Run the tests**

Run: `python -m pytest hsge/tests/test_build_sft_dataset.py hsge/tests/test_solver.py -q`
Expected: all pass (8 new + existing Solver tests unaffected).

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest hsge/tests/ -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add hsge/webarena/agents.py build_sft_dataset.py hsge/tests/test_build_sft_dataset.py
git commit -m "SFT dataset: prompt parity via import, URL+outcome history, tag stripping, trajectory metadata

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `build_sft_dataset.py` — include infeasible episodes

**Files:**
- Modify: `build_sft_dataset.py` (`load_episodes`, `main`)
- Test: `hsge/tests/test_build_sft_dataset.py`

**Interfaces:**
- Produces: `load_episodes` now yields a 7-tuple `(goal, steps, episode_dir, trajectory_id, difficulty, success, infeasible)`.
- `main()`'s filter becomes `if not (success or infeasible): continue` — an infeasible episode's final `report_infeasible(...)` step (and every preceding, non-errored navigation step) becomes a valid training target.

- [ ] **Step 1: Write the failing test**

Append to `hsge/tests/test_build_sft_dataset.py`:

```python
from build_sft_dataset import load_episodes


def _write_episode_dir(run_dir, ep_name, goal, success, infeasible, steps):
    ep_dir = os.path.join(run_dir, "episodes", ep_name)
    os.makedirs(ep_dir, exist_ok=True)
    meta = {"kind": "low_level_trajectory", "goal": goal,
            "outcome": {"success": success, "reward": 1.0 if success else 0.0,
                        "response": "", "infeasible": infeasible},
            "metadata": {"difficulty": 1, "tags": ["LOCAL"]}, "step_count": len(steps)}
    json.dump(meta, open(os.path.join(ep_dir, "episode_meta.json"), "w"))
    with open(os.path.join(ep_dir, "episode.jsonl"), "w") as f:
        for st in steps:
            f.write(json.dumps(st) + "\n")
    return ep_dir


def test_load_episodes_yields_infeasible_flag():
    run_dir = tempfile.mkdtemp()
    ep_dir = _write_episode_dir(
        run_dir, "ep_0000", "delete another user's account", False, True,
        [_step(os.path.join(run_dir, "episodes", "ep_0000"), 0, "http://x/",
              "ax", "not possible without admin rights",
              "report_infeasible('requires admin rights')")])

    results = list(load_episodes(run_dir))

    assert len(results) == 1
    goal, steps, yielded_ep_dir, trajectory_id, diff, success, infeasible = results[0]
    assert success is False
    assert infeasible is True


def test_report_infeasible_is_a_valid_training_target():
    ep_dir = tempfile.mkdtemp()
    steps = [
        _step(ep_dir, 0, "http://x/", "ax0", "checking if this is possible",
             "click('1')"),
        _step(ep_dir, 1, "http://x/settings", "ax1", "requires admin rights, "
             "cannot proceed", "report_infeasible('requires admin rights')"),
    ]

    examples = episode_to_examples("delete another user's account", steps, ep_dir,
                                    difficulty=1, trajectory_id="ep_0000")

    assert len(examples) == 2
    last_assistant = json.loads(examples[-1]["messages"][2]["content"])
    assert last_assistant["action"] == "report_infeasible('requires admin rights')"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_build_sft_dataset.py -q`
Expected: FAIL — `load_episodes` yields a 6-tuple, test unpacks 7.

- [ ] **Step 3: Implement**

In `build_sft_dataset.py`'s `load_episodes`, add `infeasible` to both yields:

```python
def load_episodes(path: str):
    """Yield (goal, steps, episode_dir, trajectory_id, difficulty, success,
    infeasible) tuples."""
    if os.path.isfile(path) and path.endswith(".json"):
        d = json.load(open(path))
        em = d.get("episode_meta", d)
        ti = d.get("task_info", {})
        steps = d.get("steps") or []
        outcome = em.get("outcome", {})
        trajectory_id = os.path.splitext(os.path.basename(path))[0]
        yield (em.get("goal", ""), steps, os.path.dirname(path), trajectory_id,
              _difficulty(ti, em), outcome.get("success", False),
              outcome.get("infeasible", False))
        return
    for meta_path in glob.glob(os.path.join(path, "**", "episode_meta.json"), recursive=True):
        ep_dir = os.path.dirname(meta_path)
        em = json.load(open(meta_path))
        jl = os.path.join(ep_dir, "episode.jsonl")
        steps = [json.loads(l) for l in open(jl)] if os.path.exists(jl) else []
        ti_path = os.path.join(ep_dir, "..", "..", "task_info.json")
        ti = json.load(open(ti_path)) if os.path.exists(ti_path) else {}
        outcome = em.get("outcome", {})
        trajectory_id = os.path.basename(ep_dir)
        yield (em.get("goal", ""), steps, ep_dir, trajectory_id, _difficulty(ti, em),
              outcome.get("success", False), outcome.get("infeasible", False))
```

In `main()`:

```python
    all_examples, n_ep, n_kept, n_infeasible_kept = [], 0, 0, 0
    for goal, steps, ep_dir, trajectory_id, diff, success, infeasible in load_episodes(src):
        n_ep += 1
        if not (success or infeasible):
            continue
        n_kept += 1
        n_infeasible_kept += int(infeasible)
        all_examples += episode_to_examples(goal, steps, ep_dir, diff, trajectory_id)
```

and add one line to the stats print block, right after `print(f"successful (kept)    : {n_kept}")`:

```python
    print(f"  of which infeasible : {n_infeasible_kept}  (teaches report_infeasible)")
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest hsge/tests/test_build_sft_dataset.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest hsge/tests/ -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add build_sft_dataset.py hsge/tests/test_build_sft_dataset.py
git commit -m "SFT dataset: include infeasible episodes as report_infeasible training targets

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `judge_episodes.py` — LLM judge pass + `build_sft_dataset.py --require-judge`

**Files:**
- Create: `judge_episodes.py`
- Modify: `build_sft_dataset.py` (migrate `main()` to `argparse`, add `--require-judge`, add `_include_episode`)
- Test: Create `hsge/tests/test_judge_episodes.py`; extend `hsge/tests/test_build_sft_dataset.py`

**Interfaces:**
- Produces: `judge_episodes.judge_episode(llm, ep_dir: str) -> dict` returning `{"judge_verified": bool, "judge_reason": str}`. The script's `main()` writes these into `episode_meta.json`'s `outcome.judge_verified` / `outcome.judge_reason` in place, for every episode with `outcome.success == True`.
- Produces: `build_sft_dataset._include_episode(success: bool, infeasible: bool, judge_verified: bool | None, require_judge: bool) -> bool`.
- `load_episodes` now yields an 8-tuple: `(goal, steps, episode_dir, trajectory_id, difficulty, success, infeasible, judge_verified)`, where `judge_verified` is `None` when the episode was never judged.
- `build_sft_dataset.py` CLI: `python build_sft_dataset.py <src> [out] [--require-judge]`.

- [ ] **Step 1: Write the failing tests**

Create `hsge/tests/test_judge_episodes.py`:

```python
"""judge_episodes.py: catch false-positive declared-success episodes by
asking a judge LLM to re-check the final state against the goal, appending
outcome.judge_verified / outcome.judge_reason to episode_meta.json in place.

Run:  python -m pytest hsge/tests/test_judge_episodes.py -q
 (or) PYTHONPATH=. python hsge/tests/test_judge_episodes.py
"""
import json
import os
import tempfile

from judge_episodes import judge_episode


def _write_episode(success, goal, final_url, final_axtree):
    ep_dir = tempfile.mkdtemp()
    os.makedirs(os.path.join(ep_dir, "page_state"), exist_ok=True)
    meta = {"kind": "low_level_trajectory", "goal": goal,
            "outcome": {"success": success, "reward": 1.0 if success else 0.0,
                        "response": "", "infeasible": False},
            "metadata": {"difficulty": 1, "tags": ["LOCAL"]}, "step_count": 1}
    json.dump(meta, open(os.path.join(ep_dir, "episode_meta.json"), "w"))
    rel = "page_state/step_000_axtree.txt"
    open(os.path.join(ep_dir, rel), "w").write(final_axtree)
    rec = {"record_type": "step", "index": 0, "url": final_url,
           "action": json.dumps({"thought": "done", "action": "send_msg_to_user('done')"}),
           "parsed_action": "send_msg_to_user('done')", "thought": "done",
           "observation": {"axtree_txt": {"path": rel}}}
    with open(os.path.join(ep_dir, "episode.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    return ep_dir


class _StubLLM:
    def __init__(self, verdict, reason):
        self.verdict, self.reason = verdict, reason
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        return {"verdict": self.verdict, "reason": self.reason}


def test_judge_passes_a_genuinely_completed_goal():
    ep_dir = _write_episode(True, "go to the wiki page", "http://x/wiki",
                            "[7] heading 'Wiki'")
    llm = _StubLLM("PASS", "the URL and page both confirm the wiki page")

    result = judge_episode(llm, ep_dir)

    assert result["judge_verified"] is True
    assert "wiki" in result["judge_reason"]


def test_judge_catches_a_false_positive():
    ep_dir = _write_episode(True, "find the number of notifications",
                            "http://x/", "[1] link 'Notifications'")
    llm = _StubLLM("FAIL", "the notification count is not shown anywhere on this page")

    result = judge_episode(llm, ep_dir)

    assert result["judge_verified"] is False


def test_judge_prompt_includes_goal_and_final_url():
    ep_dir = _write_episode(True, "go to the wiki page", "http://x/wiki", "ax")
    llm = _StubLLM("PASS", "ok")

    judge_episode(llm, ep_dir)

    assert "go to the wiki page" in llm.prompts[0]
    assert "http://x/wiki" in llm.prompts[0]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
```

Append to `hsge/tests/test_build_sft_dataset.py`:

```python
from build_sft_dataset import _include_episode


def test_include_episode_success_without_require_judge():
    assert _include_episode(success=True, infeasible=False, judge_verified=None,
                            require_judge=False) is True


def test_include_episode_infeasible_always_included_regardless_of_judge():
    assert _include_episode(success=False, infeasible=True, judge_verified=None,
                            require_judge=True) is True


def test_include_episode_require_judge_drops_unjudged_success():
    assert _include_episode(success=True, infeasible=False, judge_verified=None,
                            require_judge=True) is False


def test_include_episode_require_judge_drops_failed_judgment():
    assert _include_episode(success=True, infeasible=False, judge_verified=False,
                            require_judge=True) is False


def test_include_episode_require_judge_keeps_verified_success():
    assert _include_episode(success=True, infeasible=False, judge_verified=True,
                            require_judge=True) is True


def test_include_episode_plain_failure_excluded():
    assert _include_episode(success=False, infeasible=False, judge_verified=None,
                            require_judge=False) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_judge_episodes.py hsge/tests/test_build_sft_dataset.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'judge_episodes'`, `ImportError: cannot import name '_include_episode'`.

- [ ] **Step 3: Create `judge_episodes.py`**

```python
"""Judge pass: catch false-positive `success` episodes before they enter SFT
training data.

For a non-predicate task (LOCAL, and most GOAL tasks without a terminal
predicate), "success" in episode_meta.json only means the Solver itself
called send_msg_to_user without an error (see hsge/webarena/agents.py::
Solver.solve) -- the agent is grading its own homework. A strong judge model
re-checks each declared-success episode against its own final state and
appends outcome.judge_verified / outcome.judge_reason to episode_meta.json
IN PLACE (additive, never destructive -- outcome.success is left untouched
so the raw collection record stays intact). build_sft_dataset.py's
--require-judge flag then requires judge_verified in addition to success.

Usage:
    python judge_episodes.py outputs/wa_run_09
    python judge_episodes.py outputs/wa_run_09 --config config.yaml --limit 50
"""
from __future__ import annotations

import argparse
import glob
import json
import os

from build_sft_dataset import _read_axtree
from run_webarena import _effective_llm_config, _load_config, _load_dotenv

_SYS = (
    "You are a strict grader of a web agent's completed task. You are given "
    "the GOAL the agent was told to accomplish, the actions it took before "
    "declaring the task done, and the FINAL page (URL + accessibility tree) "
    "where it declared done. Decide whether the goal was genuinely achieved "
    "by the final state -- not whether the agent SAID it was done. Common "
    "false positives: the agent gave up and declared done anyway; it "
    "answered an INFO question with a guess not actually shown on the final "
    "page; it navigated to the wrong page. "
    'Return JSON {"verdict": "PASS"|"FAIL", "reason": "<one sentence>"}.'
)

_AXTREE_CAP = 4000


def _judge_prompt(goal: str, history: list[str], final_url: str, final_axtree: str) -> str:
    payload = {
        "goal": goal,
        "actions_taken": history,
        "final_url": final_url,
        "final_page": (final_axtree or "")[:_AXTREE_CAP],
    }
    return f"<payload>{json.dumps(payload)}</payload>"


def judge_episode(llm, ep_dir: str) -> dict:
    """Return {"judge_verified": bool, "judge_reason": str} for one episode."""
    steps = []
    for line in open(os.path.join(ep_dir, "episode.jsonl")):
        rec = json.loads(line)
        if rec.get("record_type") == "step":
            steps.append(rec)
    if not steps:
        return {"judge_verified": False, "judge_reason": "no steps recorded"}
    meta = json.load(open(os.path.join(ep_dir, "episode_meta.json")))
    goal = meta.get("goal", "")
    history = [rec.get("parsed_action", "") for rec in steps[:-1]]
    final = steps[-1]
    final_axtree = _read_axtree(ep_dir, final)
    out = llm.complete_json(_SYS, _judge_prompt(goal, history, final.get("url", ""), final_axtree))
    verdict = str(out.get("verdict", "")).strip().upper()
    return {"judge_verified": verdict == "PASS",
            "judge_reason": str(out.get("reason", ""))[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--limit", type=int, default=10**9)
    args = ap.parse_args()

    _load_dotenv()
    ns = argparse.Namespace(provider=None, model=None, base_url=None)
    cfg = _effective_llm_config(ns, _load_config(args.config)["llm"], "episode_judge")
    from hsge.backends import OpenAILLM
    print(f"[llm:episode_judge] provider={cfg['provider']} model={cfg['model']}")
    llm = OpenAILLM(model=cfg["model"], base_url=cfg["base_url"],
                    api_key=cfg["api_key"], temperature=cfg["temperature"])

    episodes_dir = os.path.join(args.run_dir, "episodes")
    checked, verified = 0, 0
    for ep_dir in sorted(glob.glob(os.path.join(episodes_dir, "ep_*")))[: args.limit]:
        meta_path = os.path.join(ep_dir, "episode_meta.json")
        meta = json.load(open(meta_path))
        if not meta.get("outcome", {}).get("success"):
            continue
        checked += 1
        result = judge_episode(llm, ep_dir)
        meta["outcome"]["judge_verified"] = result["judge_verified"]
        meta["outcome"]["judge_reason"] = result["judge_reason"]
        json.dump(meta, open(meta_path, "w"), indent=2)
        verified += int(result["judge_verified"])
        print(f"  {os.path.basename(ep_dir)}: "
              f"{'PASS' if result['judge_verified'] else 'FAIL'} -- {result['judge_reason']}")
    print(f"\njudged {checked} declared-success episodes, {verified} verified "
          f"({checked - verified} false positives caught)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Wire `--require-judge` into `build_sft_dataset.py`**

Add `_include_episode` right after `_is_error_step`:

```python
def _include_episode(success: bool, infeasible: bool, judge_verified: bool | None,
                     require_judge: bool) -> bool:
    """Whether one episode's steps should be turned into SFT examples.
    Infeasible episodes are always eligible (report_infeasible is a real
    target regardless of judging). A plain success is eligible unless
    --require-judge is set, in which case it needs judge_verified is True --
    an episode never judged (judge_verified is None) is dropped, not
    silently trusted, so --require-judge fails safe."""
    if infeasible:
        return True
    if not success:
        return False
    if require_judge:
        return judge_verified is True
    return True
```

Update `load_episodes` to also yield `judge_verified` (both branches):

```python
def load_episodes(path: str):
    """Yield (goal, steps, episode_dir, trajectory_id, difficulty, success,
    infeasible, judge_verified) tuples. judge_verified is None if the
    episode has never been through judge_episodes.py."""
    if os.path.isfile(path) and path.endswith(".json"):
        d = json.load(open(path))
        em = d.get("episode_meta", d)
        ti = d.get("task_info", {})
        steps = d.get("steps") or []
        outcome = em.get("outcome", {})
        trajectory_id = os.path.splitext(os.path.basename(path))[0]
        yield (em.get("goal", ""), steps, os.path.dirname(path), trajectory_id,
              _difficulty(ti, em), outcome.get("success", False),
              outcome.get("infeasible", False), outcome.get("judge_verified"))
        return
    for meta_path in glob.glob(os.path.join(path, "**", "episode_meta.json"), recursive=True):
        ep_dir = os.path.dirname(meta_path)
        em = json.load(open(meta_path))
        jl = os.path.join(ep_dir, "episode.jsonl")
        steps = [json.loads(l) for l in open(jl)] if os.path.exists(jl) else []
        ti_path = os.path.join(ep_dir, "..", "..", "task_info.json")
        ti = json.load(open(ti_path)) if os.path.exists(ti_path) else {}
        outcome = em.get("outcome", {})
        trajectory_id = os.path.basename(ep_dir)
        yield (em.get("goal", ""), steps, ep_dir, trajectory_id, _difficulty(ti, em),
              outcome.get("success", False), outcome.get("infeasible", False),
              outcome.get("judge_verified"))
```

Replace `main()` in full (migrates from raw `sys.argv` to `argparse`):

```python
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="run directory or single episode json")
    ap.add_argument("out", nargs="?", default="train.jsonl")
    ap.add_argument("--require-judge", action="store_true",
                    help="only keep declared-success episodes whose "
                         "outcome.judge_verified is true (run judge_episodes.py "
                         "first); never-judged success episodes are dropped, "
                         "not silently trusted")
    args = ap.parse_args()

    all_examples, n_ep, n_kept, n_infeasible_kept, n_unjudged_dropped = [], 0, 0, 0, 0
    for (goal, steps, ep_dir, trajectory_id, diff, success, infeasible,
        judge_verified) in load_episodes(args.src):
        n_ep += 1
        if args.require_judge and success and not infeasible and judge_verified is None:
            n_unjudged_dropped += 1
        if not _include_episode(success, infeasible, judge_verified, args.require_judge):
            continue
        n_kept += 1
        n_infeasible_kept += int(infeasible)
        all_examples += episode_to_examples(goal, steps, ep_dir, diff, trajectory_id)

    all_examples.sort(key=lambda e: e["difficulty"])   # curriculum: easy -> hard
    with open(args.out, "w") as f:
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n")

    by_diff = {}
    for e in all_examples:
        by_diff[e["difficulty"]] = by_diff.get(e["difficulty"], 0) + 1
    loaded = sum(e["axtree_loaded"] for e in all_examples)
    print(f"episodes seen        : {n_ep}")
    print(f"successful (kept)    : {n_kept}")
    print(f"  of which infeasible : {n_infeasible_kept}  (teaches report_infeasible)")
    if args.require_judge:
        print(f"unjudged success episodes dropped: {n_unjudged_dropped} "
              f"(run judge_episodes.py first to include them)")
    print(f"SFT examples written : {len(all_examples)} -> {args.out}")
    print(f"examples by difficulty: {dict(sorted(by_diff.items()))}")
    print(f"with real AXTree text : {loaded}/{len(all_examples)} "
          f"(rest need the run dir's page_state/*.txt files)")
    if all_examples:
        print("\n--- example[0] (truncated) ---")
        ex = all_examples[0]
        print("system   :", ex["messages"][0]["content"][:90], "...")
        print("user     :", ex["messages"][1]["content"][:120].replace("\n", " "), "...")
        print("assistant:", ex["messages"][2]["content"][:120], "...")


if __name__ == "__main__":
    main()
```

(the top-of-file `import argparse` must be added to `build_sft_dataset.py`'s import block; `sys` is no longer used and can be dropped if nothing else references it — check with `grep -n "sys\." build_sft_dataset.py` before removing).

- [ ] **Step 5: Run the tests**

Run: `python -m pytest hsge/tests/test_judge_episodes.py hsge/tests/test_build_sft_dataset.py -q`
Expected: all pass.
Run: `python build_sft_dataset.py --help` — Expected: shows `--require-judge` in the help text (confirms the CLI migration didn't break invocation).

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest hsge/tests/ -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add judge_episodes.py build_sft_dataset.py \
        hsge/tests/test_judge_episodes.py hsge/tests/test_build_sft_dataset.py
git commit -m "Add judge_episodes.py: LLM judge pass for false-positive success filtering

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `reannotate_thoughts.py` — state/subgoal/reflection/completion-check thought template

**Files:**
- Create: `reannotate_thoughts.py`
- Test: Create `hsge/tests/test_reannotate_thoughts.py`

**Interfaces:**
- Produces: `reannotate_thoughts._compose_thought(original, state, reflection, subgoal, is_segment_final, completion_check) -> str` (pure, unit-testable).
- Produces: `reannotate_thoughts.reannotate_episode(reannotate_llm, segment_llm, ep_dir: str, goal: str, axtree_sim: float = 0.6) -> int` — rewrites `episode.jsonl` in place, adding `thought_v2` per step record; returns the count of steps rewritten. Never touches the original `thought` field.
- Consumes: `replay_segmentation.load_steps(ep_dir) -> list[Step]`, `hsge.segmentation.segment_trajectory`, `hsge.webarena.agents.step_outcome`, `build_sft_dataset._read_axtree` (all from prior tasks / existing code — no new shared interfaces beyond what Task 2 already produced).

- [ ] **Step 1: Write the failing tests**

Create `hsge/tests/test_reannotate_thoughts.py`:

```python
"""reannotate_thoughts.py: state/subgoal/reflection/completion-check thought
re-annotation, written in place as `thought_v2` without touching `thought`.

Run:  python -m pytest hsge/tests/test_reannotate_thoughts.py -q
 (or) PYTHONPATH=. python hsge/tests/test_reannotate_thoughts.py
"""
import json
import os
import tempfile

from reannotate_thoughts import _compose_thought, reannotate_episode


def _write_episode(ep_dir, steps):
    os.makedirs(os.path.join(ep_dir, "page_state"), exist_ok=True)
    with open(os.path.join(ep_dir, "episode.jsonl"), "w") as f:
        for i, (url, axtree, thought, action) in enumerate(steps):
            rel = f"page_state/step_{i:03d}_axtree.txt"
            open(os.path.join(ep_dir, rel), "w").write(axtree)
            rec = {"record_type": "step", "index": i, "url": url,
                   "action": json.dumps({"thought": thought, "action": action}),
                   "parsed_action": action, "thought": thought,
                   "observation": {"axtree_txt": {"path": rel}}}
            f.write(json.dumps(rec) + "\n")


class _StubLLM:
    """Branches like the real backends: segment_trajectory's system prompt
    contains 'SEGMENT' (see hsge/segmentation.py's _SYS); everything else is
    treated as a reannotation call."""

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        if "SEGMENT" in system:
            payload = json.loads(prompt.split("<payload>", 1)[1].rsplit("</payload>", 1)[0])
            return {"segments": [{"span": s["span"], "subgoal": "search for an item"}
                                 for s in payload["segments"]]}
        return {"state": "on the search results page", "reflection": "",
                "completion_check": "the confirmation text is visible"}


def test_compose_thought_intermediate_step_includes_subgoal():
    text = _compose_thought(original="click search", state="on the home page",
                            reflection="", subgoal="log in", is_segment_final=False,
                            completion_check="")
    assert text == "State: on the home page. Subgoal: log in. click search"


def test_compose_thought_marks_segment_final():
    text = _compose_thought(original="submitted", state="form filled",
                            reflection="", subgoal="log in", is_segment_final=True,
                            completion_check="")
    assert "Subgoal complete." in text


def test_compose_thought_reflection_only_when_present():
    text = _compose_thought(original="retry", state="still on the form",
                            reflection="the previous click did not register",
                            subgoal="log in", is_segment_final=False, completion_check="")
    assert "Reflection: the previous click did not register." in text


def test_compose_thought_omits_reflection_when_empty():
    text = _compose_thought(original="click", state="on the home page", reflection="",
                            subgoal="log in", is_segment_final=False, completion_check="")
    assert "Reflection:" not in text


def test_compose_thought_terminal_step_uses_completion_check_not_subgoal():
    text = _compose_thought(original="done", state="on the confirmation page",
                            reflection="", subgoal=None, is_segment_final=False,
                            completion_check="the confirmation text is visible")
    assert "Completion check: the confirmation text is visible." in text
    assert "Subgoal:" not in text


def test_reannotate_episode_writes_thought_v2_without_touching_thought():
    ep_dir = tempfile.mkdtemp()
    _write_episode(ep_dir, [
        ("http://x/", "[1] link 'search'", "click search", "click('1')"),
        ("http://x/results", "[2] heading 'Results'", "done",
         "send_msg_to_user('done: found it')"),
    ])
    llm = _StubLLM()

    n = reannotate_episode(llm, llm, ep_dir, goal="search for an item")

    assert n == 2
    lines = [json.loads(l) for l in open(os.path.join(ep_dir, "episode.jsonl"))]
    assert lines[0]["thought"] == "click search"          # untouched
    assert "thought_v2" in lines[0]
    assert "Completion check:" in lines[1]["thought_v2"]   # terminal step


def test_reannotate_episode_empty_run_returns_zero():
    ep_dir = tempfile.mkdtemp()
    open(os.path.join(ep_dir, "episode.jsonl"), "w").close()

    n = reannotate_episode(_StubLLM(), _StubLLM(), ep_dir, goal="goal")

    assert n == 0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_reannotate_thoughts.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'reannotate_thoughts'`.

- [ ] **Step 3: Create `reannotate_thoughts.py`**

```python
"""Re-annotate collected trajectories' per-step `thought` into a richer
`thought_v2`: a terse state assessment, the step's subgoal (from an offline
replay of hsge.segmentation.segment_trajectory -- the same segmentation
Discovery uses live, just run after the fact over persisted steps), a
reflection on the prior action when it made no progress, and -- only on a
task's final step (send_msg_to_user / report_infeasible) -- a completion
check of whether the goal is genuinely satisfied by the final page.

The subgoal/completion-check text is written ONLY into the assistant target
(thought_v2), never into build_sft_dataset.py's user prompt: there is no
retrieval/grounding pipeline at inference time to supply "the current
subgoal" as an input, so putting it there would be a training/serving
mismatch. Here it teaches the model to *produce* subgoal-aware reasoning
instead.

thought_v2 is added next to (never replacing) the original `thought` in
episode.jsonl, so partially-annotated runs stay usable and re-running is
idempotent.

Usage:
    python reannotate_thoughts.py outputs/wa_run_09
    python reannotate_thoughts.py outputs/wa_run_09 --config config.yaml --limit 20
"""
from __future__ import annotations

import argparse
import glob
import json
import os

from build_sft_dataset import _read_axtree
from hsge.segmentation import segment_trajectory
from hsge.webarena.agents import step_outcome
from replay_segmentation import load_steps
from run_webarena import _effective_llm_config, _load_config, _load_dotenv

_SYS = (
    "You REWRITE one step's internal reasoning for a web agent's training "
    "data. You are given the step's GOAL, its SUBGOAL (or, for the final "
    "step of a task, a note that a final decision is being made), the "
    "action PRIOR to this one and its outcome (if any), the current page, "
    "and the action this step took. Produce a terse one-sentence STATE "
    "assessment of what the page currently shows. If the PRIOR action's "
    "outcome shows no progress or an error, write a one-sentence REFLECTION "
    "on why (empty string if the prior action clearly succeeded, or this is "
    "the first step). If this step is the FINAL step of the task (marked "
    "below), also judge in COMPLETION_CHECK whether the goal is actually "
    "satisfied by the current page -- not just whether the agent believes "
    "so (empty string otherwise). "
    'Return JSON {"state": "<one short sentence>", "reflection": "<sentence '
    'or empty string>", "completion_check": "<sentence or empty string>"}.'
)

_AXTREE_CAP = 4000


def _reannotate_prompt(goal: str, subgoal: str, is_final: bool,
                       prior_action: str | None, prior_outcome: str | None,
                       url: str, axtree: str, action: str) -> str:
    payload = {
        "goal": goal,
        "subgoal": subgoal if not is_final else "(final step -- deciding whether to finish)",
        "is_final_step": is_final,
        "prior_action": prior_action,
        "prior_outcome": prior_outcome,
        "url": url,
        "page": (axtree or "")[:_AXTREE_CAP],
        "action_taken": action,
    }
    return f"<payload>{json.dumps(payload)}</payload>"


def _compose_thought(original: str, state: str, reflection: str,
                     subgoal: str | None, is_segment_final: bool,
                     completion_check: str) -> str:
    """Join the re-annotated pieces into one compact string -- SOLVER_SYS's
    output format is {"thought": "<string>", ...}, so this stays a single
    field, not a nested structure. completion_check takes priority over
    subgoal (a step is either mid-subgoal or making the final call, never
    both)."""
    parts = [f"State: {state}."]
    if reflection:
        parts.append(f"Reflection: {reflection}.")
    if completion_check:
        parts.append(f"Completion check: {completion_check}.")
    elif subgoal:
        parts.append(f"Subgoal: {subgoal}.")
        if is_segment_final:
            parts.append("Subgoal complete.")
    parts.append(original.strip())
    return " ".join(p for p in parts if p)


def _segment_labels(llm, steps, site: str, task: str, axtree_sim: float) -> dict:
    """step index -> (subgoal, is_segment_final), from an offline
    segment_trajectory() replay over already-persisted steps."""
    subs = segment_trajectory(llm, steps, site=site, task=task, axtree_sim=axtree_sim)
    labels, idx = {}, 0
    for sub in subs:
        for j in range(len(sub.steps)):
            labels[idx] = (sub.subgoal, j == len(sub.steps) - 1)
            idx += 1
    return labels


def reannotate_episode(reannotate_llm, segment_llm, ep_dir: str, goal: str,
                       axtree_sim: float = 0.6) -> int:
    """Rewrite thought -> thought_v2 for every step in one episode's
    episode.jsonl, in place. Returns the number of steps rewritten."""
    steps = load_steps(ep_dir)
    if not steps:
        return 0
    seg_labels = _segment_labels(segment_llm, steps, site=ep_dir, task=goal,
                                 axtree_sim=axtree_sim)

    lines = [json.loads(l) for l in open(os.path.join(ep_dir, "episode.jsonl"))]
    n = 0
    for k, rec in enumerate(lines):
        if rec.get("record_type") != "step":
            continue
        action = rec.get("parsed_action", "")
        is_terminal = (action.startswith("send_msg_to_user")
                      or action.startswith("report_infeasible"))
        prior_action, prior_outcome = None, None
        if k > 0:
            prior_action = lines[k - 1].get("parsed_action", "")
            prior_outcome = step_outcome(
                lines[k - 1].get("url", ""), _read_axtree(ep_dir, lines[k - 1]),
                rec.get("url", ""), _read_axtree(ep_dir, rec))
        subgoal, is_seg_final = seg_labels.get(k, ("", False))
        prompt = _reannotate_prompt(
            goal, subgoal, is_terminal, prior_action, prior_outcome,
            rec.get("url", ""), _read_axtree(ep_dir, rec), action)
        out = reannotate_llm.complete_json(_SYS, prompt)
        rec["thought_v2"] = _compose_thought(
            original=rec.get("thought", ""),
            state=str(out.get("state", "")).strip(),
            reflection=str(out.get("reflection", "")).strip(),
            subgoal=subgoal if not is_terminal else None,
            is_segment_final=is_seg_final,
            completion_check=str(out.get("completion_check", "")).strip() if is_terminal else "")
        n += 1

    with open(os.path.join(ep_dir, "episode.jsonl"), "w") as f:
        for rec in lines:
            f.write(json.dumps(rec) + "\n")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--limit", type=int, default=10**9)
    ap.add_argument("--axtree-sim", type=float, default=0.6)
    args = ap.parse_args()

    _load_dotenv()
    llm_cfg = _load_config(args.config)["llm"]
    ns = argparse.Namespace(provider=None, model=None, base_url=None)
    from hsge.backends import OpenAILLM

    r_cfg = _effective_llm_config(ns, llm_cfg, "thought_reannotator")
    reannotate_llm = OpenAILLM(model=r_cfg["model"], base_url=r_cfg["base_url"],
                               api_key=r_cfg["api_key"], temperature=r_cfg["temperature"])
    s_cfg = _effective_llm_config(ns, llm_cfg, "trajectory_segmenter")
    segment_llm = OpenAILLM(model=s_cfg["model"], base_url=s_cfg["base_url"],
                            api_key=s_cfg["api_key"], temperature=s_cfg["temperature"])
    print(f"[llm:thought_reannotator] model={r_cfg['model']}  "
          f"[llm:trajectory_segmenter] model={s_cfg['model']}")

    episodes_dir = os.path.join(args.run_dir, "episodes")
    total = 0
    for meta_path in sorted(
            glob.glob(os.path.join(episodes_dir, "ep_*", "episode_meta.json")))[: args.limit]:
        ep_dir = os.path.dirname(meta_path)
        meta = json.load(open(meta_path))
        n = reannotate_episode(reannotate_llm, segment_llm, ep_dir, meta.get("goal", ""),
                               axtree_sim=args.axtree_sim)
        total += n
        print(f"  {os.path.basename(ep_dir)}: {n} steps re-annotated")
    print(f"\nre-annotated {total} steps total")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest hsge/tests/test_reannotate_thoughts.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest hsge/tests/ -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add reannotate_thoughts.py hsge/tests/test_reannotate_thoughts.py
git commit -m "Add reannotate_thoughts.py: state/subgoal/reflection/completion-check thought template

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Integration — stats reporting, docs, real-data smoke test

**Files:**
- Modify: `build_sft_dataset.py` (stats print: judge/thought_v2/subgoal coverage)
- Modify: `.claude/rules/architecture.md` (new subsection), `.claude/memory/changelog.md`
- Modify: `config.yaml` (optional `episode_judge` / `thought_reannotator` role stanzas — additive only, do not touch existing entries)
- Verification: real-data smoke test against a copy of `outputs/wa_run_09`

**Interfaces:**
- Consumes: everything from Tasks 1–5. No new function interfaces — this task is reporting, documentation, and end-to-end verification only.

- [ ] **Step 1: Add coverage stats to `build_sft_dataset.py`'s output**

In `main()`, after the existing `loaded = sum(...)` line, add:

```python
    thought_v2_count = sum(1 for e in all_examples
                           if "State:" in json.loads(e["messages"][2]["content"])["thought"])
    subgoal_count = sum(1 for e in all_examples
                        if "Subgoal:" in json.loads(e["messages"][2]["content"])["thought"])
```

and add two print lines right after the existing `print(f"with real AXTree text ...")` line:

```python
    print(f"re-annotated thoughts : {thought_v2_count}/{len(all_examples)} "
          f"(run reannotate_thoughts.py first to raise this)")
    print(f"with subgoal in target: {subgoal_count}/{len(all_examples)}")
```

Run: `python -m pytest hsge/tests/test_build_sft_dataset.py -q` — Expected: still passes (additive stats only, no interface change).

- [ ] **Step 2: Document the new pipeline stage in `.claude/rules/architecture.md`**

Add a new subsection right after the existing `**Vision**` bullet and before `**Each LLM-backed helper can use a different model**` (or at the end of the WebArena runtime section — find the natural break after the `runtime.py` bullet block):

```markdown
**SFT dataset assembly is a three-stage offline pipeline**, run after
`run_webarena.py` finishes collecting `episodes/`:
`judge_episodes.py` (optional) re-checks every declared-success episode
against its own final state with a strong LLM and appends
`outcome.judge_verified`/`outcome.judge_reason` to `episode_meta.json` in
place (additive; `outcome.success` is left untouched) — catches the agent
grading its own homework (declaring done without actually satisfying the
goal). `reannotate_thoughts.py` (optional) rewrites each step's `thought`
into a `thought_v2` field: a terse state assessment, a reflection when the
prior action made no progress, and — only on a task's terminal step — a
completion check, composed with the step's subgoal from an offline replay
of `segment_trajectory()` (the same segmentation `Discovery` uses live).
The subgoal only ever appears in the assistant *target*, never in
`build_sft_dataset.py`'s user prompt, since there is no retrieval/grounding
pipeline at inference time to supply "the current subgoal" as an input.
`build_sft_dataset.py` then turns `episodes/` into `train.jsonl`: its
system/user prompt is byte-for-byte the live Solver's (`SYSTEM =
SOLVER_SYS`, imported not duplicated), history lines are outcome-annotated
via the same `step_outcome()` helper `Solver.solve` uses, a leading
`[INFO]/[NAV]/[MOD]` goal tag is stripped (a real WebArena eval goal never
carries one), each example carries `trajectory_id`/`step_index`/
`total_steps` for downstream trajectory-aware batching, a step whose
recorded thought carries `"[action error:"` is excluded from both training
targets and later steps' history (it was the mistake, not the recovery, and
was never in the live Solver's own history either), `report_infeasible`
episodes are kept as valid targets, and `--require-judge` restricts
declared-success episodes to `judge_verified is True` (never-judged
episodes are dropped, not silently trusted).
```

- [ ] **Step 3: Add optional role config to `config.yaml`**

Append two entries under the existing `agents:` block, after `operator_inducer:` (do not modify any existing lines):

```yaml
    episode_judge:            # judge_episodes.py: re-checks declared-success
      model: deepseek-v4-pro  # episodes against their final state
    thought_reannotator:      # reannotate_thoughts.py: rewrites step thoughts
      model: deepseek-v4-pro
```

(both fall back to the shared `llm.*` block if omitted entirely — this addition is optional documentation of a sensible default, not a functional requirement).

- [ ] **Step 4: Update the memory changelog**

Get the real timestamp: `date "+%Y-%m-%d %H:%M"`. Add one entry under today's `## <date>` heading in `.claude/memory/changelog.md` (create the heading if the date has changed since the last entry), summarizing: SFT dataset v2 — runtime action-space additions (press/tab ops/axtree truncation marker/visible-only observation), `build_sft_dataset.py` rewrite (prompt parity by import, URL, outcome+thought history, tag stripping, trajectory/step metadata, error-step exclusion, infeasible-episode inclusion), `judge_episodes.py` (LLM judge pass + `--require-judge`), `reannotate_thoughts.py` (state/subgoal/reflection/completion-check thought template via offline segmentation replay). Name all files touched across Tasks 1–6.

- [ ] **Step 5: Real-data smoke test (manual — not committed)**

Never mutate `outputs/wa_run_09` in place (`judge_episodes.py`/`reannotate_thoughts.py` write in place, and this is real experiment history). Work on a scratch copy:

```bash
mkdir -p /tmp/sft_v2_smoke/episodes
cp -r outputs/wa_run_09/episodes/ep_0000 outputs/wa_run_09/episodes/ep_0001 \
      outputs/wa_run_09/episodes/ep_0002 outputs/wa_run_09/episodes/ep_0003 \
      outputs/wa_run_09/episodes/ep_0004 /tmp/sft_v2_smoke/episodes/
```

Then, with real API credentials available (`.env` at repo root):

```bash
python judge_episodes.py /tmp/sft_v2_smoke --limit 5
python reannotate_thoughts.py /tmp/sft_v2_smoke --limit 5
python build_sft_dataset.py /tmp/sft_v2_smoke/episodes /tmp/sft_v2_smoke/train.jsonl --require-judge
```

Expected: `judge_episodes.py` prints a PASS/FAIL line per declared-success episode among the 5 copied; `reannotate_thoughts.py` prints a re-annotated step count per episode; `build_sft_dataset.py`'s final stats block shows non-zero `re-annotated thoughts` and `with subgoal in target` counts, and the `--require-judge` run's `unjudged success episodes dropped` count is `0` for episodes that were judged in the first step (since all 5 were judged). Inspect `/tmp/sft_v2_smoke/train.jsonl`'s first line and confirm the assistant `thought` field contains `"State:"` and (for a multi-step example) `"Subgoal:"`.

If no `.env`/API key is available in this environment, skip this step and note in the changelog entry that the real-data smoke test is pending a run with credentials — do not claim it passed without having actually run it (per repo verification norms).

- [ ] **Step 6: Run the full suite one final time**

Run: `python -m pytest hsge/tests/ -q`
Expected: all pass (this is the true gate for this task, independent of whether Step 5's live-LLM smoke test could run).

- [ ] **Step 7: Commit**

```bash
git add build_sft_dataset.py .claude/rules/architecture.md .claude/memory/changelog.md config.yaml
git commit -m "SFT dataset v2: coverage stats, architecture docs, config roles for judge/reannotate

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
