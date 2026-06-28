from pathlib import Path

import pytest

from run_webarena import CONFIG_FIELDS, _build_parser, _load_yaml_defaults, _validate_args


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
