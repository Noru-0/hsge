"""The Solver's anti-loop guards must see FAILED actions too.

Measured on outputs/wa_eval_shopping_1 (shopping, 179 nodes, 1069 episodes,
9065 steps): 4115 steps (45.4%) ended in an action error, and 118 episodes
spent ALL 15 steps issuing the same failing action against the same bid
(e.g. click('229') on `link 'My Wish List'`, whose Playwright click timed out
at BrowserGym's hardcoded 500ms element timeout, 15x in a row). None of the
three guards could stop them: `Solver.solve` appended the error to the step's
thought and `continue`d *before* history/outcomes/progressed were updated, so
the same-target guard and the novelty guard were both blind to a repeated
failure and only the budget guard could end the episode -- after burning the
whole budget, at which point the wrap-up call rationalised
`report_infeasible('action budget exhausted, ...')` (199 of the run's 222
infeasible episodes carry a non-empty stop_reason).

Run: PYTHONPATH=. python -m pytest hsge/tests/test_failed_action_guards.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hsge.webarena.agents import ACTIONS_DOC, Solver, failed_outcome
from hsge.webarena.browser import ActionError


class _AlwaysFailingBrowser:
    """Every action raises, exactly like a click on a non-actionable element."""
    terminated = False

    def __init__(self, error="TimeoutError: Locator.click: Timeout 500ms exceeded."):
        self.error = error
        self.n_acts = 0

    def observation(self):
        return {"url": "http://x/wishlist", "axtree": "[229] link 'My Wish List'"}

    def screenshot_b64(self, som=False):
        return None

    def act(self, action):
        self.n_acts += 1
        raise ActionError(self.error)


class _HammerLLM:
    """Keeps issuing the same failing action -- the observed real behaviour."""
    def __init__(self):
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        return {"thought": "click the wish list link", "action": "click('229')"}


class _WanderLLM:
    """A different target every step, all of them failing."""
    def __init__(self):
        self.n = 0

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.n += 1
        return {"thought": "try another element", "action": f"click('{self.n}')"}


def test_stuck_guard_fires_on_a_repeated_FAILING_action():
    llm = _HammerLLM()
    browser = _AlwaysFailingBrowser()
    steps, _, _, _, success, infeasible, stop_reason = Solver(llm, max_steps=15).solve(
        browser, "[COMPOSITE] Check the details of the first item in 'My Wish List'")

    # stopped by the same-target guard, NOT by exhausting all 15 steps
    assert stop_reason == "stuck"
    assert browser.n_acts <= Solver._MAX_REPEATS + 1
    assert not success


def test_novelty_guard_fires_when_every_target_differs_but_all_fail():
    browser = _AlwaysFailingBrowser()
    steps, _, _, _, _, _, stop_reason = Solver(_WanderLLM(), max_steps=40).solve(
        browser, "goal")

    # different bids every step dodge the same-target guard; novelty must catch it
    assert stop_reason == "novelty"
    assert browser.n_acts <= Solver._NOVELTY_MAX + 2


def test_failed_action_is_recorded_in_the_prompt_history():
    llm = _HammerLLM()
    Solver(llm, max_steps=15).solve(_AlwaysFailingBrowser(), "goal")

    # by the 3rd call the model must SEE that its earlier attempts failed --
    # previously the history section still read "(none)", so it re-derived the
    # same action from an apparently untouched page.
    assert len(llm.prompts) >= 3
    third = llm.prompts[2]
    assert "- click('229') -> action failed: TimeoutError" in third
    assert "# History of Past Actions\n(none)" not in third


def test_a_successful_action_after_a_failure_resets_the_streak():
    """The guard must not punish a recovery: one failure followed by real
    progress leaves no streak behind."""

    class _FailOnceBrowser:
        terminated = False

        def __init__(self):
            self.n = 0

        def observation(self):
            return {"url": f"http://x/{self.n}", "axtree": f"page {self.n}"}

        def screenshot_b64(self, som=False):
            return None

        def act(self, action):
            self.n += 1
            if self.n == 1:
                raise ActionError("TimeoutError: Locator.click: Timeout 500ms exceeded.")
            return self.observation()

    steps, _, _, _, _, _, stop_reason = Solver(_WanderLLM(), max_steps=6).solve(
        _FailOnceBrowser(), "goal")
    assert stop_reason == "budget"      # ran the full budget, no guard fired
    assert len(steps) == 6


def test_failed_outcome_is_a_single_capped_line():
    line = failed_outcome("TimeoutError: Locator.click: Timeout 500ms exceeded.\n"
                          "Call log:\n  - waiting for element" + "x" * 300)
    assert "\n" not in line
    assert line.startswith("action failed: TimeoutError")
    assert len(line) < 120


def test_actions_doc_documents_scroll_hover_and_noop():
    """browsergym's `bid` subset (which browser.py enables) already executes
    scroll/hover/noop -- only the prompt was hiding them, so the model had no
    way to make a non-actionable element actionable and just re-clicked it."""
    for action in ("scroll(", "hover(", "noop("):
        assert action in ACTIONS_DOC


def test_offline_history_matches_the_live_prompt_for_an_error_step(tmp_path):
    """build_sft_dataset must reproduce the live history line for a failed
    action, or every recovery step would train on a prompt the model never saw.
    The failed action stays out of the TARGETS -- it is the mistake."""
    from build_sft_dataset import episode_to_examples
    import json as _json

    steps = [
        {"index": 0, "url": "http://x/p", "parsed_action": "click('229')",
         "thought": "click the wish list link [action error: TimeoutError: "
                    "Locator.click: Timeout 500ms exceeded.]", "observation": {}},
        {"index": 1, "url": "http://x/p", "parsed_action": "click('231')",
         "thought": "that one timed out, try the header link", "observation": {}},
        {"index": 2, "url": "http://x/wishlist",
         "parsed_action": "send_msg_to_user('done: 3 items')",
         "thought": "found it", "observation": {}},
    ]
    examples = episode_to_examples("[INFO] check the wish list", steps,
                                   str(tmp_path), 1, "ep_0000")

    actions = [_json.loads(e["messages"][2]["content"])["action"] for e in examples]
    assert actions == ["click('231')", "send_msg_to_user('done: 3 items')"]
    # the failed action is in the recovery step's history, with the live wording
    recovery_prompt = examples[0]["messages"][1]["content"]
    assert "- click('229') -> action failed: TimeoutError" in recovery_prompt
    # ...and its error is still in the error section (unchanged behaviour)
    assert "# Error Message from Last Action\nTimeoutError" in recovery_prompt
