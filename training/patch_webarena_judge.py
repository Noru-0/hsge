#!/usr/bin/env python3
"""Make WebArena's LLM judge point at a model that still exists, on every box.

The judge (`llm_fuzzy_match`, `llm_ua_match` in
`evaluation_harness/helper_functions.py`) scores the 40 single-site tasks that
string-matching cannot: shopping 15, shopping_admin 20, gitlab 5, reddit 0.
Historically WebArena hardcoded `gpt-4-1106-preview` there; that preview model
has been retired, so on a current key every call returns `404 model_not_found`,
BrowserGym's `validate()` catches only AssertionError, and each of those tasks
is recorded as errored — a silent, guaranteed 0.

Two builds exist in the wild and this script handles both:

- **env-var build** (what a current install looks like): the module reads
  `WEBARENA_EVAL_MODEL`. Nothing needs patching — the fix is to export the
  variable, which this script verifies and tells you to do. Note its default
  (`gpt-4.1-mini`) is NOT the closest successor to the original judge, so
  leaving it unset still changes the measurement silently.
- **hardcoded build**: the retired model appears as a literal. Then the source
  is patched in place, keeping a `.orig` backup on the first run only, so a
  repeat run cannot overwrite the pristine copy with an already-patched one.

`gpt-4-turbo` is the default replacement because `gpt-4-1106-preview` *was* the
GPT-4 Turbo preview — it is the direct successor, not merely a current model.

**Either way this is a deviation from the published evaluator and must be
disclosed whenever these numbers are reported**; the original cannot be run at
all. The script writes `<pkg>/.hsge_judge_override` and prints the two variables
to export, so `eval_webarena.py` stamps the choice into every `summary.json` and
the provenance travels with the numbers instead of relying on memory.

Usage (in the EVAL venv on each box, before eval_webarena.py):
    python training/patch_webarena_judge.py                     # default gpt-4-turbo
    python training/patch_webarena_judge.py --model gpt-4.1     # or another
    python training/patch_webarena_judge.py --check             # report only
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path

OLD_MODEL = "gpt-4-1106-preview"
DEFAULT_NEW_MODEL = "gpt-4-turbo"
TARGET = "evaluation_harness/helper_functions.py"


def find_helper_functions() -> Path:
    """Locate WebArena's helper_functions.py inside the installed package."""
    spec = importlib.util.find_spec("webarena")
    roots: list[Path] = []
    if spec and spec.submodule_search_locations:
        roots += [Path(p) for p in spec.submodule_search_locations]
    # browsergym vendors webarena as a dependency; its evaluation harness may
    # live beside it rather than under a top-level `webarena` package.
    for mod in ("browsergym.webarena", "browsergym"):
        spec = importlib.util.find_spec(mod)
        if spec and spec.submodule_search_locations:
            roots += [Path(p) for p in spec.submodule_search_locations]
    seen: set[Path] = set()
    for root in roots:
        for base in (root, root.parent):
            if base in seen:
                continue
            seen.add(base)
            for cand in base.rglob(TARGET):
                return cand
    raise SystemExit(
        f"ERROR: could not find {TARGET} under any of: "
        f"{', '.join(str(r) for r in roots) or '(webarena not importable)'}\n"
        f"Run this inside the eval venv, e.g.\n"
        f"  /workspace/venvs/eval/bin/python training/patch_webarena_judge.py")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=DEFAULT_NEW_MODEL,
                    help=f"replacement judge model (default {DEFAULT_NEW_MODEL})")
    ap.add_argument("--check", action="store_true",
                    help="report what would change and exit non-zero if unpatched")
    args = ap.parse_args()

    path = find_helper_functions()
    text = path.read_text(encoding="utf-8")
    n_old = text.count(f'"{OLD_MODEL}"') + text.count(f"'{OLD_MODEL}'")
    env_var = re.search(r'environ(?:\.get)?[\[(]\s*["\'](WEBARENA_EVAL_MODEL)["\']', text)
    reads_env = bool(env_var)

    print(f"file            : {path}")
    print(f"build           : {'env-var (WEBARENA_EVAL_MODEL)' if reads_env else 'hardcoded'}")
    print(f"occurrences of  : {OLD_MODEL!r} -> {n_old}")

    if args.check:
        problems = []
        if n_old:
            problems.append(f"{n_old} occurrence(s) of the retired {OLD_MODEL}")
        if reads_env and os.environ.get("WEBARENA_EVAL_MODEL") != args.model:
            problems.append(f"WEBARENA_EVAL_MODEL is "
                            f"{os.environ.get('WEBARENA_EVAL_MODEL') or '(unset)'}, "
                            f"expected {args.model}")
        if problems:
            raise SystemExit("NOT READY: " + "; ".join(problems))
        print("OK: judge is configured")
        return

    if reads_env:
        print("no source change needed: this build reads WEBARENA_EVAL_MODEL")
    elif n_old:
        orig = path.with_suffix(path.suffix + ".orig")
        if not orig.exists():          # never overwrite a pristine backup
            orig.write_text(text, encoding="utf-8")
            print(f"backup written  : {orig}")
        patched = text.replace(f'"{OLD_MODEL}"', f'"{args.model}"') \
                      .replace(f"'{OLD_MODEL}'", f"'{args.model}'")
        path.write_text(patched, encoding="utf-8")
        print(f"patched         : {n_old} occurrence(s) -> {args.model!r}")
    else:
        print("nothing to do: neither the retired literal nor the env hook is "
              "present -- inspect this build by hand before trusting its scores")

    marker = path.parent.parent / ".hsge_judge_override"
    marker.write_text(f"{args.model}\n", encoding="utf-8")
    print(f"marker          : {marker}")
    print()
    print("Export BOTH before running eval_webarena.py:")
    if reads_env:
        print(f"    export WEBARENA_EVAL_MODEL={args.model}      # what the judge uses")
    print(f"    export WA_JUDGE_MODEL_OVERRIDE={args.model}   # recorded in summary.json")
    print()
    print(f"DISCLOSE THIS when reporting scores: the published evaluator's judge "
          f"({OLD_MODEL}) is retired and cannot be called; {args.model!r} was "
          f"substituted. Note also that validate() runs on EVERY step, so a judged "
          f"task costs one judge call per step, not one per episode.")


if __name__ == "__main__":
    sys.exit(main())
