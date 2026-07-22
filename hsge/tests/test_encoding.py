"""Episode/artifact files must be written and read as UTF-8 explicitly.

On Windows, a text-mode open() without encoding= defaults to the locale codec
(cp1252), which cannot encode characters common in an accessibility tree (e.g.
'↓', a down arrow) -- a real run on Windows crashed in _record with
UnicodeEncodeError. macOS/Linux default to UTF-8 so the bug is invisible there;
these tests simulate the Windows default so they fail cross-platform without the
explicit encoding.

Run:  python -m pytest hsge/tests/test_encoding.py -q
 (or) PYTHONPATH=. python hsge/tests/test_encoding.py
"""
import builtins
import os
import tempfile
from unittest import mock

from hsge.llm import HashingEmbedder, MockLLM
from hsge.schema import Step
from hsge.webarena.runtime import WebArenaExplorer

_real_open = builtins.open


def _cp1252_open(*args, **kwargs):
    """Stand in for the Windows default: any text-mode open() that does not name
    an encoding uses cp1252 (which can't encode '↓')."""
    mode = kwargs.get("mode", args[1] if len(args) > 1 else "r")
    if "b" not in mode and "encoding" not in kwargs:
        kwargs["encoding"] = "cp1252"
    return _real_open(*args, **kwargs)


def _explorer(out_dir):
    return WebArenaExplorer(
        browser_factory=lambda url: None, llm=MockLLM(),
        embedder=HashingEmbedder(), out_dir=out_dir,
        allow_pattern=".*", terminal_goal=None)


def test_record_writes_axtree_with_non_cp1252_chars():
    out = tempfile.mkdtemp()
    ex = _explorer(out)
    axtree = "[1] link 'next'\ncollapse ↓ expand ↑ bullet •"
    steps = [Step(action="click('1')", url="http://x/", axtree=axtree)]

    with mock.patch("builtins.open", _cp1252_open):
        ex._record("goal ↓", steps, [axtree], [None], success=True,
                   difficulty=1, tag="LOCAL")

    # the axtree file round-trips as UTF-8
    ax = os.path.join(out, "episodes", "ep_0000", "page_state", "step_000_axtree.txt")
    with _real_open(ax, encoding="utf-8") as f:
        assert "↓" in f.read()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
