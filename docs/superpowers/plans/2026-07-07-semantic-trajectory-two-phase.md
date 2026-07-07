# Semantic Trajectories (Two-Phase Explore → Compose) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSGE produce long, verified, WebArena-style trajectories for SLM training, per the approved spec `docs/superpowers/specs/2026-07-07-semantic-trajectory-two-phase-design.md`.

**Architecture:** Phase 1 (existing frontier loop) gains a per-node NodeDigester that distills each page into a grounded SiteKB. Phase 2 (new) has a TaskComposer that generates multi-hop tasks with WebArena-style eval specs from the SiteKB, a Solver-driven collection loop, and an Evaluator that gates which episodes are `verified` for SFT.

**Tech Stack:** Python 3, existing `hsge` package (no new dependencies; numpy already required, browsergym/openai only for real runs), pytest for tests.

## Global Constraints

- Run everything from the repo root; activate `conda activate go-browse` before running anything.
- All code/comments/docs/commit messages in English (`.claude/rules/conventions.md`).
- Precedence everywhere: CLI flag > `config.yaml` > built-in default.
- Secrets stay in `.env`; nothing secret in `config.yaml` or code.
- The deterministic mock pipeline (`hsge/tests/test_clustering.py`, demos) must keep passing untouched — all changes live in `hsge/webarena/`, top-level scripts, and new tests.
- `run_webarena.py --phase` defaults to `explore`: existing behavior/scripts unchanged.
- Commit after each task (local only, never push).
- Full test suite command: `python -m pytest hsge/tests/ -q` — run it before every commit; expected: all pass.

## File Structure

- Create: `hsge/webarena/recording.py` — episode persistence (extracted from runtime, gains `extra_meta`).
- Create: `hsge/webarena/digest.py` — `NodeDigester`, `SiteKB`, evidence grounding, `extract_msg`.
- Create: `hsge/webarena/evaluator.py` — `string_match`/`url_match`/`program_html`, `evaluate`, `extract_answer`.
- Create: `hsge/webarena/composer.py` — `TaskComposer`, `validate_task`, `sample_bundles`, MOD denylist.
- Create: `hsge/webarena/collect.py` — `GenerationRunner` (phase-2 loop), `top_k_skill_hints`.
- Modify: `hsge/webarena/runtime.py` — delegate recording; wire digester + sitekb dump + node axtree persistence.
- Modify: `hsge/webarena/agents.py` — `Solver.solve(..., hints=None)`.
- Modify: `hsge/webarena/browser.py` — add `eval_js`.
- Modify: `run_webarena.py` — `--phase`, `gen:` config block, new LLM roles, dry-run scripting for both phases.
- Modify: `build_sft_dataset.py` — verified-GEN gating, `--include-local`, argparse.
- Modify: `config.yaml`, `.claude/rules/architecture.md`, `.claude/rules/commands.md` — config + docs.
- Tests: `hsge/tests/test_recording.py`, `test_digest.py`, `test_sitekb_runtime.py`, `test_evaluator.py`, `test_composer.py`, `test_collect.py`, `test_build_sft.py`.

---

### Task 1: Extract episode recording into `recording.py` with `extra_meta`

Both the existing explorer and the new phase-2 runner must write the same episode layout; phase 2 additionally needs `verified`/`task_id`/eval metadata in `episode_meta.json`.

**Files:**
- Create: `hsge/webarena/recording.py`
- Modify: `hsge/webarena/runtime.py` (replace `_record` body, lines ~112-134)
- Test: `hsge/tests/test_recording.py`

**Interfaces:**
- Consumes: `hsge.schema.Step` (fields `action`, `url`, `obs_summary`, `axtree`).
- Produces: `record_episode(out_dir: str, episode_index: int, goal: str, steps: list[Step], obs_texts: list[str], obs_screenshots: list[str | None], success: bool, difficulty: int, tag: str, extra_meta: dict | None = None) -> str` returning the episode id (`"ep_0007"`). Writes `episodes/ep_XXXX/{episode_meta.json,episode.jsonl,page_state/*}` exactly as today; `extra_meta` keys are merged into the top level of `episode_meta.json`.

- [ ] **Step 1: Write the failing test**

```python
# hsge/tests/test_recording.py
"""record_episode writes the run-dir episode layout build_sft_dataset.py reads,
and merges extra_meta (verified/task_id/eval) into episode_meta.json."""
import json

from hsge.schema import Step
from hsge.webarena.recording import record_episode


def test_record_episode_writes_meta_steps_and_extra_meta(tmp_path):
    steps = [Step(action="click('1')", url="http://s/a", obs_summary="go", axtree="ax1"),
             Step(action="send_msg_to_user('done: 45')", url="http://s/b",
                  obs_summary="answer", axtree="ax2")]
    ep_id = record_episode(str(tmp_path), 7, "find the count", steps,
                           ["ax1", "ax2"], [None, None], True, 3, "GEN",
                           extra_meta={"task_id": "gen_0001", "verified": True,
                                       "answer": "45"})
    assert ep_id == "ep_0007"
    ep = tmp_path / "episodes" / ep_id
    meta = json.load(open(ep / "episode_meta.json"))
    assert meta["goal"] == "find the count"
    assert meta["outcome"]["success"] is True
    assert meta["metadata"] == {"difficulty": 3, "tags": ["GEN"]}
    assert meta["task_id"] == "gen_0001" and meta["verified"] is True
    assert meta["answer"] == "45"
    lines = [json.loads(l) for l in open(ep / "episode.jsonl")]
    assert [l["parsed_action"] for l in lines] == ["click('1')", "send_msg_to_user('done: 45')"]
    assert (ep / "page_state" / "step_000_axtree.txt").read_text() == "ax1"


def test_record_episode_no_extra_meta_matches_legacy_shape(tmp_path):
    ep_id = record_episode(str(tmp_path), 0, "g", [Step(action="a", url="u", axtree="x")],
                           ["x"], [None], False, 1, "LOCAL")
    meta = json.load(open(tmp_path / "episodes" / ep_id / "episode_meta.json"))
    assert set(meta) == {"kind", "goal", "outcome", "metadata", "step_count"}
    assert meta["outcome"]["reward"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest hsge/tests/test_recording.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hsge.webarena.recording'`

- [ ] **Step 3: Create `hsge/webarena/recording.py`** (body moved verbatim from `WebArenaExplorer._record`, plus `episode_index`, `extra_meta`, and the return value)

```python
"""Episode persistence in the run-dir layout build_sft_dataset.py reads.

Shared by the phase-1 explorer (runtime.py) and the phase-2 collection loop
(collect.py). extra_meta lets phase 2 attach verification metadata
(task_id/verified/eval/answer) to episode_meta.json.
"""
from __future__ import annotations

import base64
import json
import os


def record_episode(out_dir: str, episode_index: int, goal: str, steps, obs_texts,
                   obs_screenshots, success: bool, difficulty: int, tag: str,
                   extra_meta: dict | None = None) -> str:
    ep_id = f"ep_{episode_index:04d}"
    ep = os.path.join(out_dir, "episodes", ep_id)
    os.makedirs(os.path.join(ep, "page_state"), exist_ok=True)
    meta = {"kind": "low_level_trajectory", "goal": goal,
            "outcome": {"success": bool(success), "reward": 1.0 if success else 0.0, "response": ""},
            "metadata": {"difficulty": difficulty, "tags": [tag]}, "step_count": len(steps)}
    if extra_meta:
        meta.update(extra_meta)
    json.dump(meta, open(os.path.join(ep, "episode_meta.json"), "w"), indent=2)
    with open(os.path.join(ep, "episode.jsonl"), "w") as f:
        for k, st in enumerate(steps):
            axp = f"page_state/step_{k:03d}_axtree.txt"
            open(os.path.join(ep, axp), "w").write(obs_texts[k] if k < len(obs_texts) else "")
            observation = {"axtree_txt": {"path": axp}}
            shot = obs_screenshots[k] if k < len(obs_screenshots) else None
            if shot:
                shotp = f"page_state/step_{k:03d}_screenshot.jpg"
                open(os.path.join(ep, shotp), "wb").write(base64.b64decode(shot))
                observation["screenshot"] = {"path": shotp}
            rec = {"record_type": "step", "index": k,
                   "action": json.dumps({"thought": st.obs_summary, "action": st.action}),
                   "parsed_action": st.action, "thought": st.obs_summary,
                   "observation": observation}
            f.write(json.dumps(rec) + "\n")
    return ep_id
```

