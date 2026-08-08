"""training/eval_webarena.py: the site-generalization contract.

`site_task_ids` picks only the tasks whose *sole* site is the one under test,
and `set_wa_env` points that site's WA_* var at the live URL while every other
site keeps an unreachable dummy (WebArenaInstance demands all seven vars).

Run:  python -m pytest hsge/tests/test_eval_site_selection.py -q
 (or) PYTHONPATH=. python hsge/tests/test_eval_site_selection.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "training"))

from eval_webarena import DUMMY_SITES, set_wa_env, site_task_ids  # noqa: E402

CONFIGS = [
    {"task_id": 1, "sites": ["gitlab"]},
    {"task_id": 2, "sites": ["reddit"]},
    {"task_id": 3, "sites": ["shopping"]},
    {"task_id": 4, "sites": ["gitlab", "reddit"]},   # multi-site: never selected
    {"task_id": 5, "sites": ["reddit"]},
]


def _cache():
    path = Path(tempfile.mkdtemp()) / "test.raw.json"
    path.write_text(json.dumps(CONFIGS))
    return path


def test_site_task_ids_selects_single_site_tasks_only():
    cache = _cache()
    assert site_task_ids("reddit", cache) == [2, 5]
    assert site_task_ids("shopping", cache) == [3]
    # the gitlab+reddit task belongs to neither single-site subset
    assert site_task_ids("gitlab", cache) == [1]


def test_set_wa_env_points_only_the_site_under_test_at_the_live_url():
    for key in list(DUMMY_SITES) + ["WA_FULL_RESET"]:
        os.environ.pop(key, None)

    set_wa_env("reddit", "https://tunnel.example.com/")

    assert os.environ["WA_REDDIT"] == "https://tunnel.example.com"  # trailing / stripped
    assert os.environ["WA_GITLAB"] == DUMMY_SITES["WA_GITLAB"]
    assert os.environ["WA_SHOPPING"] == DUMMY_SITES["WA_SHOPPING"]
    # every var WebArenaInstance requires is present
    assert set(DUMMY_SITES).issubset(os.environ)


def test_set_wa_env_does_not_clobber_a_preset_dummy_override():
    for key in list(DUMMY_SITES):
        os.environ.pop(key, None)
    os.environ["WA_HOMEPAGE"] = "http://real-homepage:4399"

    set_wa_env("shopping", "http://shop:7770")

    assert os.environ["WA_SHOPPING"] == "http://shop:7770"
    assert os.environ["WA_HOMEPAGE"] == "http://real-homepage:4399"


if __name__ == "__main__":
    test_site_task_ids_selects_single_site_tasks_only()
    test_set_wa_env_points_only_the_site_under_test_at_the_live_url()
    test_set_wa_env_does_not_clobber_a_preset_dummy_override()
    print("ok")
