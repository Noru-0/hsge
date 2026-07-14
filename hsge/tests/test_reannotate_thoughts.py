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
