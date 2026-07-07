"""WebArena-style eval: string_match on the send_msg_to_user answer, url_match
on the final URL, program_html against the live page. Only these verdicts gate
what counts as a verified trajectory."""
from hsge.schema import Step
from hsge.webarena.evaluator import (evaluate, extract_answer, normalize_answer,
                                     program_html, string_match, url_match)


def test_normalize_and_extract_answer():
    assert normalize_answer("  The Author is HLZ0. ") == "the author is hlz0"
    steps = [Step(action="click('1')", url="u"),
             Step(action="send_msg_to_user('done: 45 comments')", url="u")]
    assert extract_answer(steps) == "done: 45 comments"
    assert extract_answer([Step(action="click('1')", url="u")]) == ""


def test_string_match_exact_and_must_include():
    assert string_match("HLZ0.", {"exact_match": "hlz0"})
    assert not string_match("someone else", {"exact_match": "hlz0"})
    assert string_match("done: it has 45 comments", {"must_include": ["45", "comments"]})
    assert not string_match("done: 44", {"must_include": ["45"]})
    assert not string_match("anything", {})   # no reference -> never verified


class _Judge:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        return {"match": "same meaning" in prompt}


def test_string_match_fuzzy_uses_judge():
    assert string_match("x", {"fuzzy_match": ["same meaning"]}, judge=_Judge())
    assert not string_match("x", {"fuzzy_match": ["same meaning"]}, judge=None)


class _CountingJudge:
    def __init__(self, match):
        self.match, self.calls = match, 0
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.calls += 1
        return {"match": self.match}


def test_string_match_falls_back_to_judge_on_format_drift():
    j = _CountingJudge(True)
    assert string_match("done: score is 1", {"exact_match": "1 point"}, judge=j)
    assert j.calls == 1
    j = _CountingJudge(True)
    assert string_match("done: it has 2 comments in total",
                        {"must_include": ["2 comments", "movies"]}, judge=j)
    assert j.calls == 1
    # judge verdict is still binding: no match -> fail
    assert not string_match("done: score is 1", {"exact_match": "1 point"},
                            judge=_CountingJudge(False))
    # no judge configured -> behavior unchanged (fail-closed)
    assert not string_match("done: score is 1", {"exact_match": "1 point"})


def test_string_match_judge_not_consulted_when_code_match_or_empty():
    j = _CountingJudge(False)   # would fail the episode if consulted
    assert string_match("done: the author is hlz0", {"exact_match": "hlz0"}, judge=j)
    assert j.calls == 0
    j = _CountingJudge(True)    # would fake-verify if consulted
    assert not string_match("", {"exact_match": "x"}, judge=j)
    assert not string_match("x", {"must_include": []}, judge=j)
    assert j.calls == 0


def test_url_match_normalizes():
    assert url_match("http://s/f/gaming/", "http://s/f/gaming")
    assert url_match("http://s/p?a=1&b=2", "http://s/p?b=2&a=1")
    assert not url_match("http://s/p", "http://s/q")


class _EvalBrowser:
    def __init__(self):
        self.gotos = []
        self.page_text = "comment 'great post' by alice"
    def act(self, action):
        self.gotos.append(action)
        return self.observation()
    def observation(self):
        return {"url": "http://s/post/1", "axtree": self.page_text}
    def eval_js(self, expr):
        return "great post" if "comment" in expr else ""


def test_program_html_last_page_and_goto_and_locator():
    b = _EvalBrowser()
    assert program_html(b, [{"url": "last", "locator": "",
                             "required_contents": {"must_include": ["great post"]}}])
    assert program_html(b, [{"url": "http://s/post/1",
                             "locator": "document.querySelector('.comment').outerText",
                             "required_contents": {"must_include": ["great post"]}}])
    assert b.gotos == ["goto('http://s/post/1')"]
    assert not program_html(b, [{"url": "last", "locator": "",
                                 "required_contents": {"must_include": ["missing"]}}])


def test_evaluate_combines_types():
    task = {"eval": {"eval_types": ["string_match", "url_match"],
                     "reference_answers": {"must_include": ["45"]},
                     "reference_url": "http://s/p"}}
    ok, details = evaluate(task, "it has 45", "http://s/p/", None)
    assert ok and details == {"string_match": True, "url_match": True}
    ok, details = evaluate(task, "wrong", "http://s/p/", None)
    assert not ok and details["string_match"] is False
    assert not evaluate({"eval": {"eval_types": []}}, "x", "u", None)[0]
