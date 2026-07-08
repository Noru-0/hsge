# SFT prompt fidelity + Solver action-space expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `build_sft_dataset.py` emit the exact prompt `Solver.solve()` sent to the LLM at inference time (via one shared `build_solver_prompt()` function), and teach the Solver 3 actions (`report_infeasible`, `press`, `hover`) the underlying BrowserGym executor already supports but the prompt never documents.

**Architecture:** Extract the Solver's inline prompt-assembly f-string into a pure module-level function `build_solver_prompt()` in `hsge/webarena/agents.py`, called live by `Solver.solve()` and offline by `build_sft_dataset.py`. Persist two small new `Step` fields (`hints`, `last_error`) plus the already-existing-but-dropped `url` field into `episode.jsonl`, so `build_sft_dataset.py` can replay an episode's steps and reconstruct the exact `history`/`progressed` inputs `build_solver_prompt()` needs — without ever storing the assembled prompt itself during exploration.

**Tech Stack:** Python 3, stdlib only (`dataclasses`, `json`), pytest for tests.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-08-sft-prompt-fidelity-action-space-design.md`.
- Do not add `noop`, `scroll`, `dblclick`, `focus`, `clear`, `drag_and_drop`, `upload_file`, `go_forward` to `ACTIONS_DOC` — out of scope this round.
- Do not add `verified`/reward as a per-example column or `episode_id`/`step_idx`/`traj_length` — out of scope this round.
- A step from an episode recorded before this change (missing `hints`/`last_error`/`url` in its `episode.jsonl` record) must be **skipped** by `build_sft_dataset.py`, never approximated with a fallback template.
- `report_infeasible` ends `Solver.solve()`'s loop like `send_msg_to_user` does, but must **not** set `success = True`.
- All new/changed code in English; run `python -m pytest hsge/tests/ -q` after each task.

---

### Task 1: `Step` gains `hints`/`last_error` fields

**Files:**
- Modify: `hsge/schema.py` (the `Step` dataclass, currently ending at line 26 with `axtree: str = ""`)
- Test: `hsge/tests/test_recording.py`

**Interfaces:**
- Produces: `Step.hints: str = ""`, `Step.last_error: str = ""` — two new dataclass fields, appended after `axtree` so all existing positional `Step(...)` call sites (e.g. `hsge/tests/test_clustering.py`) stay valid.

- [ ] **Step 1: Write the failing test**

Add to `hsge/tests/test_recording.py` (new test, keep existing two tests untouched):

```python
def test_step_carries_hints_and_last_error_defaults():
    from hsge.schema import Step
    s = Step(action="click('1')", url="u", axtree="ax")
    assert s.hints == ""
    assert s.last_error == ""


def test_step_accepts_hints_and_last_error_explicitly():
    from hsge.schema import Step
    s = Step(action="click('1')", url="u", axtree="ax",
              hints="KNOWN PROCEDURES: ...", last_error="TimeoutError: click failed")
    assert s.hints == "KNOWN PROCEDURES: ..."
    assert s.last_error == "TimeoutError: click failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest hsge/tests/test_recording.py -k "hints_and_last_error" -v`
Expected: FAIL with `TypeError: Step.__init__() got an unexpected keyword argument 'hints'`

- [ ] **Step 3: Add the fields**

In `hsge/schema.py`, the `Step` dataclass currently reads:

```python
@dataclass
class Step:
    """One primitive (action, observation) pair in a trajectory."""
    action: str                 # e.g. "click [submit]", "type [username] 'alice'"
    url: str                    # URL after the action
    obs_summary: str = ""       # short NL summary of the resulting observation
    dom_signature: str = ""     # cheap structural fingerprint of the page
    axtree: str = ""            # full accessibility tree at this step (real backends only)
```

Change it to:

