from pathlib import Path
import sys
from types import ModuleType

import pytest

from run_webarena import CONFIG_FIELDS, _build_parser, _load_yaml_defaults, _validate_args
from hsge.backends import OpenAILLM


def test_repository_config_covers_every_documented_destination():
    root = Path(__file__).resolve().parents[2]
    defaults = _load_yaml_defaults(str(root / "config.yaml"), required=True)
    expected = {dest for fields in CONFIG_FIELDS.values() for dest in fields.values()}

    assert set(defaults) == expected


def test_cli_explicit_value_overrides_yaml_default(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "exploration:\n  max_nodes: 7\nrun:\n  dry_run: true\n",
        encoding="utf-8",
    )
    defaults = _load_yaml_defaults(str(config), required=True)
    parser = _build_parser(defaults)
    args = parser.parse_args(["--max-nodes", "11", "--no-dry-run"])
    _validate_args(parser, args)

    assert args.max_nodes == 11
    assert args.dry_run is False


def test_unknown_yaml_key_is_rejected(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("skills:\n  mystery_knob: 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="mystery_knob"):
        _load_yaml_defaults(str(config), required=True)


def test_yaml_lists_are_preserved_for_denylist(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "browser:\n  denylist:\n    - /logout\n    - /danger\n",
        encoding="utf-8",
    )

    defaults = _load_yaml_defaults(str(config), required=True)
    args = _build_parser(defaults).parse_args([])

    assert args.denylist == ["/logout", "/danger"]


def test_openai_backend_applies_request_timeout_and_retry_limit(monkeypatch):
    captured = {}
    fake_openai = ModuleType("openai")

    def make_client(**kwargs):
        captured.update(kwargs)
        return object()

    fake_openai.OpenAI = make_client
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    OpenAILLM(
        model="test-model", api_key="test-key",
        timeout_seconds=17.5, max_retries=1,
    )

    assert captured["timeout"] == 17.5
    assert captured["max_retries"] == 1
