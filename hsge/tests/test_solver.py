"""Solver must not silently give up on a step when a vision-attached call
gets refused/empty -- retry once text-only before treating it as a dead end.
"""

from hsge.webarena.agents import Solver


class _FakeBrowser:
    def __init__(self):
        self.acted = []

    def observation(self):
        return {"url": "http://x", "axtree": "[1] link 'next'"}

    def screenshot_b64(self, som=False):
        return "ZmFrZQ=="

    def act(self, action):
        self.acted.append(action)
        return self.observation()


class _RefusesWithImageLLM:
    """Refuses (empty response) only when an image is attached; the
    text-only retry succeeds by declaring the goal done."""

    def __init__(self):
        self.calls = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.calls.append(image_b64)
        if image_b64:
            return {}
        return {"thought": "done", "action": "send_msg_to_user('done')"}


def test_solver_retries_without_image_when_vision_call_is_refused():
    llm = _RefusesWithImageLLM()
    solver = Solver(llm, vision=True)
    browser = _FakeBrowser()

    steps, obs_texts, obs_screenshots, final_obs, success, infeasible, _ = solver.solve(browser, "goal")

    assert success is True
    assert len(steps) == 1
    assert steps[0].action == "send_msg_to_user('done')"
    assert llm.calls == ["ZmFrZQ==", None]


class _LoopThenRecoverLLM:
    """Keeps clicking the same bid (as if it already arrived and doesn't
    recognize it) until the solver's repeated-action warning shows up in the
    prompt, then declares done -- simulates the ep_0004-style real-run loop
    where the same action succeeded twice in a row with no error and no
    progress, and the model needed an explicit nudge to stop."""

    def __init__(self):
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        if "WARNING" in prompt:
            return {"thought": "already there", "action": "send_msg_to_user('done')"}
        return {"thought": "click nav link", "action": "click('39')"}


def test_solver_warns_and_recovers_from_a_repeated_no_progress_action():
    """Regression: a real run showed the solver click the same bid 13-14
    times in a row (the target link keeps re-appearing under a new bid on
    the page it just navigated to) and burn the full max_steps budget on
    every such episode. Once the same action has succeeded twice in a row
    with no error, the solver must warn the model instead of silently
    repeating the prompt unchanged."""
    llm = _LoopThenRecoverLLM()
    solver = Solver(llm, max_steps=15)
    browser = _FakeBrowser()

    steps, obs_texts, obs_screenshots, final_obs, success, infeasible, _ = solver.solve(browser, "goal")

    assert success is True
    assert len(steps) == 3  # recovered on the 3rd call instead of burning all 15
    assert steps[-1].action == "send_msg_to_user('done')"
    assert any("WARNING" in p for p in llm.prompts)


class _StubbornRepeatLLM:
    """Never listens to the repeat warning -- keeps issuing the exact same
    action regardless of prompt content. Reproduces a real run (ep_0003,
    outputs/wa_run_01) where click('117') was issued unchanged for the full
    15-step budget: page_state axtree dumps confirmed the page never
    changed at all, yet the WARNING nudge alone (present in the prompt from
    the 3rd call onward) was not enough to make the model stop."""

    def __init__(self):
        self.calls = 0

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.calls += 1
        return {"thought": "Navigate to the Submissions page", "action": "click('117')"}


def test_solver_gives_up_after_max_repeats_when_model_ignores_the_warning():
    """A soft nudge isn't always obeyed -- once the same target has been
    interacted with _MAX_REPEATS times in a row with no progress, the
    solver stops the action loop, then makes exactly one wrap-up call; a
    non-terminal wrap-up answer (this mock still says click) is discarded."""
    llm = _StubbornRepeatLLM()
    solver = Solver(llm, max_steps=15)
    browser = _FakeBrowser()

    steps, obs_texts, obs_screenshots, final_obs, success, infeasible, _ = solver.solve(browser, "goal")

    assert success is False
    assert infeasible is False
    assert len(steps) == Solver._MAX_REPEATS      # wrap-up click was discarded
    assert llm.calls == Solver._MAX_REPEATS + 1   # action loop + 1 wrap-up call


