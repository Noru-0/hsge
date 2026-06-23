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


def test_episode_to_examples_exports_webarena_id_click_and_stop(tmp_path):
    ep = tmp_path / "ep_0004"
    state = ep / "page_state"
    state.mkdir(parents=True)
    (state / "step_000_axtree.txt").write_text(
        "[101] button 'Add to Cart'\n",
        encoding="utf-8",
    )
    (state / "step_001_axtree.txt").write_text(
        "[101] button 'Add to Cart'\n[201] StaticText 'Done'\n",
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
                "thought": "The task is complete.",
                "action": "send_msg_to_user('Done')",
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
        action_format="webarena_id",
        report=report,
    )

    assert len(examples) == 2
    assert examples[0]["action_format"] == "webarena_id"
    assert "```click [101]```" in examples[0]["messages"][2]["content"]
    assert "```stop [Done]```" in examples[1]["messages"][2]["content"]
    assert not examples[0]["messages"][2]["content"].lstrip().startswith("{")


def test_episode_to_examples_exports_webarena_id_fill_as_type_no_enter(tmp_path):
    ep = tmp_path / "ep_0005"
    state = ep / "page_state"
    state.mkdir(parents=True)
    (state / "step_000_axtree.txt").write_text(
        "[102] textbox 'Search'\n",
        encoding="utf-8",
    )
    steps = [
        {
            "action": json.dumps({
                "thought": "I should enter the search term.",
                "action": "fill('102','wireless mouse')",
            }),
            "observation": {"axtree_txt": {"path": "page_state/step_000_axtree.txt"}},
        },
    ]
    report = _new_report()
    examples = episode_to_examples(
        "Search for wireless mouse",
        steps,
        str(ep),
        difficulty=1,
        action_format="webarena_id",
        report=report,
    )

    assert len(examples) == 1
    assert "```type [102] [wireless mouse] [0]```" in examples[0]["messages"][2]["content"]


def test_episode_to_examples_drops_webarena_id_unsafe_bracket_text(tmp_path):
    ep = tmp_path / "ep_0006"
    state = ep / "page_state"
    state.mkdir(parents=True)
    (state / "step_000_axtree.txt").write_text(
        "[102] textbox 'Search'\n",
        encoding="utf-8",
    )
    steps = [
        {
            "action": json.dumps({
                "thought": "I should enter the search term.",
                "action": "fill('102','bad ] text')",
            }),
            "observation": {"axtree_txt": {"path": "page_state/step_000_axtree.txt"}},
        },
    ]
    report = _new_report()
    examples = episode_to_examples(
        "Search for bad text",
        steps,
        str(ep),
        difficulty=1,
        action_format="webarena_id",
        report=report,
    )

    assert examples == []
    assert report["steps_dropped"] == 1
    assert report["drop_reasons"]["webarena_unsafe_bracket_text"] == 1