```python
@dataclass
class Step:
    """One primitive (action, observation) pair in a trajectory."""
    action: str                 # e.g. "click [submit]", "type [username] 'alice'"
    url: str                    # URL after the action
    obs_summary: str = ""       # short NL summary of the resulting observation
    dom_signature: str = ""     # cheap structural fingerprint of the page
    axtree: str = ""            # full accessibility tree at this step (real backends only)
    hints: str = ""             # KNOWN PROCEDURES block shown to the Solver for this step, if any
    last_error: str = ""        # LAST ACTION ERROR text shown to the Solver for this step, if any
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest hsge/tests/test_recording.py -k "hints_and_last_error" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add hsge/schema.py hsge/tests/test_recording.py
git commit -m "Add hints/last_error fields to Step"
```

---

### Task 2: `record_episode` persists `hints`/`last_error`/`url`

**Files:**
- Modify: `hsge/webarena/recording.py` (the `rec` dict built in `record_episode`, lines 36-39)
- Test: `hsge/tests/test_recording.py`

**Interfaces:**
- Consumes: `Step.hints`, `Step.last_error`, `Step.url` (from Task 1 / pre-existing).
- Produces: each line of `episode.jsonl` now has `"hints"`, `"last_error"`, `"url"` keys in addition to the existing `record_type`/`index`/`action`/`parsed_action`/`thought`/`observation`.

- [ ] **Step 1: Write the failing test**

Add to `hsge/tests/test_recording.py`:

```python
def test_record_episode_persists_hints_last_error_and_url(tmp_path):
    steps = [Step(action="click('1')", url="http://s/a", axtree="ax1",
                   hints="try clicking the nav link", last_error=""),
             Step(action="send_msg_to_user('done')", url="http://s/b", axtree="ax2",
                   hints="", last_error="TimeoutError: element not found")]
    ep_id = record_episode(str(tmp_path), 0, "goal", steps, ["ax1", "ax2"], [None, None],
                           True, 1, "LOCAL")
    lines = [json.loads(l) for l in open(tmp_path / "episodes" / ep_id / "episode.jsonl")]
    assert lines[0]["hints"] == "try clicking the nav link"
    assert lines[0]["last_error"] == ""
    assert lines[0]["url"] == "http://s/a"
    assert lines[1]["last_error"] == "TimeoutError: element not found"
    assert lines[1]["url"] == "http://s/b"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest hsge/tests/test_recording.py -k persists_hints_last_error_and_url -v`
Expected: FAIL with `KeyError: 'hints'`

- [ ] **Step 3: Update `record_episode`**

In `hsge/webarena/recording.py`, the `rec` dict currently reads (lines 36-39):

```python
            rec = {"record_type": "step", "index": k,
                   "action": json.dumps({"thought": st.obs_summary, "action": st.action}),
                   "parsed_action": st.action, "thought": st.obs_summary,
                   "observation": observation}
```

Change it to:

```python
            rec = {"record_type": "step", "index": k,
                   "action": json.dumps({"thought": st.obs_summary, "action": st.action}),
                   "parsed_action": st.action, "thought": st.obs_summary,
                   "observation": observation, "hints": st.hints,
                   "last_error": st.last_error, "url": st.url}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest hsge/tests/test_recording.py -v`
Expected: PASS (all tests in the file, including the 2 pre-existing ones — confirms no regression)

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/recording.py hsge/tests/test_recording.py
git commit -m "Persist Step.hints/last_error/url into episode.jsonl"
```

---

### Task 3: Expand `ACTIONS_DOC`/`SOLVER_SYS` with `report_infeasible`/`press`/`hover`

**Files:**
- Modify: `hsge/webarena/agents.py` (the `ACTIONS_DOC` and `SOLVER_SYS` constants, lines 16-18 and 46-54)
- Test: `hsge/tests/test_solver.py`

**Interfaces:**
- Produces: `ACTIONS_DOC` (str) mentions `press`, `hover`, `report_infeasible`; `SOLVER_SYS` (str) includes a `report_infeasible` example.

- [ ] **Step 1: Write the failing test**

Add to `hsge/tests/test_solver.py`:

```python
def test_actions_doc_documents_the_three_new_actions():
    from hsge.webarena.agents import ACTIONS_DOC
    assert "report_infeasible(" in ACTIONS_DOC
    assert "press(" in ACTIONS_DOC
    assert "hover(" in ACTIONS_DOC