class _SameTargetDifferentArgsLLM:
    """Keeps retrying the same dropdown (bid 378) with different-looking
    but equally ineffective option text each time. Reproduces a real run
    (ep_0005, outputs/wa_run_01) where select_option('378', ...) was called
    9 times in a row with varying arguments while the combobox's value
    never actually changed (confirmed via page_state axtree diffs) -- the
    *action string* never repeats exactly, but the *target* (bid 378)
    does, so detection must key off the target, not literal string equality."""

    def __init__(self, options):
        self._options = list(options)
        self.calls = 0

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.calls += 1
        opt = self._options[min(self.calls - 1, len(self._options) - 1)]
        return {"thought": "select a forum", "action": f"select_option('378', '{opt}')"}


def test_solver_gives_up_on_same_target_repeated_with_different_arguments():
    llm = _SameTargetDifferentArgsLLM(
        ["Choose one", "Forum Name", "Another Forum Name", "Forum Name"])
    solver = Solver(llm, max_steps=15)
    browser = _FakeBrowser()

    steps, obs_texts, obs_screenshots, final_obs, success, infeasible, _ = solver.solve(browser, "goal")

    assert success is False
    assert len(steps) == Solver._MAX_REPEATS
    assert all("378" in s.action for s in steps)
    assert llm.calls == Solver._MAX_REPEATS + 1


class _NavOnceBrowser:
    """First act() navigates to /wiki; every later act() changes nothing
    (the sitewide 'Wiki' link is still on the destination page)."""

    def __init__(self):
        self.i = 0

    def observation(self):
        if self.i == 0:
            return {"url": "http://x/", "axtree": "[24] link 'Wiki'"}
        return {"url": "http://x/wiki", "axtree": "[7] heading 'Wiki'\n[24] link 'Wiki'"}

    def screenshot_b64(self, som=False):
        return None

    def act(self, action):
        self.i += 1
        return self.observation()


class _ArrivesButKeepsClickingLLM:
    """Clicks the same nav link forever (never realizes it arrived); only
    the wrap-up prompt makes it declare done. Mirrors the dominant real-run
    NAV failure (wa_run_07: 116 NAV fails, model on the right page but
    still clicking)."""

    def __init__(self):
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        # Match the wrap-up by its stable closing instruction, not by the opening
        # sentence: that now varies with WHY the episode stopped (budget vs a
        # guard), so keying on "budget is exhausted" silently stopped matching.
        if "Answer with one of those two actions only." in prompt:
            return {"thought": "already on the wiki page",
                    "action": "send_msg_to_user('done: on the wiki page')"}
        return {"thought": "go to wiki", "action": "click('24')"}


def test_wrapup_call_converts_arrived_but_undeclared_into_success():
    llm = _ArrivesButKeepsClickingLLM()
    solver = Solver(llm, max_steps=15)

    steps, obs_texts, obs_screenshots, final_obs, success, infeasible, _ = solver.solve(
        _NavOnceBrowser(), "[NAV] Go to the Wiki page")

    assert success is True
    assert infeasible is False
    assert steps[-1].action.startswith("send_msg_to_user")


def test_history_lines_carry_outcome_annotations():
    llm = _ArrivesButKeepsClickingLLM()
    solver = Solver(llm, max_steps=15)
    solver.solve(_NavOnceBrowser(), "[NAV] Go to the Wiki page")

    # the 2nd action-loop prompt must show the first click actually navigated
    assert any("click('24') -> now at http://x/wiki" in p for p in llm.prompts)
    # and later repeats must be visibly inert
    assert any("click('24') -> no change" in p for p in llm.prompts)


class _InfeasibleLLM:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"thought": "requires admin rights",
                "action": "report_infeasible('requires admin rights')"}


def test_report_infeasible_ends_episode_without_acting():
    browser = _FakeBrowser()
    steps, obs_texts, obs_screenshots, final_obs, success, infeasible, _ = Solver(
        _InfeasibleLLM()).solve(browser, "goal")

    assert infeasible is True
    assert success is False
    assert len(steps) == 1
    assert browser.acted == []   # report_infeasible is never sent to the browser


def test_no_wrapup_for_predicate_goals():
    """GOAL tasks are verified by reached(); the wrap-up call must not fire."""
    llm = _StubbornRepeatLLM()
    solver = Solver(llm, max_steps=15)

    steps, obs_texts, obs_screenshots, final_obs, success, infeasible, _ = solver.solve(
        _FakeBrowser(), "goal", goal_predicate="order_confirmed")

    assert success is False
    assert llm.calls == Solver._MAX_REPEATS   # no +1: wrap-up skipped


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
