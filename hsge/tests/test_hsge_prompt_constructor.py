import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "webarena-main-lora"
sys.path.insert(0, str(WEB))
for name in ("REDDIT", "SHOPPING", "SHOPPING_ADMIN", "GITLAB", "WIKIPEDIA", "MAP", "HOMEPAGE"):
    os.environ.setdefault(name, f"http://{name.lower()}.test")

from agent.prompts.prompt_constructor import HSGEPromptConstructor  # noqa: E402
from browser_env import ActionParsingError  # noqa: E402


def test_hsge_to_webarena_handles_quoted_answer():
    action = HSGEPromptConstructor._hsge_to_webarena(
        "send_msg_to_user('No products found for \"switch accessories\"')"
    )
    assert action == 'stop [No products found for "switch accessories"]'


def test_hsge_to_webarena_rejects_legacy_select_option():
    try:
        HSGEPromptConstructor._hsge_to_webarena("select_option('101','Blue')")
    except ActionParsingError:
        pass
    else:
        raise AssertionError("select_option should not be accepted")
