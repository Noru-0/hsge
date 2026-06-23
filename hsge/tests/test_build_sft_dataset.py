import json

from build_sft_dataset import _new_report, episode_to_examples


def test_episode_to_examples_filters_invalid_and_repairs_thoughts(tmp_path):
    ep = tmp_path / "ep_0001"
    state = ep / "page_state"
    state.mkdir(parents=True)
    (state / "step_000_axtree.txt").write_text(
        "[101] button 'Add to Cart'\n[102] textbox 'Search'\n",
        encoding="utf-8",
    )
    (state / "step_001_axtree.txt").write_text(
        "[101] button 'Add to Cart'\n[102] textbox 'Search'\n",
        encoding="utf-8",
    )
    steps = [
        {
            "action": json.dumps({
                "thought": "I need to add the item.",
                "action": "click('101')",
            }),
            "observation": {"axtree_txt": {"path": "page_state/step_000_axtree.txt"}},
        },
        {
            "action": json.dumps({
                "thought": "Bad target.",
                "action": "click('Blue')",
            }),
            "observation": {"axtree_txt": {"path": "page_state/step_001_axtree.txt"}},
        },
    ]
    report = _new_report()
    examples = episode_to_examples(
        "Add the product to the cart",
        steps,
        str(ep),
        difficulty=1,
        repair=True,
        report=report,
    )
    assert len(examples) == 1
    target = json.loads(examples[0]["messages"][2]["content"])
    assert target["action"] == "click('101')"
    assert "click" in target["thought"].lower()
    assert report["steps_kept"] == 1
    assert report["steps_dropped"] == 1
    assert report["thoughts_repaired"] == 1


def test_episode_to_examples_drops_goto_by_default(tmp_path):
    ep = tmp_path / "ep_0002"
    state = ep / "page_state"
    state.mkdir(parents=True)
    (state / "step_000_axtree.txt").write_text("[101] link 'Next'\n", encoding="utf-8")
    steps = [
        {
            "action": json.dumps({
                "thought": "I should navigate directly.",
                "action": "goto('http://example.com/search?q=x')",
            }),
            "observation": {"axtree_txt": {"path": "page_state/step_000_axtree.txt"}},
        }
    ]
    report = _new_report()
    examples = episode_to_examples(
        "Search for x",
        steps,
        str(ep),
        difficulty=1,
        report=report,
    )
    assert examples == []
    assert report["steps_dropped"] == 1


def test_episode_to_examples_drops_disabled_targets(tmp_path):
    ep = tmp_path / "ep_0003"
    state = ep / "page_state"
    state.mkdir(parents=True)
    (state / "step_000_axtree.txt").write_text(
        "[101] button 'Submit', disabled=True\n",
        encoding="utf-8",
    )
    steps = [
        {
            "action": json.dumps({
                "thought": "I need to click the submit button.",
                "action": "click('101')",
            }),
            "observation": {"axtree_txt": {"path": "page_state/step_000_axtree.txt"}},
        }
    ]
    report = _new_report()
    examples = episode_to_examples(
        "Submit the visible form",
        steps,
        str(ep),
        difficulty=1,
        report=report,
    )
    assert examples == []
    assert report["steps_dropped"] == 1
    assert report["drop_reasons"]["click target [101] is disabled"] == 1
