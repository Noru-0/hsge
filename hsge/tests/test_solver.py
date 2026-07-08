"""Solver must not silently give up on a step when a vision-attached call
gets refused/empty -- retry once text-only before treating it as a dead end.
"""

from hsge.webarena.agents import Solver, ACTIONS_DOC


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

    steps, obs_texts, obs_screenshots, final_obs, success = solver.solve(browser, "goal")

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

    steps, obs_texts, obs_screenshots, final_obs, success = solver.solve(browser, "goal")

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
    solver must stop calling the LLM entirely instead of burning the rest
    of max_steps on a model that keeps ignoring the warning."""
    llm = _StubbornRepeatLLM()
    solver = Solver(llm, max_steps=15)
    browser = _FakeBrowser()

    steps, obs_texts, obs_screenshots, final_obs, success = solver.solve(browser, "goal")

    assert success is False
    assert len(steps) == Solver._MAX_REPEATS  # gave up well before max_steps=15
    assert llm.calls == Solver._MAX_REPEATS


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

    steps, obs_texts, obs_screenshots, final_obs, success = solver.solve(browser, "goal")

    assert success is False
    assert len(steps) == Solver._MAX_REPEATS
    assert all("378" in s.action for s in steps)


def test_actions_doc_documents_the_three_new_actions():
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