class _InfeasibleLLM:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"thought": "no email field exists on this page",
                "action": "report_infeasible('There is no email field on this page.')"}


def test_solver_ends_episode_as_failure_on_report_infeasible():
    llm = _InfeasibleLLM()
    solver = Solver(llm)
    browser = _FakeBrowser()

    steps, obs_texts, obs_screenshots, final_obs, success = solver.solve(browser, "goal")

    assert success is False
    assert len(steps) == 1
    assert steps[0].action.startswith("report_infeasible(")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest hsge/tests/test_solver.py -k "actions_doc or report_infeasible" -v`
Expected: FAIL — `report_infeasible(` not found in `ACTIONS_DOC`, and the solver test currently loops for `max_steps` calls instead of stopping after 1 (since `report_infeasible` isn't in the break condition yet), so `len(steps)` would be 15, not 1.

- [ ] **Step 3: Rewrite `ACTIONS_DOC` and `SOLVER_SYS`**

In `hsge/webarena/agents.py`, replace lines 16-18:

```python
ACTIONS_DOC = ("Allowed actions (return exactly one): click('bid'), "
               "fill('bid','text'), select_option('bid','opt'), goto('url'), "
               "go_back(), send_msg_to_user('done message').")
```

with:

```python
ACTIONS_DOC = (
    "Allowed actions (return exactly one):\n"
    "click('bid') -- click an element.\n"
    "fill('bid','text') -- type text into an input/textarea.\n"
    "select_option('bid','opt') -- choose an option in a <select>.\n"
    "press('bid','key') -- focus the element and press a key or combo, e.g. "
    "press('12','Enter') to submit a search box, press('12','Escape') to close a dialog.\n"
    "hover('bid') -- hover an element, e.g. to open a hover-only dropdown menu.\n"
    "goto('url') -- navigate to a URL.\n"
    "go_back() -- go to the previous page.\n"
    "report_infeasible('reason') -- use ONLY when the GOAL cannot be done on this "
    "site (e.g. a required field or page does not exist); explain why in 'reason'.\n"
    "send_msg_to_user('done message') -- use ONLY when the GOAL is fully achieved."
)
```

Then replace lines 46-54:

```python
SOLVER_SYS = (
    "You are a web agent. Reach the GOAL by choosing the single best next action from "
    "the page accessibility tree (elements shown as [bid] role 'name'). " + ACTIONS_DOC +
    " Think step by step; reflect on your past actions and any error from your last "
    "action before deciding. Output ONE action as JSON "
    "{\"thought\": \"...\", \"action\": \"<one action>\"}. "
    "Examples: {\"thought\": \"Open the product\", \"action\": \"click('12')\"} ; "
    "{\"thought\": \"Goal met\", \"action\": \"send_msg_to_user('done: price is $19')\"}. "
    "Call send_msg_to_user ONLY when the goal is fully achieved.")
```

with:

```python
SOLVER_SYS = (
    "You are a web agent. Reach the GOAL by choosing the single best next action from "
    "the page accessibility tree (elements shown as [bid] role 'name'). " + ACTIONS_DOC +
    " Think step by step; reflect on your past actions and any error from your last "
    "action before deciding. Output ONE action as JSON "
    "{\"thought\": \"...\", \"action\": \"<one action>\"}. "
    "Examples: {\"thought\": \"Open the product\", \"action\": \"click('12')\"} ; "
    "{\"thought\": \"Submit the search\", \"action\": \"press('9','Enter')\"} ; "
    "{\"thought\": \"Goal met\", \"action\": \"send_msg_to_user('done: price is $19')\"} ; "
    "{\"thought\": \"No email field exists on this page\", "
    "\"action\": \"report_infeasible('There is no email field on this page.')\"}. "
    "Call send_msg_to_user ONLY when the goal is fully achieved.")
```

Now add `report_infeasible` to the loop-termination condition. In `solve()`, the line currently reads (line 275):

```python
            if not action or action.startswith("send_msg_to_user"):
                break
```

Change to:

```python
            if not action or action.startswith("send_msg_to_user") or action.startswith("report_infeasible"):
                break
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest hsge/tests/test_solver.py -v`
Expected: PASS (all tests in the file, including the 4 pre-existing ones — confirms no regression to the repeat-warning/stuck-loop tests)

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/agents.py hsge/tests/test_solver.py
git commit -m "Solver: document press/hover/report_infeasible; stop on report_infeasible"
```

---

### Task 4: Extract `build_solver_prompt()`, wire it into `solve()`, store `hints`/`last_error` on `Step`

**Files:**
- Modify: `hsge/webarena/agents.py` (new module-level function; `solve()` body, lines 239-284)
- Test: `hsge/tests/test_solver.py`

**Interfaces:**
- Produces: `build_solver_prompt(goal: str, hints: str | None, history: list[str], progressed: list[bool], last_error: str, url: str, axtree: str) -> str` — pure function, no side effects, callable with the **full** (unsliced) `history`/`progressed` lists (it slices `history[-6:]` internally for display and passes the full lists to `Solver._stuck_streak`). This is the exact function `build_sft_dataset.py` (Task 5) will import and call.
- Consumes (internally): `Solver._stuck_streak(history, progressed)` and `Solver._action_target(action)` (existing classmethods, unchanged).

- [ ] **Step 1: Write the failing test**

Add to `hsge/tests/test_solver.py`:

```python
def test_build_solver_prompt_matches_what_solve_sends_to_the_llm():
    from hsge.webarena.agents import build_solver_prompt

    class _RecordingLLM:
        def __init__(self):
            self.last_prompt = None

        def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
            self.last_prompt = prompt
            return {"thought": "done", "action": "send_msg_to_user('done')"}

    llm = _RecordingLLM()
    solver = Solver(llm)
    browser = _FakeBrowser()

    solver.solve(browser, "find the price", hints="try the search box first")

    expected = build_solver_prompt("find the price", "try the search box first",
                                    [], [], "", "http://x", "[1] link 'next'")
    assert llm.last_prompt == expected


def test_step_records_hints_and_last_error_seen_at_that_step():
    class _ErrorsOnceThenDoneLLM:
        def __init__(self):
            self.calls = 0

        def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
            self.calls += 1
            if self.calls == 1:
                return {"thought": "click it", "action": "click('bad')"}
            return {"thought": "done", "action": "send_msg_to_user('done')"}

    class _FailsOnceBrowser(_FakeBrowser):
        def act(self, action):
            if action == "click('bad')":
                raise RuntimeError("element not found")
            return super().act(action)

    llm = _ErrorsOnceThenDoneLLM()
    solver = Solver(llm)
    browser = _FailsOnceBrowser()

    steps, *_ = solver.solve(browser, "goal", hints="a known procedure")

    # call 1: click('bad') fails (exception) -> recorded with last_error="" (no
    # prior error yet), the loop retries without incrementing history.
    # call 2: LLM (now on its 2nd call) returns send_msg_to_user -> recorded
    # with last_error="element not found" (carried in from call 1's failure).
    assert len(steps) == 2
    assert steps[0].action == "click('bad')"
    assert steps[0].hints == "a known procedure"
    assert steps[0].last_error == ""
    assert steps[1].action == "send_msg_to_user('done')"
    assert steps[1].last_error == "element not found"
```

Note: `_FakeBrowser`/`Solver` are already imported at the top of `hsge/tests/test_solver.py` from earlier tasks — no new imports needed beyond `build_solver_prompt`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest hsge/tests/test_solver.py -k "build_solver_prompt or records_hints" -v`
Expected: FAIL with `ImportError: cannot import name 'build_solver_prompt'`

- [ ] **Step 3: Add `build_solver_prompt()` and wire it into `solve()`**

In `hsge/webarena/agents.py`, add this function after the `Solver` class (i.e. at the end of the file, after the `return steps, obs_texts, obs_screenshots, obs, success` line that currently ends the file):

```python
def build_solver_prompt(goal: str, hints: str | None, history: list[str],
                        progressed: list[bool], last_error: str,
                        url: str, axtree: str) -> str:
    """Build the exact user-message text for one Solver step. Used live by
    Solver.solve() and offline by build_sft_dataset.py so both produce
    byte-identical prompts from the same inputs -- this is the only place
    that assembles this text.

    `history`/`progressed` are the full (unsliced) lists Solver.solve()
    maintains; this function slices history[-6:] for display and passes the
    full lists to Solver._stuck_streak, exactly matching solve()'s own logic.
    """
    streak = Solver._stuck_streak(history, progressed)
    repeat_warning = ""
    if streak >= Solver._WARN_AFTER_REPEATS:
        repeat_warning = (
            f"\n\nWARNING: your last {streak} actions all targeted "
            f"{Solver._action_target(history[-1])!r} with no visible progress -- "
            "repeating it again will not help. If the goal is already achieved, "
            "call send_msg_to_user(...) now instead. Otherwise choose a "
            "genuinely different action/target.")
    return (f"GOAL: {goal}\n"
            + (f"\nKNOWN PROCEDURES (from earlier runs, may help):\n{hints}\n"
               if hints else "")
            + "\nRECENT ACTIONS:\n"
            + ("\n".join(f"- {h}" for h in history[-6:]) or "(none)")
            + (f"\n\nLAST ACTION ERROR: {last_error}" if last_error else "")
            + repeat_warning
            + f"\n\nURL: {url}\n\nPAGE:\n{axtree[:6000]}")
```

Now replace the `solve()` loop body. It currently reads (lines 228-272, inside the `for _ in range(self.max_steps):` loop, up to the `steps.append(...)` call):

```python
        for _ in range(self.max_steps):
            streak = self._stuck_streak(history, progressed)
            if streak >= self._MAX_REPEATS:
                # A text nudge alone isn't reliably obeyed (verified against a
                # real run: the warning was present in the prompt from the 3rd
                # call onward and the model kept issuing the exact same click
                # anyway for all 15 steps). Stop spending steps on a target
                # that clearly isn't moving instead of exhausting max_steps.
                print(f"    [solver] giving up: target {self._action_target(history[-1])!r} "
                      f"hit {streak}x in a row with no progress")
                break
            repeat_warning = ""
            if streak >= self._WARN_AFTER_REPEATS:
                # The same target just got hit >=2 times in a row with no error --
                # e.g. clicking a nav link that navigated fine but re-appears
                # under a new bid on the destination page, so the model keeps
                # clicking it without realizing it already arrived. Nudge
                # instead of silently repeating the same prompt.
                repeat_warning = (
                    f"\n\nWARNING: your last {streak} actions all targeted "
                    f"{self._action_target(history[-1])!r} with no visible progress -- "
                    "repeating it again will not help. If the goal is already achieved, "
                    "call send_msg_to_user(...) now instead. Otherwise choose a "
                    "genuinely different action/target.")
            prompt = (f"GOAL: {goal}\n"
                      + (f"\nKNOWN PROCEDURES (from earlier runs, may help):\n{hints}\n"
                         if hints else "")
                      + "\nRECENT ACTIONS:\n"
                      + ("\n".join(f"- {h}" for h in history[-6:]) or "(none)")
                      + (f"\n\nLAST ACTION ERROR: {last_error}" if last_error else "")
                      + repeat_warning
                      + f"\n\nURL: {obs['url']}\n\nPAGE:\n{obs['axtree'][:6000]}")
            screenshot_b64 = browser.screenshot_b64(som=self.som) if self.vision else None
            out = self.llm.complete_json(SOLVER_SYS, prompt,
                                          image_b64=screenshot_b64, image_detail=self.image_detail)
            if screenshot_b64 and not (out.get("action") or "").strip():
                # same rationale as PageExplorer.propose(): don't let a refused/
                # empty vision call silently end the episode -- try text-only.
                print("    [solver] empty response with image attached, retrying text-only")
                out = self.llm.complete_json(SOLVER_SYS, prompt,
                                              image_b64=None, image_detail=self.image_detail)
            action = (out.get("action") or "").strip()
            thought = out.get("thought", "")
            steps.append(Step(action=action, url=obs["url"], obs_summary=thought[:100],
                              axtree=obs["axtree"]))
```

Replace with:

```python
        for _ in range(self.max_steps):
            streak = self._stuck_streak(history, progressed)
            if streak >= self._MAX_REPEATS:
                # A text nudge alone isn't reliably obeyed (verified against a
                # real run: the warning was present in the prompt from the 3rd
                # call onward and the model kept issuing the exact same click
                # anyway for all 15 steps). Stop spending steps on a target
                # that clearly isn't moving instead of exhausting max_steps.
                print(f"    [solver] giving up: target {self._action_target(history[-1])!r} "
                      f"hit {streak}x in a row with no progress")
                break
            prompt = build_solver_prompt(goal, hints, history, progressed, last_error,
                                         obs["url"], obs["axtree"])
            screenshot_b64 = browser.screenshot_b64(som=self.som) if self.vision else None
            out = self.llm.complete_json(SOLVER_SYS, prompt,
                                          image_b64=screenshot_b64, image_detail=self.image_detail)
            if screenshot_b64 and not (out.get("action") or "").strip():
                # same rationale as PageExplorer.propose(): don't let a refused/
                # empty vision call silently end the episode -- try text-only.
                print("    [solver] empty response with image attached, retrying text-only")
                out = self.llm.complete_json(SOLVER_SYS, prompt,
                                              image_b64=None, image_detail=self.image_detail)
            action = (out.get("action") or "").strip()
            thought = out.get("thought", "")
            steps.append(Step(action=action, url=obs["url"], obs_summary=thought[:100],
                              axtree=obs["axtree"], hints=hints or "", last_error=last_error))
```

(The rest of the loop body — the `if not action or ...: break` check onward — is unchanged from Task 3.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest hsge/tests/test_solver.py -v`
Expected: PASS (all tests in the file — 6 pre-existing + 4 new from Tasks 3-4)

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/agents.py hsge/tests/test_solver.py
git commit -m "Extract build_solver_prompt(); Solver records hints/last_error per step"
```

---

### Task 5: `build_sft_dataset.py` uses `build_solver_prompt()` instead of a hand-rolled template

**Files:**
- Modify: `build_sft_dataset.py` (whole file: remove `SYSTEM`, `_read_axtree`; rewrite `episode_to_examples`)
- Test: `hsge/tests/test_build_sft.py`

**Interfaces:**
- Consumes: `hsge.webarena.agents.SOLVER_SYS`, `hsge.webarena.agents.build_solver_prompt` (from Task 4).
- Produces: `episode_to_examples(goal: str, steps: list[dict], episode_dir: str, difficulty: int) -> list[dict]` — same name/signature as before; each returned dict is now `{"messages": [...], "difficulty": int}` (the `axtree_loaded` key is removed).

- [ ] **Step 1: Write the failing tests**

Replace the contents of `hsge/tests/test_build_sft.py` with:

```python
"""build_sft_dataset gates on verification (only verified GEN episodes are
kept by default) and rebuilds each example's prompt via the same
build_solver_prompt() Solver.solve() uses live, so training data matches
what the Solver actually saw."""
import json

from hsge.schema import Step
from hsge.webarena.agents import SOLVER_SYS, build_solver_prompt
from hsge.webarena.recording import record_episode
from build_sft_dataset import build, episode_to_examples


def _mk(tmp_path, idx, tag, success, extra=None, difficulty=1, steps=None):
    steps = steps or [Step(action="click('1')", url="u", axtree="ax", hints="", last_error="")]
    record_episode(str(tmp_path), idx, f"goal {idx}", steps,
                   [s.axtree for s in steps], [None] * len(steps),
                   success, difficulty, tag, extra_meta=extra)


def test_default_keeps_only_verified_gen(tmp_path):
    _mk(tmp_path, 0, "GEN", True, {"task_id": "gen_0000", "verified": True}, difficulty=3)
    _mk(tmp_path, 1, "GEN", False, {"task_id": "gen_0001", "verified": False})
    _mk(tmp_path, 2, "LOCAL", True)
    out = tmp_path / "train.jsonl"
    stats = build(str(tmp_path), str(out))
    assert stats["kept"] == 1
    (ex,) = [json.loads(l) for l in open(out)]
    assert ex["difficulty"] == 3


def test_include_local_admits_self_reported_successes(tmp_path):
    _mk(tmp_path, 0, "GEN", True, {"task_id": "gen_0000", "verified": True})
    _mk(tmp_path, 1, "LOCAL", True)
    _mk(tmp_path, 2, "LOCAL", False)     # failures never enter
    stats = build(str(tmp_path), str(tmp_path / "t.jsonl"), include_local=True)
    assert stats["kept"] == 2


def test_example_messages_match_build_solver_prompt_exactly(tmp_path):
    steps = [Step(action="click('1')", url="http://s/a", axtree="[1] link 'next'",
                   hints="try the nav menu", last_error="")]
    _mk(tmp_path, 0, "LOCAL", True, steps=steps)
    examples = episode_to_examples("find the price", [
        {"action": "click('1')", "url": "http://s/a", "hints": "try the nav menu",
         "last_error": "", "observation": {"axtree_txt": {"path": "page_state/step_000_axtree.txt"}}},
    ], str(tmp_path / "episodes" / "ep_0000"), difficulty=1)

    expected_prompt = build_solver_prompt("find the price", "try the nav menu", [], [],
                                          "", "http://s/a", "[1] link 'next'")
    assert examples == [{
        "messages": [
            {"role": "system", "content": SOLVER_SYS},
            {"role": "user", "content": expected_prompt},
            {"role": "assistant", "content": "click('1')"},
        ],
        "difficulty": 1,
    }]


def test_step_missing_prompt_fidelity_fields_is_skipped(tmp_path):
    # Simulates a pre-change episode: no "hints"/"last_error"/"url" keys at all.
    legacy_steps = [{"action": "click('1')", "parsed_action": "click('1')",
                     "observation": {"axtree_txt": {"path": "page_state/step_000_axtree.txt"}}}]
    examples = episode_to_examples("goal", legacy_steps, str(tmp_path), difficulty=1)
    assert examples == []


def test_error_step_is_excluded_from_next_steps_history():
    # step 0 (click('nav')) succeeds -- proven by step 1's last_error being "".
    # step 1 (click('bad')) fails -- proven by step 2's last_error being set.
    # step 2's prompt must show the failure and must list click('nav') but not
    # click('bad') in RECENT ACTIONS.
    steps = [
        {"action": "click('nav')", "url": "http://s/a", "hints": "", "last_error": "",
         "observation": {}},
        {"action": "click('bad')", "url": "http://s/b", "hints": "", "last_error": "",
         "observation": {}},
        {"action": "send_msg_to_user('done')", "url": "http://s/b", "hints": "",
         "last_error": "element not found", "observation": {}},
    ]
    examples = episode_to_examples("goal", steps, "/nonexistent", difficulty=1)
    assert len(examples) == 3
    recent = examples[2]["messages"][1]["content"]
    assert "LAST ACTION ERROR: element not found" in recent
    assert "click('nav')" in recent
    assert "click('bad')" not in recent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest hsge/tests/test_build_sft.py -v`
Expected: FAIL — `ImportError: cannot import name 'episode_to_examples'` is already importable, but the new tests fail on assertions (`axtree_loaded` key still present, `SYSTEM` still hand-rolled, no skip-on-missing-fields behavior) or `ImportError: cannot import name 'build_solver_prompt' from 'hsge.webarena.agents'` if Task 4 wasn't completed first.

- [ ] **Step 3: Rewrite `build_sft_dataset.py`**

Replace the file's `SYSTEM` constant, `_read_axtree`, and `episode_to_examples` (currently lines 28-81) with:

```python
from hsge.webarena.agents import SOLVER_SYS, build_solver_prompt


def _load_axtree(episode_dir: str, step: dict) -> str:
    """Load the step's full accessibility-tree text from disk."""
    obs = step.get("observation")
    if not isinstance(obs, dict):
        return ""
    node = obs.get("axtree_txt")
    if isinstance(node, dict) and node.get("path"):
        p = node["path"] if os.path.isabs(node["path"]) else os.path.join(episode_dir, node["path"])
        if os.path.exists(p):
            return open(p, encoding="utf-8", errors="ignore").read()
    return ""


def _difficulty(task_info: dict, episode_meta: dict) -> int:
    # GOAL/composed tasks carry an explicit difficulty; local tasks default to 1.
    for src in (task_info, episode_meta, episode_meta.get("metadata", {})):
        if isinstance(src, dict) and isinstance(src.get("difficulty"), int):
            return src["difficulty"]
    return 1


def episode_to_examples(goal: str, steps: list[dict], episode_dir: str,
                        difficulty: int) -> list[dict]:
    """Replay an episode's persisted steps and rebuild each step's exact
    Solver prompt via build_solver_prompt() -- the same function
    Solver.solve() calls live -- so training data matches inference exactly.
    A step recorded before hints/last_error/url were persisted is skipped
    rather than approximated with a different template."""
    examples: list[dict] = []
    history: list[str] = []
    progressed: list[bool] = []
    n = len(steps)
    for i, step in enumerate(steps):
        target = step.get("action")
        if not target:
            continue
        url = step.get("url")
        hints = step.get("hints")
        last_error = step.get("last_error")
        if url is None or hints is None or last_error is None:
            continue    # pre-fidelity episode: not enough data to rebuild the exact prompt
        axtree = _load_axtree(episode_dir, step)
        prompt = build_solver_prompt(goal, hints, history, progressed, last_error, url, axtree)
        examples.append({
            "messages": [
                {"role": "system", "content": SOLVER_SYS},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": target},
            ],
            "difficulty": difficulty,
        })
        if i + 1 < n and not steps[i + 1].get("last_error"):
            next_url = steps[i + 1].get("url")
            next_axtree = _load_axtree(episode_dir, steps[i + 1])
            history.append(target)
            progressed.append(url != next_url or axtree != next_axtree)
    return examples
```

Note: `import os` is already at the top of `build_sft_dataset.py` (used elsewhere); `glob`/`json` imports are unaffected. `load_episodes`, `_keep`, and `build()` are unchanged — `build()` already calls `episode_to_examples(goal, steps, ep_dir, diff)` with the same signature.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest hsge/tests/test_build_sft.py -v`
Expected: PASS (all 6 tests)

Then run the full suite to confirm no regressions:

Run: `python -m pytest hsge/tests/ -q`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add build_sft_dataset.py hsge/tests/test_build_sft.py
git commit -m "build_sft_dataset: rebuild exact Solver prompts via build_solver_prompt()"
```

---

## Post-plan note (not a task)

Existing runs `outputs/wa_run_01`..`wa_run_05` predate this change and will
contribute 0 SFT examples per episode until re-run (`build_sft_dataset.py`
skips every step missing `hints`/`last_error`/`url`) — this is intentional
per the spec, not a bug to fix here.
