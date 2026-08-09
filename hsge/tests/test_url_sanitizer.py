"""Host-independent URLs: the observation's URL field and same-origin `goto`
targets are site-relative, so a model trained on one WebArena instance works on
another.

train_all.jsonl carried the collection host in 93% of its prompts
(192.168.1.31:8080/8023/8081) and in every absolute `goto` target, while the
eval instance was a different host entirely. The three helpers here are shared
by the live Solver prompt (agents.py), the offline SFT builder
(build_sft_dataset.py) and the executor (browser.py), so training and inference
see the same shape and a relative goto still runs in the browser.

Run:  python -m pytest hsge/tests/test_url_sanitizer.py -q
 (or) PYTHONPATH=. python hsge/tests/test_url_sanitizer.py
"""
from hsge.webarena.urls import absolutize_goto, relativize_goto, site_relative


def test_site_relative_strips_scheme_and_host():
    assert site_relative("http://192.168.1.31:8080/f/pics") == "/f/pics"


def test_site_relative_keeps_query_and_fragment():
    assert site_relative("http://192.168.1.31:8081/electronics.html?cat=6&p=2") == \
        "/electronics.html?cat=6&p=2"
    assert site_relative("http://h/checkout/cart/#payment") == "/checkout/cart/#payment"


def test_site_relative_root_is_a_single_slash():
    assert site_relative("http://192.168.1.31:8080") == "/"
    assert site_relative("http://192.168.1.31:8080/") == "/"


def test_site_relative_passes_through_relative_and_empty():
    assert site_relative("/f/pics") == "/f/pics"
    assert site_relative("") == ""
    assert site_relative("about:blank") == "about:blank"


def test_relativize_goto_rewrites_same_origin_target():
    assert relativize_goto("goto('http://192.168.1.31:8080/f/AskReddit')",
                           "http://192.168.1.31:8080/f/pics") == "goto('/f/AskReddit')"


def test_relativize_goto_leaves_off_origin_target_alone():
    """Off-origin gotos are dropped as targets elsewhere (they end a WebArena
    episode at reward 0); rewriting one to a relative path would silently turn
    it into a legal same-site action, which is worse than leaving it visible."""
    a = "goto('https://www.reddit.com/r/AskReddit/')"
    assert relativize_goto(a, "http://192.168.1.31:8080/f/pics") == a


def test_relativize_goto_ignores_non_goto_actions():
    assert relativize_goto("click('24')", "http://h/") == "click('24')"


def test_absolutize_goto_resolves_relative_against_current_origin():
    """Playwright's page.goto needs an absolute URL (BrowserGym sets no
    baseURL), so the executor has to put the origin back before stepping."""
    assert absolutize_goto("goto('/f/AskReddit')", "http://10.0.0.5:8080/f/pics") == \
        "goto('http://10.0.0.5:8080/f/AskReddit')"


def test_absolutize_goto_leaves_absolute_target_untouched():
    a = "goto('http://10.0.0.5:8080/f/x')"
    assert absolutize_goto(a, "http://10.0.0.5:8080/f/pics") == a


def test_absolutize_goto_is_a_noop_without_a_base_url():
    a = "goto('/f/x')"
    assert absolutize_goto(a, "") == a


def test_roundtrip_relativize_then_absolutize_on_a_new_host():
    """The point of the pair: an action learned on the collection host runs
    unchanged on the eval host."""
    learned = relativize_goto("goto('http://192.168.1.31:8080/f/books')",
                              "http://192.168.1.31:8080/f/pics")
    assert absolutize_goto(learned, "https://eval-host.example.com/f/pics") == \
        "goto('https://eval-host.example.com/f/books')"


# ---- wiring: the same shape at collection, training and execution ---------

class _CapturingLLM:
    def __init__(self):
        self.prompts = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.prompts.append(prompt)
        return {"thought": "done", "action": "send_msg_to_user('done')"}


class _FakeBrowser:
    def __init__(self, url="http://192.168.1.31:8080/f/pics"):
        self.url = url
        self.acted = []

    def observation(self):
        return {"url": self.url, "axtree": "[1] link 'next'"}

    def screenshot_b64(self, som=False):
        return None

    def act(self, action):
        self.acted.append(action)
        return self.observation()


def test_solver_prompt_shows_a_site_relative_url():
    """Parity with the SFT prompt: if training strips the host, inference must
    strip it too, or the model meets a field shape it never saw."""
    from hsge.webarena.agents import Solver

    llm = _CapturingLLM()
    Solver(llm).solve(_FakeBrowser(), "goal")

    prompt = llm.prompts[0]
    assert "/f/pics" in prompt
    assert "192.168.1.31" not in prompt


def test_browser_act_absolutizes_a_relative_goto_before_stepping():
    """The model emits `goto('/f/x')` because that is what it was trained on;
    Playwright needs the origin back, so act() restores it from the page the
    agent is currently on -- which is what makes the action portable."""
    from hsge.webarena.browser import WebArenaBrowser

    class _Env:
        def __init__(self):
            self.stepped = []

        def step(self, action):
            self.stepped.append(action)
            return ({"url": "http://10.0.0.5:8080/f/x", "last_action_error": ""},
                    0.0, False, False, {})

    browser = object.__new__(WebArenaBrowser)
    browser.env = _Env()
    browser._last_obs = {"url": "http://10.0.0.5:8080/f/pics"}
    browser.terminated = False

    browser.act("goto('/f/x')")

    assert browser.env.stepped == ["goto('http://10.0.0.5:8080/f/x')"]


def test_sft_prompt_and_target_are_host_free():
    import tempfile

    from build_sft_dataset import episode_to_examples

    ep_dir = tempfile.mkdtemp()
    from hsge.tests.test_build_sft_dataset import _step
    steps = [
        _step(ep_dir, 0, "http://192.168.1.31:8080/f/pics", "ax0", "jump",
             "goto('http://192.168.1.31:8080/f/books')"),
        _step(ep_dir, 1, "http://192.168.1.31:8080/f/books", "ax1", "done",
             "send_msg_to_user('done')"),
    ]

    examples = episode_to_examples("goal", steps, ep_dir, difficulty=1,
                                    trajectory_id="ep_0000")

    first = examples[0]
    assert "192.168.1.31" not in first["messages"][1]["content"]
    assert "URL: /f/pics" in first["messages"][1]["content"]
    import json as _json
    assert _json.loads(first["messages"][2]["content"])["action"] == "goto('/f/books')"
    # the history line the next step sees is host-free too
    assert "192.168.1.31" not in examples[1]["messages"][1]["content"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