- [ ] **Step 4: Delegate in `runtime.py`.** Add `from .recording import record_episode` to the imports, then replace the whole `_record` method body (keep the method so call sites don't change):

```python
    # ---- persistence in a build_sft_dataset-compatible run-dir layout --------
    def _record(self, goal, steps, obs_texts, obs_screenshots, success, difficulty, tag):
        record_episode(self.out_dir, self.episode, goal, steps, obs_texts,
                       obs_screenshots, success, difficulty, tag)
        self.episode += 1
```

Remove the now-unused `import base64` from `runtime.py` **only if** nothing else uses it (the node-screenshot code at line ~407 still does — so keep it).

- [ ] **Step 5: Run tests to verify pass (including the existing suite)**

Run: `python -m pytest hsge/tests/ -q`
Expected: all PASS (new recording tests + existing suite unaffected)

- [ ] **Step 6: Commit**

```bash
git add hsge/webarena/recording.py hsge/webarena/runtime.py hsge/tests/test_recording.py
git commit -m "Extract episode recording into recording.py with extra_meta support"
```

---

### Task 2: `digest.py` — evidence grounding, NodeDigester, SiteKB

**Files:**
- Create: `hsge/webarena/digest.py`
- Test: `hsge/tests/test_digest.py`

**Interfaces:**
- Consumes: any `LLM` with `complete_json(system, prompt, image_b64=None, image_detail="low") -> dict`.
- Produces (used by Tasks 3, 5, 6, 7):
  - `normalize_ws(text: str) -> str`
  - `evidence_grounded(evidence: str, axtree: str) -> bool`
  - `extract_msg(action: str) -> str` — text inside `send_msg_to_user('...')`, `""` if none.
  - `NodeDigester(llm, max_entities=20, max_facts=10)` with `digest(obs: dict, solved: list[dict]) -> dict`; `obs` is `{"url", "axtree", ...}`; each `solved` item is `{"task": str, "success": bool, "answer": str, "final_axtree": str}`. Returns `{"url", "page_type", "title", "entities": [...], "facts": [...]}` where every entity/fact carries `evidence` and a code-computed `grounded: bool`.
  - `SiteKB(site="")` with `.site`, `.nodes: list[dict]`, `.skills: list[dict]`, `add_node(node)`, `node_by_index(i)`, `resolve_ref(ref) -> tuple[str, bool] | None` (value, grounded), `known_urls() -> set[str]`, `dump(path)`, `SiteKB.load(path)`. Ref grammar: `n<node_index>.f<fact_idx>` | `n<node_index>.e<entity_idx>` | `n<node_index>.e<entity_idx>.attrs.<key>`.

- [ ] **Step 1: Write the failing tests**

```python
# hsge/tests/test_digest.py
"""SiteKB + NodeDigester: the grounding gate is code (evidence must be a literal
substring of the axtree), not LLM self-report; refs resolve to (value, grounded)."""
import json

from hsge.webarena.digest import (NodeDigester, SiteKB, evidence_grounded,
                                  extract_msg, normalize_ws)


def test_evidence_grounded_is_whitespace_insensitive_substring():
    ax = "[1] link 'Best budget GPU'\n\ttext '183 upvotes'"
    assert evidence_grounded("link 'Best budget GPU'", ax)
    assert evidence_grounded("text  '183   upvotes'", ax)   # ws-normalized
    assert not evidence_grounded("text '999 upvotes'", ax)  # not on the page
    assert not evidence_grounded("", ax)                    # empty evidence


def test_extract_msg():
    assert extract_msg("send_msg_to_user('done: the author is hlz0')") == "done: the author is hlz0"
    assert extract_msg('send_msg_to_user("45")') == "45"
    assert extract_msg("click('1')") == ""


class _DigestLLM:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        assert system.startswith("DIGEST")
        return {"page_type": "forum_listing", "title": "gaming",
                "entities": [
                    {"type": "post", "name": "Best budget GPU",
                     "attrs": {"upvotes": "183"}, "evidence": "link 'Best budget GPU'"},
                    {"type": "post", "name": "Fake post", "attrs": {},
                     "evidence": "link 'not on page'"}],
                "facts": [
                    {"q": "upvotes of Best budget GPU?", "a": "183",
                     "evidence": "text '183 upvotes'"},
                    {"q": "hallucinated?", "a": "yes", "evidence": "nope"}]}


def test_digester_grounds_entities_and_facts_by_code():
    obs = {"url": "http://s/f/gaming",
           "axtree": "[1] link 'Best budget GPU'\n\ttext '183 upvotes'"}
    solved = [{"task": "[INFO] Find the upvote count", "success": True,
               "answer": "183", "final_axtree": "text '183 upvotes'"},
              {"task": "[INFO] Find the moderator", "success": True,
               "answer": "bob", "final_axtree": "text 'nothing here'"}]
    d = NodeDigester(_DigestLLM()).digest(obs, solved)
    assert d["page_type"] == "forum_listing"
    assert [e["grounded"] for e in d["entities"]] == [True, False]
    ax_facts = [f for f in d["facts"] if f["source"] == "axtree"]
    assert [f["grounded"] for f in ax_facts] == [True, False]
    # episode-sourced facts are grounded iff the answer appears in the episode's
    # final axtree
    ep_facts = [f for f in d["facts"] if f["source"] == "episode"]
    assert [(f["a"], f["grounded"]) for f in ep_facts] == [("183", True), ("bob", False)]


def test_sitekb_resolve_ref_and_known_urls(tmp_path):
    kb = SiteKB(site="http://s")
    kb.add_node({"node_index": 3, "url": "http://s/f/gaming", "outlinks": ["http://s/f/gaming/1"],
                 "entities": [{"type": "post", "name": "Best budget GPU",
                               "attrs": {"author": "hlz0"}, "grounded": True}],
                 "facts": [{"q": "q", "a": "183", "grounded": False}]})
    assert kb.resolve_ref("n3.e0") == ("Best budget GPU", True)
    assert kb.resolve_ref("n3.e0.attrs.author") == ("hlz0", True)
    assert kb.resolve_ref("n3.f0") == ("183", False)
    assert kb.resolve_ref("n3.f9") is None and kb.resolve_ref("bogus") is None
    assert kb.known_urls() == {"http://s/f/gaming", "http://s/f/gaming/1"}
    kb.dump(tmp_path / "kb.json")
    kb2 = SiteKB.load(tmp_path / "kb.json")
    assert kb2.site == "http://s" and kb2.resolve_ref("n3.f0") == ("183", False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_digest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hsge.webarena.digest'`

- [ ] **Step 3: Create `hsge/webarena/digest.py`**

```python
"""Node digests and the Site Knowledge Base (SiteKB).

Phase 1 distills every visited node into a digest (page_type, entities, facts,
outlinks). The load-bearing anti-hallucination layer is CODE, not the LLM:
every entity/fact must quote `evidence`, and evidence_grounded() checks it is a
literal (whitespace-normalized) substring of the page's axtree. Only
`grounded: true` items may back a generated task's reference answer
(see composer.validate_task). Spec:
docs/superpowers/specs/2026-07-07-semantic-trajectory-two-phase-design.md
"""
from __future__ import annotations

import json
import re

_WS_RE = re.compile(r"\s+")
_MSG_RE = re.compile(r"send_msg_to_user\(\s*['\"](.*?)['\"]\s*\)", re.S)
_REF_RE = re.compile(r"^n(\d+)\.(?:f(\d+)|e(\d+)(?:\.attrs\.([\w-]+))?)$")

DIGEST_SYS = (
    "DIGEST this web page into structured site knowledge. Return JSON "
    '{"page_type": str, "title": str, '
    '"entities": [{"type": str, "name": str, "attrs": {str: str}, "evidence": str}], '
    '"facts": [{"q": str, "a": str, "evidence": str}]}.\n'
    "Rules:\n"
    "- page_type and entity type are short snake_case labels you choose "
    "(e.g. forum_listing, post, user, product).\n"
    "- evidence is REQUIRED for every entity and fact: quote the exact axtree text "
    "(a contiguous snippet) that supports it. Items whose evidence is not literally "
    "on the page get discarded, so never paraphrase.\n"
    "- facts are question/answer pairs a user could ask about THIS page; the answer "
    "must be visible on the page and must appear inside the evidence.\n"
    "- The solved-task results below are hints only; repeat one as a fact only if "
    "its answer is visible in the axtree.")


def normalize_ws(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def evidence_grounded(evidence: str, axtree: str) -> bool:
    ev = normalize_ws(evidence)
    return bool(ev) and ev in normalize_ws(axtree)


def extract_msg(action: str) -> str:
    m = _MSG_RE.search(action or "")
    return m.group(1) if m else ""


class SiteKB:
    def __init__(self, site: str = ""):
        self.site = site
        self.nodes: list[dict] = []
        self.skills: list[dict] = []

    def add_node(self, node: dict):
        self.nodes.append(node)

    def node_by_index(self, idx: int) -> dict | None:
        return next((n for n in self.nodes if n.get("node_index") == idx), None)

    def resolve_ref(self, ref: str) -> tuple[str, bool] | None:
        """(value, grounded) for a ref like n12.f3 / n13.e1 / n13.e1.attrs.author."""
        m = _REF_RE.match(ref or "")
        if not m:
            return None
        node = self.node_by_index(int(m.group(1)))
        if node is None:
            return None
        if m.group(2) is not None:
            facts = node.get("facts") or []
            i = int(m.group(2))
            if i >= len(facts):
                return None
            return str(facts[i].get("a", "")), bool(facts[i].get("grounded"))
        ents = node.get("entities") or []
        i = int(m.group(3))
        if i >= len(ents):
            return None
        ent = ents[i]
        if m.group(4):
            val = (ent.get("attrs") or {}).get(m.group(4))
            if val is None:
                return None
            return str(val), bool(ent.get("grounded"))
        return str(ent.get("name", "")), bool(ent.get("grounded"))

    def known_urls(self) -> set[str]:
        urls: set[str] = set()
        for n in self.nodes:
            urls.add(n.get("url") or "")
            urls.update(n.get("outlinks") or [])
        urls.discard("")
        return urls

    def to_dict(self) -> dict:
        return {"site": self.site, "nodes": self.nodes, "skills": self.skills}

    def dump(self, path):
        json.dump(self.to_dict(), open(path, "w"), indent=2)

    @classmethod
    def load(cls, path) -> "SiteKB":
        d = json.load(open(path))
        kb = cls(d.get("site", ""))
        kb.nodes = d.get("nodes") or []
        kb.skills = d.get("skills") or []
        return kb


class NodeDigester:
    def __init__(self, llm, max_entities: int = 20, max_facts: int = 10):
        self.llm = llm
        self.max_entities = max_entities
        self.max_facts = max_facts

    def digest(self, obs: dict, solved: list[dict]) -> dict:
        """One LLM call -> digest with code-checked `grounded` flags.

        solved items ({"task","success","answer","final_axtree"}) become
        episode-sourced facts; those are grounded iff the answer text appears
        in that episode's FINAL axtree (the page the answer was read from),
        never on the LLM's say-so.
        """
        solved_txt = "\n".join(
            f"- task: {s['task']!r} success={s['success']} answer={s['answer']!r}"
            for s in solved) or "(none)"
        prompt = (f"URL: {obs['url']}\n\nSOLVED TASKS ON THIS PAGE:\n{solved_txt}"
                  f"\n\nPAGE (accessibility tree):\n{obs['axtree'][:8000]}")
        out = self.llm.complete_json(DIGEST_SYS, prompt) or {}
        axtree = obs.get("axtree", "")
        entities = []
        for e in (out.get("entities") or [])[: self.max_entities]:
            if not isinstance(e, dict) or not e.get("name"):
                continue
            ev = str(e.get("evidence") or "")
            entities.append({
                "type": str(e.get("type") or "unknown"), "name": str(e["name"]),
                "attrs": {str(k): str(v) for k, v in (e.get("attrs") or {}).items()},
                "evidence": ev, "grounded": evidence_grounded(ev, axtree)})
        facts = []
        for f in (out.get("facts") or [])[: self.max_facts]:
            if not isinstance(f, dict) or not f.get("q"):
                continue
            ev = str(f.get("evidence") or "")
            facts.append({"q": str(f["q"]), "a": str(f.get("a", "")), "source": "axtree",
                          "evidence": ev, "grounded": evidence_grounded(ev, axtree)})
        for s in solved:
            if s.get("success") and s.get("answer"):
                facts.append({"q": s["task"], "a": s["answer"], "source": "episode",
                              "evidence": s["answer"],
                              "grounded": evidence_grounded(s["answer"],
                                                            s.get("final_axtree", ""))})
        return {"url": obs.get("url", ""), "page_type": str(out.get("page_type") or "unknown"),
                "title": str(out.get("title") or ""), "entities": entities, "facts": facts}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest hsge/tests/test_digest.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/digest.py hsge/tests/test_digest.py
git commit -m "Add digest.py: NodeDigester + SiteKB with code-side evidence grounding"
```

---

### Task 3: Wire digest into the phase-1 loop (runtime + roles)

**Files:**
- Modify: `hsge/webarena/runtime.py` (imports; `__init__`; the node loop in `run()`)
- Modify: `run_webarena.py` (`AGENT_ROLES` only — the rest of the CLI comes in Task 7)
- Test: `hsge/tests/test_sitekb_runtime.py`

**Interfaces:**
- Consumes: `NodeDigester`, `SiteKB`, `extract_msg` from Task 2.
- Produces: after every node, `out_dir/sitekb.json` exists (SiteKB with that node's digest, `node_index`, `url_template`, `outlinks`, `axtree_path`, plus current `skills`), and `out_dir/node_state/node_XXXX_axtree.txt` holds the node's initial axtree. New LLM roles `node_digester`, `task_composer`, `judge` resolve like every other role.

- [ ] **Step 1: Write the failing test**

```python
# hsge/tests/test_sitekb_runtime.py
"""Phase-1 wiring: every visited node gets its axtree persisted and a digest
added to sitekb.json; a digester crash logs digest_error and does not kill
the run."""
import json

from hsge.llm import HashingEmbedder
from hsge.webarena.runtime import WebArenaExplorer


class _LLM:
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        if system.startswith("PROPOSE"):
            return {"tasks": []}          # no episodes; isolates digest wiring
        if system.startswith("DIGEST"):
            return {"page_type": "page", "title": "home",
                    "entities": [{"type": "link", "name": "next", "attrs": {},
                                  "evidence": "link 'next'"}],
                    "facts": [{"q": "main link?", "a": "next", "evidence": "link 'next'"},
                              {"q": "made up?", "a": "x", "evidence": "absent"}]}
        return {}


class _BoomLLM(_LLM):
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        if system.startswith("DIGEST"):
            raise RuntimeError("digester down")
        return super().complete_json(system, prompt, image_b64, image_detail)


class _Browser:
    def __init__(self, url): self.url = url
    def reset(self): return {"url": self.url, "axtree": "[1] link 'next'", "bids": ["1"]}
    def links(self): return []
    def page_hrefs(self, limit=100): return ["http://site/a"]
    def close(self): pass


def _run(tmp_path, llm):
    WebArenaExplorer(
        browser_factory=_Browser, llm=llm, embedder=HashingEmbedder(),
        out_dir=str(tmp_path), allow_pattern=r"http://site",
        max_nodes=1, max_depth=3, terminal_goal=None,
        agent_llms={"node_digester": llm},
    ).run("http://site/home")


def test_node_digest_lands_in_sitekb_and_axtree_persisted(tmp_path):
    _run(tmp_path, _LLM())
    kb = json.load(open(tmp_path / "sitekb.json"))
    assert kb["site"] == "http://site/home"
    (node,) = kb["nodes"]
    assert node["node_index"] == 1 and node["url"] == "http://site/home"
    assert node["url_template"] == "site/home"
    assert "http://site/a" in node["outlinks"]
    assert [f["grounded"] for f in node["facts"]] == [True, False]
    axp = tmp_path / node["axtree_path"]
    assert axp.read_text() == "[1] link 'next'"


def test_digester_crash_logs_and_run_survives(tmp_path):
    _run(tmp_path, _BoomLLM())
    kb = json.load(open(tmp_path / "sitekb.json"))
    assert kb["nodes"] == []            # no digest, but the KB file still exists
    events = [json.loads(l)["event"] for l in open(tmp_path / "run_log.jsonl")]
    assert "digest_error" in events and "run_summary" in events
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest hsge/tests/test_sitekb_runtime.py -q`
Expected: FAIL — `FileNotFoundError: ... sitekb.json`

- [ ] **Step 3: Wire into `runtime.py`.**

3a. Imports — add to the existing `from .agents import ...` block area:

```python
from .digest import NodeDigester, SiteKB, extract_msg
```

3b. In `__init__`, after `self.discovery = Discovery(...)`:

```python
        self.digester = NodeDigester(role("node_digester"))
        self.sitekb = SiteKB()
```

3c. In `run()`, right after `self.run_started_epoch, self.run_started_iso = _now()`:

```python
        self.sitekb.site = root_url
```

3d. In the node loop, after `seen_urls = set()` add:

```python
                solved_tasks: list[dict] = []
```

and inside the local-task loop, right after `seen_urls.add(final_obs.get("url", ""))`:

```python
                    solved_tasks.append({
                        "task": task, "success": success,
                        "answer": extract_msg(steps[-1].action) if steps else "",
                        "final_axtree": obs_texts[-1] if obs_texts else ""})
```

3e. In the frontier-expansion block, hoist the mined list so the digest can reuse it. Replace:

```python
                    mined_new = 0
                    if self.mine_hrefs:
                        for link in browser.page_hrefs(self.max_hrefs_per_page):
```

with:

```python
                    mined_new = 0
                    if self.mine_hrefs:
                        mined_hrefs = browser.page_hrefs(self.max_hrefs_per_page)
                        for link in mined_hrefs:
```

and add `mined_hrefs: list[str] = []` just before the `if depth < self.max_depth:` line (so it exists when depth is maxed out or mining is off).

3f. After the frontier-expansion block and **before** `browser.close()`:

```python
                # persist the node's initial axtree + distill it into the SiteKB.
                # The digest is best-effort: a digester failure loses one node's
                # knowledge, never the run.
                node_dir = os.path.join(self.out_dir, "node_state")
                os.makedirs(node_dir, exist_ok=True)
                axp = f"node_state/node_{node_index:04d}_axtree.txt"
                open(os.path.join(self.out_dir, axp), "w").write(obs["axtree"])
                try:
                    nd = self.digester.digest(obs, solved_tasks)
                    nd.update({"node_index": node_index,
                               "url_template": self._url_template(obs["url"]),
                               "outlinks": sorted((seen_urls | set(mined_hrefs)) - {""}),
                               "axtree_path": axp})
                    self.sitekb.add_node(nd)
                except Exception as e:
                    self._log("digest_error", node_index=node_index, error=str(e))
                self.sitekb.skills = [c.to_dict() for c in self.library.all_skills()]
                self.sitekb.dump(os.path.join(self.out_dir, "sitekb.json"))
```

3g. In `run_webarena.py`, extend `AGENT_ROLES` (Task 7 wires the rest):

```python
AGENT_ROLES = (
    "page_explorer",
    "solver",
    "trajectory_segmenter",
    "skill_abstractor",
    "skill_verifier",
    "operator_inducer",
    "node_digester",     # phase 1: distills each node into the SiteKB
    "task_composer",     # phase 2: generates tasks from the SiteKB
    "judge",             # phase 2: optional fuzzy_match string judge
)
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest hsge/tests/ -q`
Expected: all PASS (existing `test_frontier_mining.py` etc. still pass — their scripted LLMs return `{}` for the DIGEST system prompt, which digests to an empty-but-valid node)

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/runtime.py run_webarena.py hsge/tests/test_sitekb_runtime.py
git commit -m "Wire NodeDigester + SiteKB into the phase-1 node loop"
```

---

### Task 4: `evaluator.py` + `browser.eval_js` + `Solver` hints

**Files:**
- Create: `hsge/webarena/evaluator.py`
- Modify: `hsge/webarena/browser.py` (add `eval_js`)
- Modify: `hsge/webarena/agents.py` (`Solver.solve` gains `hints`)
- Test: `hsge/tests/test_evaluator.py`

**Interfaces:**
- Consumes: `extract_msg` from `digest.py`; a browser exposing `act(action)`, `observation()`, `eval_js(expr) -> str`.
- Produces (used by Tasks 5, 6):
  - `normalize_answer(text: str) -> str`
  - `extract_answer(steps) -> str` — last `send_msg_to_user` payload in the episode.
  - `string_match(answer: str, reference_answers: dict, judge=None) -> bool`
  - `url_match(final_url: str, reference_url: str) -> bool`
  - `program_html(browser, specs: list[dict]) -> bool`
  - `evaluate(task: dict, answer: str, final_url: str, browser, judge=None) -> tuple[bool, dict]`
  - `Solver.solve(browser, goal, goal_predicate=None, hints=None)` — unchanged return type.
  - `WebArenaBrowser.eval_js(expr: str) -> str` — Playwright `page.evaluate`, `""` on failure.

- [ ] **Step 1: Write the failing tests**

```python
# hsge/tests/test_evaluator.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_evaluator.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hsge.webarena.evaluator'`

- [ ] **Step 3: Create `hsge/webarena/evaluator.py`**

```python
"""Minimal WebArena-style evaluators: string_match / url_match / program_html.

Verification here is what makes a phase-2 trajectory `verified` for SFT; a
task's eval spec is authored by the TaskComposer and validated against the
SiteKB before any episode runs (composer.validate_task).
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, urlsplit

from .digest import extract_msg

JUDGE_SYS = (
    "You judge whether a web agent's ANSWER conveys the same information as any "
    "of the REFERENCE answers. Return JSON {\"match\": true|false}. Judge meaning, "
    "not wording; numbers and names must actually agree.")


def normalize_answer(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return text.strip(" .,:;!?'\"")


def extract_answer(steps) -> str:
    for st in reversed(steps or []):
        msg = extract_msg(st.action)
        if msg:
            return msg
    return ""


def string_match(answer: str, reference_answers: dict, judge=None) -> bool:
    refs = reference_answers or {}
    na = normalize_answer(answer)
    if "exact_match" in refs:
        return na == normalize_answer(str(refs["exact_match"]))
    if "must_include" in refs:
        items = refs["must_include"] or []
        return bool(items) and all(normalize_answer(str(x)) in na for x in items)
    if "fuzzy_match" in refs and judge is not None:
        out = judge.complete_json(JUDGE_SYS, json.dumps(
            {"answer": answer, "references": refs["fuzzy_match"]}))
        return bool(out.get("match"))
    return False


def url_match(final_url: str, reference_url: str) -> bool:
    def key(u: str):
        p = urlsplit(u or "")
        return (p.netloc, (p.path.rstrip("/") or "/"), tuple(sorted(parse_qsl(p.query))))
    return bool(reference_url) and key(final_url) == key(reference_url)


def program_html(browser, specs: list[dict]) -> bool:
    for spec in specs or []:
        url = spec.get("url") or "last"
        if url != "last":
            browser.act(f"goto('{url}')")
        locator = spec.get("locator") or ""
        content = browser.eval_js(locator) if locator else browser.observation()["axtree"]
        text = normalize_answer(str(content))
        required = (spec.get("required_contents") or {}).get("must_include") or []
        if not required or not all(normalize_answer(str(x)) in text for x in required):
            return False
    return bool(specs)


def evaluate(task: dict, answer: str, final_url: str, browser, judge=None) -> tuple[bool, dict]:
    """(verified, per-type details). All declared eval types must pass; a task
    with no eval types can never verify (fail-closed)."""
    ev = task.get("eval") or {}
    details: dict[str, bool] = {}
    for t in ev.get("eval_types") or []:
        if t == "string_match":
            details[t] = string_match(answer, ev.get("reference_answers") or {}, judge=judge)
        elif t == "url_match":
            details[t] = url_match(final_url, ev.get("reference_url") or "")
        elif t == "program_html":
            details[t] = program_html(browser, ev.get("program_html") or [])
        else:
            details[t] = False
    return bool(details) and all(details.values()), details
```

- [ ] **Step 4: Add `eval_js` to `hsge/webarena/browser.py`** (after `page_hrefs`):

```python
    def eval_js(self, expr: str) -> str:
        """Evaluate a JS expression on the live page (program_html eval spec).
        Fail-soft to "" like observation()/page_hrefs()."""
        try:
            return str(self.env.unwrapped.page.evaluate(expr))
        except Exception:
            return ""
```

- [ ] **Step 5: Add `hints` to `Solver.solve` in `hsge/webarena/agents.py`.** Change the signature and the prompt construction:

```python
    def solve(self, browser, goal: str, goal_predicate: str | None = None,
              hints: str | None = None):
        """Drive the browser toward `goal`.

        `hints` (optional) is a short "known procedures" block retrieved from
        previously discovered skills; it is advisory context, never a script.
        Returns (steps, obs_texts, obs_screenshots, final_obs, success).
        """
```

and in the prompt f-string replace `prompt = (f"GOAL: {goal}\n\nRECENT ACTIONS:\n"` with:

```python
            prompt = (f"GOAL: {goal}\n"
                      + (f"\nKNOWN PROCEDURES (from earlier runs, may help):\n{hints}\n"
                         if hints else "")
                      + "\nRECENT ACTIONS:\n"
```

(the rest of the prompt concatenation is unchanged).

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest hsge/tests/ -q`
Expected: all PASS (evaluator tests green; `test_solver.py` unaffected by the optional param)

- [ ] **Step 7: Commit**

```bash
git add hsge/webarena/evaluator.py hsge/webarena/browser.py hsge/webarena/agents.py hsge/tests/test_evaluator.py
git commit -m "Add WebArena-style evaluator, browser.eval_js, and Solver skill hints"
```

---

### Task 5: `composer.py` — TaskComposer with code gates

**Files:**
- Create: `hsge/webarena/composer.py`
- Test: `hsge/tests/test_composer.py`

**Interfaces:**
- Consumes: `SiteKB` (Task 2: `resolve_ref`, `known_urls`, `.nodes`, `.site`), `normalize_answer` (Task 4).
- Produces (used by Tasks 6, 7):
  - `MOD_DENY_RE` — compiled denylist regex.
  - `sample_bundles(kb, rng, max_nodes=4) -> list[list[dict]]`
  - `validate_task(task: dict, kb, accepted: list[dict]) -> str | None` — rejection reason or None.
  - `TaskComposer(llm, kb, quota=None, hops=(2, 4), tasks_per_call=5, seed=0)` with `generate() -> tuple[list[dict], list[dict]]` (accepted with assigned `task_id`s `gen_0000...`, rejected as `{"task", "reason"}`).

- [ ] **Step 1: Write the failing tests**

```python
# hsge/tests/test_composer.py
"""TaskComposer gates are code: INFO answers must be backed by grounded SiteKB
refs, NAV targets must be known URLs, MOD intents pass a denylist and must not
collide on program_html targets. Rejected tasks carry a reason."""
import random

from hsge.webarena.composer import TaskComposer, sample_bundles, validate_task
from hsge.webarena.digest import SiteKB


def _kb():
    kb = SiteKB(site="http://s")
    kb.add_node({"node_index": 1, "url": "http://s/f/gaming",
                 "page_type": "forum", "title": "gaming",
                 "outlinks": ["http://s/f/gaming/post1"],
                 "entities": [{"type": "post", "name": "Best budget GPU",
                               "attrs": {"author": "hlz0"}, "grounded": True}],
                 "facts": [{"q": "top post?", "a": "Best budget GPU", "grounded": True},
                           {"q": "mods?", "a": "bob", "grounded": False}]})
    kb.add_node({"node_index": 2, "url": "http://s/f/movies", "page_type": "forum",
                 "title": "movies", "outlinks": [],
                 "entities": [{"type": "post", "name": "Dune review",
                               "attrs": {}, "grounded": True}], "facts": []})
    return kb


def _info(refs, ra):
    return {"intent": "find the author of the top post in gaming", "type": "INFO",
            "start_url": "http://s", "hops": 2, "source_nodes": [1],
            "answer_fact_refs": refs,
            "eval": {"eval_types": ["string_match"], "reference_answers": ra,
                     "reference_url": None, "program_html": []}}


def test_validate_info_gates():
    kb = _kb()
    assert validate_task(_info(["n1.e0.attrs.author"], {"exact_match": "hlz0"}), kb, []) is None
    assert "ungrounded" in validate_task(_info(["n1.f1"], {"exact_match": "bob"}), kb, [])
    assert "unknown ref" in validate_task(_info(["n9.f0"], {"exact_match": "x"}), kb, [])
    assert "not backed" in validate_task(
        _info(["n1.e0.attrs.author"], {"exact_match": "someone else"}), kb, [])
    assert "without answer_fact_refs" in validate_task(_info([], {"exact_match": "x"}), kb, [])


def test_validate_nav_mod_and_dedup():
    kb = _kb()
    nav = {"intent": "go to the first gaming post", "type": "NAV", "start_url": "http://s",
           "hops": 2, "source_nodes": [1], "answer_fact_refs": [],
           "eval": {"eval_types": ["url_match"], "reference_answers": None,
                    "reference_url": "http://s/f/gaming/post1", "program_html": []}}
    assert validate_task(nav, kb, []) is None
    nav_bad = dict(nav, eval=dict(nav["eval"], reference_url="http://elsewhere"))
    assert "not in SiteKB" in validate_task(nav_bad, kb, [])

    mod = {"intent": "post a comment saying hello under Dune review", "type": "MOD",
           "start_url": "http://s", "hops": 2, "source_nodes": [2], "answer_fact_refs": [],
           "eval": {"eval_types": ["program_html"], "reference_answers": None,
                    "reference_url": None,
                    "program_html": [{"url": "http://s/f/movies", "locator": "",
                                      "required_contents": {"must_include": ["hello"]}}]}}
    assert validate_task(mod, kb, []) is None
    assert "destructive" in validate_task(dict(mod, intent="delete the Dune review"), kb, [])
    mod2 = dict(mod, intent="post another comment under Dune review")
    assert "collides" in validate_task(mod2, kb, [dict(mod, task_id="gen_0000")])
    assert "duplicate" in validate_task(dict(mod), kb, [dict(mod, task_id="gen_0000")])


def test_sample_bundles_links_and_types():
    bundles = sample_bundles(_kb(), random.Random(0))
    # link-neighborhood bundles + one same-entity-type ("post") bundle
    assert any(len(b) == 2 and {n["node_index"] for n in b} == {1, 2} for b in bundles)


class _ComposerLLM:
    def __init__(self): self.calls = 0
    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        assert system.startswith("COMPOSE")
        self.calls += 1
        return {"tasks": [
            _info_task("find the author of the top gaming post"),
            _info_task("find the author of the top gaming post"),      # dup -> rejected
            dict(_info_task("tell me the moderator"),
                 answer_fact_refs=["n1.f1"]),                           # ungrounded -> rejected
        ]}


def _info_task(intent):
    return {"intent": intent, "type": "INFO", "start_url": "http://s", "hops": 2,
            "source_nodes": [1], "answer_fact_refs": ["n1.e0.attrs.author"],
            "eval": {"eval_types": ["string_match"],
                     "reference_answers": {"exact_match": "hlz0"},
                     "reference_url": None, "program_html": []}}


def test_generate_assigns_ids_and_collects_rejections():
    comp = TaskComposer(_ComposerLLM(), _kb(), quota={"INFO": 5, "NAV": 0, "MOD": 0})
    accepted, rejected = comp.generate()
    assert [t["task_id"] for t in accepted] == ["gen_0000"]
    assert len(rejected) >= 2
    assert all(r["reason"] for r in rejected)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_composer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hsge.webarena.composer'`

- [ ] **Step 3: Create `hsge/webarena/composer.py`**

```python
"""TaskComposer: generate WebArena-style tasks (with eval specs) from a SiteKB.

Generation is per "context bundle" (a few related node digests), never the
whole KB in one prompt, so multi-hop tasks are grounded in pages that really
link together. Hard gates are code: INFO reference answers must be backed by
grounded SiteKB refs, NAV targets must be known URLs, MOD intents pass a
denylist and must not collide on program_html targets.
"""
from __future__ import annotations

import json
import random
import re

from .evaluator import normalize_answer

MOD_DENY_RE = re.compile(
    r"\b(delete|remove|erase|logout|log\s*out|password|ban|deactivate|wipe)\b", re.I)
_PUNCT_RE = re.compile(r"[^\w\s]")

COMPOSER_SYS = (
    "COMPOSE realistic WebArena-style tasks for a web agent from the site knowledge "
    'below. Return JSON {"tasks": [{"intent": str, "type": "INFO"|"NAV"|"MOD", '
    '"start_url": str, "hops": int, "source_nodes": [int], "answer_fact_refs": [str], '
    '"eval": {"eval_types": [str], "reference_answers": object|null, '
    '"reference_url": str|null, "program_html": [object]}}]}.\n'
    "Rules:\n"
    "- intent reads like a real user request; prefer multi-hop (hops = pages the "
    "agent must traverse to solve it). Never put the answer in the intent text.\n"
    '- INFO: eval_types=["string_match"]; reference_answers is {"exact_match": str} '
    'or {"must_include": [str, ...]}; answer_fact_refs cites the knowledge refs the '
    'answer comes from (e.g. "n12.f3", "n13.e1.attrs.author") -- ONLY items shown '
    "with grounded=true.\n"
    '- NAV: eval_types=["url_match"]; reference_url must be a URL from the knowledge.\n'
    '- MOD: eval_types=["program_html"]; entries are {"url": str|"last", "locator": '
    'str (JS expression, "" = check the whole page), "required_contents": '
    '{"must_include": [str, ...]}}. Never destructive (no delete/remove/logout/'
    "password/ban).\n"
    "- Do not repeat or trivially rephrase ALREADY GENERATED intents.")


def _norm_intent(text: str) -> str:
    return re.sub(r"\s+", " ", _PUNCT_RE.sub("", (text or "").lower())).strip()


def _mod_target_urls(task: dict) -> set[str]:
    urls = {p.get("url") for p in (task.get("eval") or {}).get("program_html") or []}
    return {u for u in urls if u and u != "last"}


def sample_bundles(kb, rng: random.Random, max_nodes: int = 4) -> list[list[dict]]:
    """Link-neighborhood bundles (a node + KB nodes it links to) plus
    same-entity-type bundles (e.g. every node holding 'post' entities)."""
    rich = [n for n in kb.nodes if (n.get("entities") or n.get("facts"))]
    by_url = {n.get("url"): n for n in kb.nodes}
    by_idx = {n.get("node_index"): n for n in kb.nodes}
    bundles: list[list[dict]] = []
    for n in rich:
        linked = [by_url[u] for u in (n.get("outlinks") or [])
                  if u in by_url and by_url[u] is not n]
        bundles.append([n] + linked[: max_nodes - 1])
    by_type: dict[str, set[int]] = {}
    for n in rich:
        for e in n.get("entities") or []:
            by_type.setdefault(str(e.get("type") or ""), set()).add(n["node_index"])
    for _t, idxs in sorted(by_type.items()):
        if len(idxs) >= 2:
            bundles.append([by_idx[i] for i in sorted(idxs)[:max_nodes]])
    rng.shuffle(bundles)
    return bundles


def validate_task(task, kb, accepted: list[dict]) -> str | None:
    """Rejection reason, or None when the task passes every code gate."""
    if not isinstance(task, dict):
        return "not an object"
    intent = str(task.get("intent") or "")
    ttype = task.get("type")
    if ttype not in ("INFO", "NAV", "MOD"):
        return "bad type"
    if not intent.strip():
        return "empty intent"
    key = _norm_intent(intent)
    if any(_norm_intent(a.get("intent", "")) == key for a in accepted):
        return "duplicate intent"
    ev = task.get("eval") or {}
    types = ev.get("eval_types") or []
    if ttype == "INFO":
        if "string_match" not in types:
            return "INFO without string_match"
        refs = task.get("answer_fact_refs") or []
        if not refs:
            return "INFO without answer_fact_refs"
        resolved = []
        for r in refs:
            got = kb.resolve_ref(r)
            if got is None:
                return f"unknown ref {r}"
            val, grounded = got
            if not grounded:
                return f"ungrounded ref {r}"
            resolved.append(normalize_answer(val))
        ra = ev.get("reference_answers") or {}
        targets = ([ra["exact_match"]] if "exact_match" in ra
                   else ra.get("must_include") or [])
        if not targets:
            return "INFO without reference answer"
        for t in targets:
            nt = normalize_answer(str(t))
            if not any(nt == v or nt in v for v in resolved):
                return f"reference answer {t!r} not backed by refs"
    elif ttype == "NAV":
        if "url_match" not in types:
            return "NAV without url_match"
        if ev.get("reference_url") not in kb.known_urls():
            return "reference_url not in SiteKB"
    else:  # MOD
        if MOD_DENY_RE.search(intent):
            return "destructive MOD intent"
        if "program_html" not in types or not ev.get("program_html"):
            return "MOD without program_html"
        mine = _mod_target_urls(task)
        for a in accepted:
            if a.get("type") == "MOD" and mine & _mod_target_urls(a):
                return "MOD target collides with an accepted MOD task"
    return None


class TaskComposer:
    def __init__(self, llm, kb, quota: dict | None = None, hops: tuple = (2, 4),
                 tasks_per_call: int = 5, seed: int = 0):
        self.llm = llm
        self.kb = kb
        self.quota = dict(quota or {"INFO": 60, "NAV": 20, "MOD": 20})
        self.hops = hops
        self.tasks_per_call = tasks_per_call
        self.rng = random.Random(seed)

    def _render_bundle(self, bundle: list[dict]) -> str:
        view = []
        for n in bundle:
            view.append({
                "node_index": n["node_index"], "url": n.get("url"),
                "page_type": n.get("page_type"), "title": n.get("title"),
                "entities": [dict(e, ref=f"n{n['node_index']}.e{i}")
                             for i, e in enumerate(n.get("entities") or [])],
                "facts": [dict(f, ref=f"n{n['node_index']}.f{i}")
                          for i, f in enumerate(n.get("facts") or [])],
                "outlinks": (n.get("outlinks") or [])[:20]})
        return json.dumps(view, indent=1)

    def generate(self) -> tuple[list[dict], list[dict]]:
        accepted: list[dict] = []
        rejected: list[dict] = []
        remaining = dict(self.quota)
        for bundle in sample_bundles(self.kb, self.rng):
            if all(v <= 0 for v in remaining.values()):
                break
            prompt = (f"SITE: {self.kb.site}\nQUOTA REMAINING: {remaining}\n"
                      f"PREFERRED HOPS: {self.hops[0]}-{self.hops[1]}\n\n"
                      f"SITE KNOWLEDGE (this bundle):\n{self._render_bundle(bundle)}\n\n"
                      "ALREADY GENERATED:\n"
                      + ("\n".join(f"- {a['intent']}" for a in accepted[-30:]) or "(none)")
                      + f"\n\nGenerate up to {self.tasks_per_call} tasks from THIS bundle.")
            out = self.llm.complete_json(COMPOSER_SYS, prompt) or {}
            for t in out.get("tasks") or []:
                reason = None
                if isinstance(t, dict) and remaining.get(t.get("type"), 0) <= 0:
                    reason = "quota exhausted for type"
                reason = reason or validate_task(t, self.kb, accepted)
                if reason:
                    rejected.append({"task": t, "reason": reason})
                    continue
                t["task_id"] = f"gen_{len(accepted):04d}"
                t.setdefault("start_url", self.kb.site)
                t.setdefault("hops", 1)
                accepted.append(t)
                remaining[t["type"]] -= 1
        return accepted, rejected
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest hsge/tests/test_composer.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/composer.py hsge/tests/test_composer.py
git commit -m "Add TaskComposer: bundle-sampled task generation with code gates"
```

---

### Task 6: `collect.py` — phase-2 collection loop

**Files:**
- Create: `hsge/webarena/collect.py`
- Test: `hsge/tests/test_collect.py`

**Interfaces:**
- Consumes: `record_episode` (Task 1), `evaluate`/`extract_answer` (Task 4), `SiteKB` (Task 2), a `Solver`-shaped object (`solve(browser, goal, goal_predicate=None, hints=None) -> (steps, obs_texts, obs_screenshots, final_obs, success)`), an `Embedder` (`encode(list[str]) -> ndarray`), optional `Discovery` (`on_trajectory(steps, site=..., task=...)`).
- Produces (used by Task 7):
  - `top_k_skill_hints(embedder, skills: list[dict], intent: str, k=3) -> str | None`
  - `GenerationRunner(browser_factory, solver, out_dir, embedder, kb, judge_llm=None, discovery=None, root_url="", reset_fn=None, skill_hints=True)` with `run(tasks: list[dict]) -> dict` (the stats dict also written to `summary.json["gen"]`). Episodes land in `out_dir/episodes/` as tag `GEN`, `difficulty=hops`, meta `task_id`/`verified`/`task_type`/`eval`/`answer`/`eval_details`. Resume: task_ids already on disk are skipped. `reset_fn` is called once, after the MOD batch, iff any MOD task ran.

- [ ] **Step 1: Write the failing tests**

```python
# hsge/tests/test_collect.py
"""GenerationRunner: INFO/NAV run before MOD, verdicts gate `verified`, resume
skips task_ids already on disk, stats land in summary.json['gen'], and the
(expensive) instance reset runs once after the MOD batch."""
import json

from hsge.llm import HashingEmbedder
from hsge.schema import Step
from hsge.webarena.collect import GenerationRunner, top_k_skill_hints
from hsge.webarena.digest import SiteKB


class _Browser:
    def __init__(self, url): self.url = url
    def reset(self): return self.observation()
    def observation(self): return {"url": self.url, "axtree": "comment 'hello world'"}
    def act(self, action): return self.observation()
    def eval_js(self, expr): return ""
    def close(self): pass


class _Solver:
    """Answers '42' to everything; the eval spec decides pass/fail."""
    def solve(self, browser, goal, goal_predicate=None, hints=None):
        steps = [Step(action="send_msg_to_user('the answer is 42')",
                      url=browser.url, axtree="ax")]
        return steps, ["ax"], [None], browser.observation(), True


def _task(tid, ttype="INFO", ra=None, ph=None):
    return {"task_id": tid, "intent": f"task {tid}", "type": ttype,
            "start_url": "http://s/home", "hops": 2, "source_nodes": [1],
            "answer_fact_refs": [],
            "eval": {"eval_types": ["string_match"] if ttype == "INFO" else ["program_html"],
                     "reference_answers": ra, "reference_url": None,
                     "program_html": ph or []}}


def test_runner_verifies_orders_and_resets(tmp_path):
    resets = []
    tasks = [_task("gen_0002", "MOD",
                   ph=[{"url": "last", "locator": "",
                        "required_contents": {"must_include": ["hello world"]}}]),
             _task("gen_0000", ra={"must_include": ["42"]}),
             _task("gen_0001", ra={"exact_match": "not this"})]
    runner = GenerationRunner(_Browser, _Solver(), str(tmp_path), HashingEmbedder(),
                              SiteKB(), reset_fn=lambda: resets.append(1),
                              skill_hints=False)
    stats = runner.run(tasks)
    assert stats["attempted"] == 3 and stats["verified"] == 2 and stats["failed"] == 1
    assert resets == [1]                       # once, after the MOD batch
    metas = sorted(
        (json.load(open(p)) for p in tmp_path.glob("episodes/*/episode_meta.json")),
        key=lambda m: m["task_id"])
    assert [(m["task_id"], m["verified"]) for m in metas] == [
        ("gen_0000", True), ("gen_0001", False), ("gen_0002", True)]
    # MOD ran last despite being listed first
    assert metas[2]["task_id"] == "gen_0002"
    ep_dirs = sorted(p.name for p in (tmp_path / "episodes").iterdir())
    mod_meta = json.load(open(tmp_path / "episodes" / ep_dirs[-1] / "episode_meta.json"))
    assert mod_meta["task_id"] == "gen_0002"
    assert json.load(open(tmp_path / "summary.json"))["gen"]["verified"] == 2


def test_runner_resumes_and_skips_done(tmp_path):
    t = _task("gen_0000", ra={"must_include": ["42"]})
    runner = GenerationRunner(_Browser, _Solver(), str(tmp_path), HashingEmbedder(),
                              SiteKB(), skill_hints=False)
    runner.run([t])
    n_eps = len(list((tmp_path / "episodes").iterdir()))
    runner2 = GenerationRunner(_Browser, _Solver(), str(tmp_path), HashingEmbedder(),
                               SiteKB(), skill_hints=False)
    stats = runner2.run([t])
    assert stats["attempted"] == 0
    assert len(list((tmp_path / "episodes").iterdir())) == n_eps


def test_top_k_skill_hints():
    skills = [{"name": "open_forum", "description": "open a forum page"},
              {"name": "checkout", "description": "complete a purchase"}]
    hints = top_k_skill_hints(HashingEmbedder(), skills, "go to the gaming forum", k=1)
    assert hints and hints.count("\n") == 0     # exactly one hint line
    assert top_k_skill_hints(HashingEmbedder(), [], "x") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_collect.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hsge.webarena.collect'`

- [ ] **Step 3: Create `hsge/webarena/collect.py`**

```python
"""Phase-2 collection loop: solve composer-generated tasks, verify, record.

INFO/NAV run before the MOD batch so read answers can't be dirtied by writes,
and the (slow) instance reset happens at most once, after all MODs. Re-running
is idempotent: task_ids that already have an episode on disk are skipped.
"""
from __future__ import annotations

import glob
import json
import os

from .evaluator import evaluate, extract_answer
from .recording import record_episode


def top_k_skill_hints(embedder, skills: list[dict], intent: str, k: int = 3) -> str | None:
    texts = [f"{s['name']}: {s.get('description', '')}"
             for s in skills or [] if s.get("name")]
    if not texts:
        return None
    vecs = embedder.encode(texts + [intent])
    q = vecs[-1]
    scored = sorted(zip((float(v @ q) for v in vecs[:-1]), texts), reverse=True)
    return "\n".join(f"- {t}" for _, t in scored[:k])


class GenerationRunner:
    def __init__(self, browser_factory, solver, out_dir: str, embedder, kb,
                 judge_llm=None, discovery=None, root_url: str = "",
                 reset_fn=None, skill_hints: bool = True):
        self.browser_factory = browser_factory
        self.solver = solver
        self.out_dir = out_dir
        self.embedder = embedder
        self.kb = kb
        self.judge_llm = judge_llm
        self.discovery = discovery
        self.root_url = root_url
        self.reset_fn = reset_fn
        self.skill_hints = skill_hints
        os.makedirs(os.path.join(out_dir, "episodes"), exist_ok=True)
        # continue numbering after phase-1 episodes (never overwrite them)
        self.episode = len(glob.glob(os.path.join(out_dir, "episodes", "ep_*")))

    def _done_task_ids(self) -> set[str]:
        done = set()
        for p in glob.glob(os.path.join(self.out_dir, "episodes", "*", "episode_meta.json")):
            try:
                tid = json.load(open(p)).get("task_id")
            except Exception:
                continue
            if tid:
                done.add(tid)
        return done

    def _dump_stats(self, stats: dict):
        """Merge GEN stats into summary.json without clobbering phase-1 fields."""
        spath = os.path.join(self.out_dir, "summary.json")
        summary = {}
        if os.path.exists(spath):
            try:
                summary = json.load(open(spath))
            except Exception:
                summary = {}
        summary["gen"] = stats
        json.dump(summary, open(spath, "w"), indent=2)

    def run(self, tasks: list[dict]) -> dict:
        order = ([t for t in tasks if t.get("type") in ("INFO", "NAV")]
                 + [t for t in tasks if t.get("type") == "MOD"])
        done = self._done_task_ids()
        stats = {"attempted": 0, "verified": 0, "failed": 0, "errors": 0,
                 "by_type": {k: {"verified": 0, "failed": 0}
                             for k in ("INFO", "NAV", "MOD")}}
        ran_mod = False
        for task in order:
            if task["task_id"] in done:
                continue
            stats["attempted"] += 1
            browser = self.browser_factory(task["start_url"])
            try:
                browser.reset()
                hints = (top_k_skill_hints(self.embedder, self.kb.skills, task["intent"])
                         if self.skill_hints else None)
                steps, obs_texts, shots, final_obs, _ = self.solver.solve(
                    browser, task["intent"], hints=hints)
                answer = extract_answer(steps)
                verified, details = evaluate(task, answer, final_obs.get("url", ""),
                                             browser, judge=self.judge_llm)
            except Exception as e:  # a dead episode must not kill the batch
                steps, obs_texts, shots = [], [], []
                answer, verified, details = "", False, {"error": str(e)}
                stats["errors"] += 1
            finally:
                browser.close()
            record_episode(
                self.out_dir, self.episode, task["intent"], steps, obs_texts, shots,
                verified, difficulty=int(task.get("hops") or 1), tag="GEN",
                extra_meta={"task_id": task["task_id"], "verified": verified,
                            "task_type": task.get("type"), "eval": task.get("eval"),
                            "answer": answer, "eval_details": details})
            self.episode += 1
            stats["verified" if verified else "failed"] += 1
            by = stats["by_type"].get(task.get("type"))
            if by is not None:
                by["verified" if verified else "failed"] += 1
            if task.get("type") == "MOD":
                ran_mod = True
            if verified and self.discovery:
                self.discovery.on_trajectory(steps, site=self.root_url,
                                             task=task["intent"])
            print(f"    [gen] {task['task_id']} {task.get('type')} "
                  f"verified={verified} steps={len(steps)}")
            self._dump_stats(stats)   # after every task: interrupt-safe snapshot
        if ran_mod and self.reset_fn:
            self.reset_fn()
        return stats
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest hsge/tests/test_collect.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add hsge/webarena/collect.py hsge/tests/test_collect.py
git commit -m "Add phase-2 GenerationRunner: verify, record, resume, reset-frugal MOD batch"
```

---

### Task 7: `--phase` CLI, `gen:` config, dry-run through both phases

**Files:**
- Modify: `run_webarena.py`
- Modify: `config.yaml`

**Interfaces:**
- Consumes: everything above.
- Produces: `python run_webarena.py --phase generate --out <dir>` runs phase 2 against an existing `sitekb.json`; `--phase all` chains both; default `--phase explore` is byte-for-byte today's behavior. `--dry-run --phase all` exercises the whole pipeline offline. Existing `gen_tasks.json` is reused (no composer re-burn) on re-run.

- [ ] **Step 1: Add the `gen` section to `DEFAULTS` in `run_webarena.py`**

```python
    "gen": {"quota": {"INFO": 60, "NAV": 20, "MOD": 20}, "hops_min": 2, "hops_max": 4,
            "max_steps": 25, "skill_hints": True},
```

(`_load_config` already merges any section present in `DEFAULTS`.)

- [ ] **Step 2: Extend `_DryLLM` and `_FakeBrowser`.** Add to `_DryLLM.complete_json`, before the `if system.startswith("PROPOSE")` line:

```python
        if system.startswith("DIGEST"):                          # node digester
            return {"page_type": "page", "title": "home",
                    "entities": [{"type": "link", "name": "next", "attrs": {},
                                  "evidence": "link 'next'"}],
                    "facts": [{"q": "main link label?", "a": "next",
                               "evidence": "link 'next'"}]}
        if system.startswith("COMPOSE"):                         # task composer
            return {"tasks": [{
                "intent": "Find the label of the main link on the home page and report it",
                "type": "INFO", "start_url": "http://shop/home", "hops": 2,
                "source_nodes": [1], "answer_fact_refs": ["n1.f0"],
                "eval": {"eval_types": ["string_match"],
                         "reference_answers": {"must_include": ["next"]},
                         "reference_url": None, "program_html": []}}]}
```

and add to the solver branch (inside `if "web agent" in system.lower():`, before the purchase check):

```python
            if "report it" in prompt.lower():                    # phase-2 INFO task
                return {"thought": "answer", "action": "send_msg_to_user('the label is next')"}
```

Add a no-op `eval_js` to `_FakeBrowser`:

```python
    def eval_js(self, expr: str) -> str: return ""
```

- [ ] **Step 3: Add the `--phase` flag and phase wiring in `main()`.** Add near the other args:

```python
    ap.add_argument("--phase", choices=["explore", "generate", "all"], default="explore",
                    help="explore = phase-1 frontier loop (default, current behavior); "
                         "generate = phase-2 task generation + verified collection "
                         "(needs sitekb.json in --out); all = both")
```

Add `import json` to the imports. In `main()`, add `gen_cfg = cfg["gen"]` next to the other section unpacks, and add `full_reset_url = None` immediately before the `if args.dry_run:` branch. The real branch already contains `full_reset_url = _pick(...)`, which now rebinds that pre-initialized name; the dry-run branch leaves it `None`, so the phase-2 wiring below can reference `full_reset_url` in both modes.

Replace the tail of `main()`:

```python
    explorer.run(root_url)
    print("\nnext: python build_sft_dataset.py", os.path.join(out_dir, "episodes"), "train.jsonl")
```

with:

```python
    if args.phase in ("explore", "all"):
        explorer.run(root_url)

    if args.phase in ("generate", "all"):
        from hsge.webarena.collect import GenerationRunner
        from hsge.webarena.composer import TaskComposer
        from hsge.webarena.digest import SiteKB
        from hsge.webarena.agents import Solver

        kb_path = os.path.join(out_dir, "sitekb.json")
        if not os.path.exists(kb_path):
            ap.error(f"--phase generate needs {kb_path} (run --phase explore first)")
        kb = SiteKB.load(kb_path)

        gt_path = os.path.join(out_dir, "gen_tasks.json")
        if os.path.exists(gt_path):    # idempotent re-run: no composer re-burn
            tasks = json.load(open(gt_path))["accepted"]
            print(f"[gen] reusing {len(tasks)} tasks from {gt_path}")
        else:
            composer = TaskComposer(agent_llms["task_composer"], kb,
                                    quota=gen_cfg["quota"],
                                    hops=(gen_cfg["hops_min"], gen_cfg["hops_max"]))
            tasks, rejected = composer.generate()
            json.dump({"accepted": tasks, "rejected": rejected},
                      open(gt_path, "w"), indent=2)
            print(f"[gen] composed {len(tasks)} tasks ({len(rejected)} rejected) -> {gt_path}")

        sv = agent_vision["solver"]
        gen_solver = Solver(agent_llms["solver"], max_steps=gen_cfg["max_steps"],
                            vision=sv["vision"], som=sv["som"],
                            image_detail=sv["image_detail"])
        runner = GenerationRunner(
            browser_factory, gen_solver, out_dir, embedder, kb,
            judge_llm=agent_llms.get("judge"),
            discovery=explorer.discovery if args.phase == "all" else None,
            root_url=root_url,
            reset_fn=(lambda: perform_full_reset(full_reset_url)) if full_reset_url else None,
            skill_hints=bool(gen_cfg["skill_hints"]))
        stats = runner.run(tasks)
        print(f"[gen] done: {stats['verified']} verified / {stats['attempted']} attempted")

    print("\nnext: python build_sft_dataset.py", os.path.join(out_dir, "episodes"), "train.jsonl")
```

- [ ] **Step 4: Add the new roles + `gen` block to `config.yaml`.** Under `llm.agents`, after `operator_inducer`:

```yaml
    node_digester:           # phase 1: distills each visited node into the SiteKB
      model: deepseek-v4-flash
    task_composer:           # phase 2: composes WebArena-style tasks from the SiteKB
      provider: openai
      model: gpt-4o          # whole-KB reasoning -- worth the stronger model
    judge:                   # phase 2: fuzzy_match string judge (rarely called)
      model: deepseek-v4-flash
```

Top-level, after the `embedder:` block:

```yaml
gen:                         # phase 2 (run_webarena.py --phase generate|all)
  quota: {INFO: 60, NAV: 20, MOD: 20}   # generated-task budget per type
  hops_min: 2                # preferred multi-hop range for composed tasks
  hops_max: 4
  max_steps: 25              # solver step budget per generated task
  skill_hints: true          # inject top-k discovered skills into the solver prompt
```

- [ ] **Step 5: End-to-end dry run**

Run: `python run_webarena.py --dry-run --phase all --out /tmp/wa_dry_gen --max-nodes 2`
Expected output/artifacts:
- `[gen] composed 1 tasks ... -> /tmp/wa_dry_gen/gen_tasks.json`
- `[gen] gen_0000 INFO verified=True ...`
- `/tmp/wa_dry_gen/sitekb.json` exists with grounded facts; `gen_tasks.json` has `accepted` + `rejected`; one `GEN` episode dir with `"verified": true` in its meta; `summary.json` has a `"gen"` key.

Then re-run the same command: expected `[gen] reusing 1 tasks ...` and `attempted == 0` (resume path, no duplicate episodes).

Also run: `python run_webarena.py --dry-run --out /tmp/wa_dry_plain --max-nodes 2` (no `--phase`)
Expected: behaves exactly like today's dry run (no `[gen]` lines) plus the new `sitekb.json`.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest hsge/tests/ -q`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add run_webarena.py config.yaml
git commit -m "Add --phase explore|generate|all: compose + collect verified GEN episodes"
```

---

### Task 8: `build_sft_dataset.py` — verified-GEN gating + `--include-local`

**Files:**
- Modify: `build_sft_dataset.py`
- Test: `hsge/tests/test_build_sft.py`

**Interfaces:**
- Consumes: run-dir episode layout incl. the new meta fields (`verified`, `metadata.tags`).
- Produces: `build(src: str, out: str, include_local: bool = False) -> dict` (stats: `{"episodes_seen", "kept", "examples"}`) — importable for tests; `main()` argparse CLI: `python build_sft_dataset.py <src> [out.jsonl] [--include-local]`. Default selection: `GEN` + `verified` only; `--include-local` additionally admits self-reported LOCAL/GOAL successes.

- [ ] **Step 1: Write the failing test**

```python
# hsge/tests/test_build_sft.py
"""build_sft_dataset gates on verification: by default only verified GEN
episodes are kept (self-reported LOCAL successes need --include-local)."""
import json

from hsge.schema import Step
from hsge.webarena.recording import record_episode
from build_sft_dataset import build


def _mk(tmp_path, idx, tag, success, extra=None, difficulty=1):
    record_episode(str(tmp_path), idx, f"goal {idx}",
                   [Step(action="click('1')", url="u", obs_summary="t", axtree="ax")],
                   ["ax"], [None], success, difficulty, tag, extra_meta=extra)


def test_default_keeps_only_verified_gen(tmp_path):
    _mk(tmp_path, 0, "GEN", True, {"task_id": "gen_0000", "verified": True}, difficulty=3)
    _mk(tmp_path, 1, "GEN", False, {"task_id": "gen_0001", "verified": False})
    _mk(tmp_path, 2, "LOCAL", True)
    out = tmp_path / "train.jsonl"
    stats = build(str(tmp_path), str(out))
    assert stats["kept"] == 1
    (ex,) = [json.loads(l) for l in open(out)]
    assert ex["difficulty"] == 3


def test_include_local_admits_self_reported_successes(tmp_path):
    _mk(tmp_path, 0, "GEN", True, {"task_id": "gen_0000", "verified": True})
    _mk(tmp_path, 1, "LOCAL", True)
    _mk(tmp_path, 2, "LOCAL", False)     # failures never enter
    stats = build(str(tmp_path), str(tmp_path / "t.jsonl"), include_local=True)
    assert stats["kept"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest hsge/tests/test_build_sft.py -q`
Expected: FAIL — `ImportError: cannot import name 'build'`

- [ ] **Step 3: Rework `build_sft_dataset.py`.** Keep `SYSTEM`, `_read_axtree`, `_difficulty`, `episode_to_examples` as they are. Replace `load_episodes` (yield the full meta) and `main` (argparse + `build`):

```python
def _keep(meta: dict, include_local: bool) -> bool:
    """Default gate: only GEN episodes that PASSED their eval spec (verified).
    Self-reported LOCAL/GOAL successes are opt-in via --include-local."""
    tags = (meta.get("metadata") or {}).get("tags") or []
    if "GEN" in tags:
        return bool(meta.get("verified"))
    return include_local and bool((meta.get("outcome") or {}).get("success"))


def load_episodes(path: str):
    """Yield (goal, steps, episode_dir, difficulty, meta) tuples."""
    if os.path.isfile(path) and path.endswith(".json"):
        d = json.load(open(path))
        em = d.get("episode_meta", d)
        ti = d.get("task_info", {})
        steps = d.get("steps") or []
        yield em.get("goal", ""), steps, os.path.dirname(path), _difficulty(ti, em), em
        return
    for meta_path in glob.glob(os.path.join(path, "**", "episode_meta.json"), recursive=True):
        ep_dir = os.path.dirname(meta_path)
        em = json.load(open(meta_path))
        jl = os.path.join(ep_dir, "episode.jsonl")
        steps = [json.loads(l) for l in open(jl)] if os.path.exists(jl) else []
        ti_path = os.path.join(ep_dir, "..", "..", "task_info.json")
        ti = json.load(open(ti_path)) if os.path.exists(ti_path) else {}
        yield em.get("goal", ""), steps, ep_dir, _difficulty(ti, em), em


def build(src: str, out: str, include_local: bool = False) -> dict:
    all_examples, n_ep, n_kept = [], 0, 0
    for goal, steps, ep_dir, diff, meta in load_episodes(src):
        n_ep += 1
        if not _keep(meta, include_local):
            continue
        n_kept += 1
        all_examples += episode_to_examples(goal, steps, ep_dir, diff)
    all_examples.sort(key=lambda e: e["difficulty"])   # curriculum: easy -> hard
    with open(out, "w") as f:
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n")
    return {"episodes_seen": n_ep, "kept": n_kept, "examples": len(all_examples)}


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="run dir or single episode json")
    ap.add_argument("out", nargs="?", default="train.jsonl")
    ap.add_argument("--include-local", action="store_true",
                    help="also include self-reported LOCAL/GOAL successes "
                         "(default: verified GEN episodes only)")
    args = ap.parse_args()
    stats = build(args.src, args.out, include_local=args.include_local)
    print(f"episodes seen        : {stats['episodes_seen']}")
    print(f"kept (verified/gated): {stats['kept']}")
    print(f"SFT examples written : {stats['examples']} -> {args.out}")
```

Also update the module docstring's Usage line to:

```
Usage:
    python build_sft_dataset.py <run_dir_or_episode.json> [out.jsonl] [--include-local]

By default only verified GEN episodes (phase-2, eval-spec-passing) are kept;
--include-local additionally admits self-reported LOCAL/GOAL successes.
```

(the old per-difficulty/axtree summary prints can be dropped or kept; keep the code minimal — drop them.)

- [ ] **Step 4: Run tests + a smoke on the dry-run output**

Run: `python -m pytest hsge/tests/test_build_sft.py -q`
Expected: PASS (2 tests)

Run: `python build_sft_dataset.py /tmp/wa_dry_gen train_dry.jsonl && rm train_dry.jsonl`
Expected: `kept (verified/gated): 1` (only the verified GEN episode from Task 7's dry run)

- [ ] **Step 5: Run the full suite, then commit**

Run: `python -m pytest hsge/tests/ -q` — expected: all PASS

```bash
git add build_sft_dataset.py hsge/tests/test_build_sft.py
git commit -m "Gate SFT dataset on verified GEN episodes; --include-local opt-in"
```

---

### Task 9: Documentation

**Files:**
- Modify: `.claude/rules/architecture.md`
- Modify: `.claude/rules/commands.md`

- [ ] **Step 1: `.claude/rules/architecture.md`** — add a section after the frontier-expansion block:

```markdown
**Semantic-trajectory generation is two-phase** (see
`docs/superpowers/specs/2026-07-07-semantic-trajectory-two-phase-design.md`).
Phase 1 (the frontier loop above) additionally runs a `NodeDigester`
(`digest.py`, role `node_digester`) once per node: it distills the page into
entities/facts, each carrying quoted `evidence` that code (not the LLM) checks
is a literal substring of the axtree (`grounded: true/false`); the node's
axtree is persisted to `node_state/node_XXXX_axtree.txt` and the accumulated
`sitekb.json` (SiteKB: digests + skills) is dumped after every node. Phase 2
(`run_webarena.py --phase generate|all`; default `explore` keeps the old
behavior) reads the SiteKB: `composer.py` (role `task_composer`) samples
context bundles and generates WebArena-style tasks with eval specs
(`string_match`/`url_match`/`program_html`), code-gated so INFO reference
answers must be backed by grounded refs, NAV targets must be known URLs, and
MOD intents pass a denylist; `collect.py`'s `GenerationRunner` solves each
task (Solver + top-k skill hints), scores it with `evaluator.py`, and records
tag-`GEN` episodes whose meta carries `verified` — INFO/NAV run before the MOD
batch, and the (slow) instance reset runs at most once, after all MODs.
Re-running phase 2 is idempotent (existing `gen_tasks.json` reused, done
task_ids skipped). `build_sft_dataset.py` keeps only verified GEN episodes by
default (`--include-local` opts self-reported LOCAL successes back in), with
`difficulty` = the task's hops.
```

- [ ] **Step 2: `.claude/rules/commands.md`** — extend the WebArena section's command list:

```bash
python run_webarena.py --phase all                   # explore + generate/collect in one run
python run_webarena.py --phase generate --out outputs/wa_run_02   # phase 2 on an existing run
python build_sft_dataset.py outputs/wa_run_02 train.jsonl          # verified GEN episodes only
python build_sft_dataset.py outputs/wa_run_02 train.jsonl --include-local
```

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/architecture.md .claude/rules/commands.md
git commit -m "Document two-phase semantic-trajectory pipeline in rules"
```

---

## Execution notes

- Tasks 1→2→3 and 4→5→6→7 are sequential chains; Task 4 does not depend on Task 3 (only on Task 2), so 3 and 4 could swap, but keep the listed order for simplicity. Task 8 depends on Tasks 1 and 7 (dry-run smoke). Task 9 is last.
- Real-run validation (not part of this plan's gates, needs the LAN instance the sandbox can't reach — ask the user to run): `python run_webarena.py --phase all --max-nodes 10 --read-only` against reddit, then inspect `sitekb.json` grounding rates and `gen_tasks.json` rejection reasons before a full collection run.
