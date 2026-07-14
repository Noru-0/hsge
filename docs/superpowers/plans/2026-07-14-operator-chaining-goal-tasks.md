# Operator Chaining + Depth-Gated Goal Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make operators actually chain (vocabulary-aware predicate induction + anti-tautology gate) and generate goal tasks from the operator graph's own depth (all chains ≥ 2, attempted once each) with `terminal_goal` demoted to a two-level backup.

**Architecture:** Five code tasks in dependency order, one integration task. Task 1 gives `PredicateRegistry` usage counts and a `vocabulary()` selector; Task 2 threads a `known_predicates` list through `induce_operator`'s prompt; Task 3 adds bounded `all_chains()` enumeration to `OperatorGraph`; Task 4 rewires `runtime._promote_skill_to_operator` (vocabulary pass-through, `eff - pre` tautology gate, `_op_meta` recording); Task 5 rewrites `runtime._goal_task()` to return a list of depth-based tasks (terminal backup preserved) and updates the GOAL block + config/CLI; Task 6 is docs, changelog, and end-to-end verification.

**Tech Stack:** Python 3.10+, no new dependencies. Tests follow the repo's standalone-or-pytest pattern.

**Spec:** `docs/superpowers/specs/2026-07-14-operator-chaining-goal-tasks-design.md`

## Global Constraints

- Run everything from the repo root; activate the conda env first: `conda activate go-browse`.
- All code/comments/commit messages in English.
- Commit after each task; end commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` (exact trailer).
- Mock pipeline stays deterministic; the full suite (`python -m pytest hsge/tests/ -q`, currently 113 tests) must be green at the end of every task.
- Per repo convention (`.claude/rules/memory.md`), append a `.claude/memory/changelog.md` entry as part of finishing each task (real timestamp via `date "+%Y-%m-%d %H:%M"`).
- `config.yaml` contains the user's live run configuration — only ADD the new `goal_chains_per_node` key (Task 5); never modify or revert any existing line.
- Config precedence everywhere: CLI flag > config.yaml > built-in default.
- The grounding check (`verify_operator_grounding`) stays observation-only — it must NOT become a promotion gate in this plan.
- The legacy terminal-goal path keeps its exact existing behavior when used as backup: attempted at every node (not once-per-run), hardcoded "Purchase an item…" wording, `goal_predicate=terminal_goal`.
- `--dry-run` must still complete with a successful GOAL episode (its scripted operators have empty preconditions → no chain edges → the backup terminal path fires, same as today).

---

### Task 1: `PredicateRegistry` — usage counts + `vocabulary()` selector

**Files:**
- Modify: `hsge/predicate_registry.py`
- Test: Create `hsge/tests/test_predicate_registry.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `PredicateRegistry.counts: dict[int, int]` (canonical cluster id → number of times `canonical()` resolved to it); `PredicateRegistry.vocabulary(max_frequent: int = 25, max_recent: int = 25) -> list[str]` — labels of the most-used ids (count desc, id asc tiebreak) followed by the most recent ids (id desc) not already selected, deduplicated, at most `max_frequent + max_recent` entries. Task 4 calls `self.registry.vocabulary()`.

- [ ] **Step 1: Write the failing tests**

Create `hsge/tests/test_predicate_registry.py`:

```python
"""PredicateRegistry usage counts + vocabulary() selection (frequent + recent
mix, so the induction prompt keeps both the core vocabulary and new concepts).

Run:  python -m pytest hsge/tests/test_predicate_registry.py -q
 (or) PYTHONPATH=. python hsge/tests/test_predicate_registry.py
"""
from hsge.llm import HashingEmbedder
from hsge.predicate_registry import PredicateRegistry


def _registry():
    return PredicateRegistry(HashingEmbedder(), sim_threshold=0.99)


def test_counts_increment_per_canonical_call():
    reg = _registry()
    reg.canonical("the cart is empty")
    reg.canonical("the cart is empty")          # same text -> same cluster
    reg.canonical("search results are shown")

    assert reg.counts[0] == 2
    assert reg.counts[1] == 1


def test_vocabulary_orders_frequent_first_then_recent():
    reg = _registry()
    reg.canonical("alpha predicate")            # p0, used 3x
    reg.canonical("alpha predicate")
    reg.canonical("alpha predicate")
    reg.canonical("beta predicate")             # p1, used 1x
    reg.canonical("gamma predicate")            # p2, used 1x (most recent)

    vocab = reg.vocabulary(max_frequent=1, max_recent=1)

    assert vocab == ["alpha predicate", "gamma predicate"]


def test_vocabulary_dedupes_when_frequent_is_also_recent():
    reg = _registry()
    reg.canonical("only predicate")
    reg.canonical("only predicate")

    vocab = reg.vocabulary(max_frequent=25, max_recent=25)

    assert vocab == ["only predicate"]


def test_vocabulary_caps_total_size():
    reg = _registry()
    for i in range(10):
        reg.canonical(f"predicate number {i} entirely unique wording {i}")

    vocab = reg.vocabulary(max_frequent=3, max_recent=3)

    assert len(vocab) == 6


def test_vocabulary_empty_registry_returns_empty_list():
    assert _registry().vocabulary() == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
```

Note on `test_counts_increment_per_canonical_call`: `sim_threshold=0.99` makes the
HashingEmbedder treat only *identical* token bags as the same cluster, so the id
assignment in these tests is deterministic (first distinct text → cluster 0, next → 1, …).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_predicate_registry.py -q`
Expected: FAIL — `AttributeError: 'PredicateRegistry' object has no attribute 'counts'` / no attribute `vocabulary`.

- [ ] **Step 3: Implement**

In `hsge/predicate_registry.py`, replace the `__init__` and `canonical` bodies and add `vocabulary`:

```python
class PredicateRegistry:
    def __init__(self, embedder: Embedder, sim_threshold: float = 0.6):
        self.embedder = embedder
        # merge_threshold > 1 disables online merging: canonical ids are append-only
        # and never reassigned, so ids already baked into operators stay valid.
        self.clusterer = OnlineClusterer(sim_threshold=sim_threshold, merge_threshold=2.0)
        self.labels: dict[int, str] = {}     # canonical cluster id -> representative NL
        self.counts: dict[int, int] = {}     # canonical cluster id -> times resolved

    def canonical(self, nl: str) -> str:
        """Map one NL predicate to a stable canonical id like 'p3'.

        Close predicates (cosine >= sim_threshold) collapse onto the same id; the
        first NL seen for a cluster is kept as its human-readable label. Usage is
        counted so vocabulary() can surface the most-shared predicates.
        """
        text = (nl or "").strip()
        vec = self.embedder.encode([text])[0]
        cid = self.clusterer.partial_fit(vec, text)
        self.labels.setdefault(cid, text)
        self.counts[cid] = self.counts.get(cid, 0) + 1
        return f"p{cid}"

    def vocabulary(self, max_frequent: int = 25, max_recent: int = 25) -> list[str]:
        """Labels for LLM prompt context: the most-used predicates first (the
        core vocabulary foundational operators share), then the most recent
        (new concepts), deduplicated. Recent-only selection would "forget"
        foundational predicates once the vocabulary outgrows the cap."""
        by_freq = sorted(self.counts, key=lambda cid: (-self.counts[cid], cid))
        chosen = by_freq[:max_frequent]
        chosen_set = set(chosen)
        by_recent = sorted(self.counts, reverse=True)
        for cid in by_recent:
            if len(chosen) >= max_frequent + max_recent:
                break
            if cid not in chosen_set:
                chosen.append(cid)
                chosen_set.add(cid)
        return [self.labels[cid] for cid in chosen]
```

(`label()` is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest hsge/tests/test_predicate_registry.py -q`
Expected: 5 passed.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest hsge/tests/ -q`
Expected: all pass (118 total).

- [ ] **Step 6: Commit**

```bash
git add hsge/predicate_registry.py hsge/tests/test_predicate_registry.py
git commit -m "PredicateRegistry: usage counts + frequent/recent vocabulary() selector

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Vocabulary-aware `induce_operator`

**Files:**
- Modify: `hsge/operator_induction.py` (`_SYS`, `induce_operator`)
- Test: Create `hsge/tests/test_operator_induction.py`

**Interfaces:**
- Consumes: nothing from Task 1 directly (the caller wires them together in Task 4).
- Produces: `induce_operator(llm, card, boundary_obs, known_predicates: list[str] | None = None) -> dict` — when `known_predicates` is a non-empty list, the payload JSON gains a `"known_predicates"` key with exactly that list; when `None` or empty, the key is absent (old payload shape preserved).

- [ ] **Step 1: Write the failing tests**

Create `hsge/tests/test_operator_induction.py`:

```python
"""induce_operator: vocabulary-aware prompting. The LLM must see the existing
predicate vocabulary and be told to reuse matching phrases verbatim, so
canonicalization happens at the source instead of relying on embedding
similarity alone (measured on wa_run_09: the true synonym pair scored 0.570,
below the 0.6 threshold, while a false pair scored 0.606 -- no threshold works).

Run:  python -m pytest hsge/tests/test_operator_induction.py -q
 (or) PYTHONPATH=. python hsge/tests/test_operator_induction.py
"""
import json

from hsge.operator_induction import _SYS, induce_operator
from hsge.schema import SkillCard


class _CapturingLLM:
    def __init__(self):
        self.system = None
        self.prompt = None

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.system = system
        self.prompt = prompt
        return {"preconditions": ["a"], "effects": ["b"], "terminal": False}


def _card():
    return SkillCard(name="AddToCart", description="add an item to the cart",
                     slots=[], action_template=["click {add_button}"],
                     precondition="item page is open",
                     success_predicate="cart count increased", cluster_id="c0")


def _payload(llm):
    return json.loads(llm.prompt.split("<payload>", 1)[1].rsplit("</payload>", 1)[0])


def test_known_predicates_included_in_payload():
    llm = _CapturingLLM()

    induce_operator(llm, _card(), [("before", "after")],
                    known_predicates=["the user is logged in", "an item is in the cart"])

    payload = _payload(llm)
    assert payload["known_predicates"] == [
        "the user is logged in", "an item is in the cart"]


def test_payload_shape_unchanged_without_known_predicates():
    llm = _CapturingLLM()

    induce_operator(llm, _card(), [("before", "after")])

    payload = _payload(llm)
    assert "known_predicates" not in payload
    assert set(payload) == {"skill", "boundary_states"}


def test_empty_known_predicates_omitted():
    llm = _CapturingLLM()

    induce_operator(llm, _card(), [("before", "after")], known_predicates=[])

    assert "known_predicates" not in _payload(llm)


def test_system_prompt_mandates_verbatim_reuse():
    assert "verbatim" in _SYS
    assert "known predicate" in _SYS.lower()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_operator_induction.py -q`
Expected: FAIL — `TypeError: induce_operator() got an unexpected keyword argument 'known_predicates'` and the `_SYS` content assertion.

- [ ] **Step 3: Implement**

In `hsge/operator_induction.py`, replace `_SYS`:

```python
_SYS = (
    "You convert a reusable web skill into a PLANNING OPERATOR. Given the skill "
    "and the page state before/after it ran on a few sites, state the world "
    "conditions in short, site-agnostic natural language. Preconditions = what "
    "must already be true to apply the skill; effects = what becomes true after. "
    "Keep each predicate a terse phrase (e.g. 'search results are shown', 'an "
    "item is in the cart'). Mark terminal=true only if an effect is a final/"
    "transactional state (order placed, purchase confirmed). "
    "A list of KNOWN predicates from previously induced operators may be "
    "provided. If a precondition or effect you want to state is semantically "
    "equivalent to a known predicate, you MUST reuse that predicate's exact "
    "text verbatim instead of rephrasing it. Only coin a new phrase when no "
    "known predicate matches. "
    'Return JSON {"preconditions": ["..."], "effects": ["..."], "terminal": bool}.'
)
```

Replace `induce_operator`:

```python
def induce_operator(
    llm: LLM,
    card: SkillCard,
    boundary_obs: list[tuple[str, str]],
    known_predicates: list[str] | None = None,
) -> dict:
    """Return {"preconditions": [NL...], "effects": [NL...], "terminal": bool}.

    `boundary_obs` is a list of (start_axtree, end_axtree) pairs from a few
    members of the skill's cluster; only a couple are needed for context.
    `known_predicates` is the registry's existing vocabulary (see
    PredicateRegistry.vocabulary()) -- shown to the LLM so equivalent
    predicates are reused verbatim instead of re-coined, which is what lets
    operators share canonical ids and chain.
    """
    examples = [
        {"before": (start or "")[:_AXTREE_CAP], "after": (end or "")[:_AXTREE_CAP]}
        for start, end in boundary_obs[:2]
    ]
    payload = {
        "skill": {
            "name": card.name,
            "description": card.description,
            "action_template": card.action_template,
        },
        "boundary_states": examples,
    }
    if known_predicates:
        payload["known_predicates"] = list(known_predicates)
    out = llm.complete_json(_SYS, f"<payload>{json.dumps(payload)}</payload>")
    return {
        "preconditions": [p for p in out.get("preconditions", []) if p],
        "effects": [e for e in out.get("effects", []) if e],
        "terminal": bool(out.get("terminal", False)),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest hsge/tests/test_operator_induction.py -q`
Expected: 4 passed.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest hsge/tests/ -q`
Expected: all pass (the dry run's `MockLLM` ignores the new prompt text; `test_operator_grounding.py` is untouched).

- [ ] **Step 6: Commit**

```bash
git add hsge/operator_induction.py hsge/tests/test_operator_induction.py
git commit -m "induce_operator: vocabulary-aware prompting (reuse known predicates verbatim)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `OperatorGraph.all_chains` with circuit breakers

**Files:**
- Modify: `hsge/operators.py` (add method to `OperatorGraph`)
- Test: Create `hsge/tests/test_operators.py`

**Interfaces:**
- Consumes: existing `OperatorGraph.edges()` (`A -> B iff a.effects & b.preconditions`).
- Produces: `OperatorGraph.all_chains(min_len: int = 2, max_len: int = 6, max_paths: int = 200) -> list[list[str]]` — deterministic (sorted starts/successors), cycle-safe, includes sub-chains (a 3-op path also yields its 2-op prefix as a separate chain). Task 5 consumes this.

- [ ] **Step 1: Write the failing tests**

Create `hsge/tests/test_operators.py`:

```python
"""OperatorGraph.all_chains: bounded enumeration of composable operator
chains over effect->precondition edges. min_len gates shallow graphs,
max_len/max_paths are circuit breakers for densely connected graphs
(unbounded simple-path enumeration is O(V!) in the worst case).

Run:  python -m pytest hsge/tests/test_operators.py -q
 (or) PYTHONPATH=. python hsge/tests/test_operators.py
"""
from hsge.operators import Operator, OperatorGraph


def _graph(*ops):
    g = OperatorGraph()
    for op in ops:
        g.add(op)
    return g


def test_linear_chain_enumerated_with_prefixes():
    g = _graph(
        Operator("search", frozenset(), frozenset({"results"})),
        Operator("open_item", frozenset({"results"}), frozenset({"item_open"})),
        Operator("add_cart", frozenset({"item_open"}), frozenset({"in_cart"})),
    )

    chains = g.all_chains(min_len=2)

    assert ["search", "open_item"] in chains
    assert ["open_item", "add_cart"] in chains
    assert ["search", "open_item", "add_cart"] in chains


def test_min_len_excludes_single_operators():
    g = _graph(
        Operator("a", frozenset(), frozenset({"x"})),
        Operator("b", frozenset({"x"}), frozenset({"y"})),
    )

    assert all(len(c) >= 2 for c in g.all_chains(min_len=2))


def test_disconnected_graph_yields_no_chains():
    g = _graph(
        Operator("a", frozenset({"p"}), frozenset({"q"})),
        Operator("b", frozenset({"r"}), frozenset({"s"})),
    )

    assert g.all_chains(min_len=2) == []


def test_cycle_is_safe_and_terminates():
    g = _graph(
        Operator("a", frozenset({"y"}), frozenset({"x"})),
        Operator("b", frozenset({"x"}), frozenset({"y"})),
    )

    chains = g.all_chains(min_len=2)

    assert ["a", "b"] in chains and ["b", "a"] in chains
    assert all(len(set(c)) == len(c) for c in chains)   # simple paths only


def test_max_len_stops_descent():
    ops = [Operator(f"op{i}", frozenset({f"p{i}"}) if i else frozenset(),
                    frozenset({f"p{i+1}"})) for i in range(8)]
    g = _graph(*ops)

    chains = g.all_chains(min_len=2, max_len=3)

    assert max(len(c) for c in chains) == 3


def test_max_paths_bounds_result_count():
    ops = [Operator(f"op{i}", frozenset({f"p{i}"}) if i else frozenset(),
                    frozenset({f"p{i+1}"})) for i in range(8)]
    g = _graph(*ops)

    assert len(g.all_chains(min_len=2, max_paths=3)) == 3


def test_deterministic_ordering():
    g = _graph(
        Operator("z_first", frozenset(), frozenset({"m"})),
        Operator("a_second", frozenset({"m"}), frozenset({"n"})),
    )

    assert g.all_chains(min_len=2) == g.all_chains(min_len=2)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_operators.py -q`
Expected: FAIL — `AttributeError: 'OperatorGraph' object has no attribute 'all_chains'`.

- [ ] **Step 3: Implement**

In `hsge/operators.py`, add to `OperatorGraph` (after `successors`):

```python
    def all_chains(self, min_len: int = 2, max_len: int = 6,
                   max_paths: int = 200) -> list[list[str]]:
        """Simple paths of min_len..max_len operators over effect->precondition
        edges (A -> B iff effects(A) & preconditions(B)). DFS with a per-path
        visited check (cycle-safe), deterministic (sorted starts/successors).
        max_len and max_paths are circuit breakers: today's graphs are tiny
        (tens of operators), but once predicates unify the graph becomes
        densely connected and unbounded simple-path enumeration is O(V!) in
        the worst case -- DFS stops descending at max_len and returns as soon
        as max_paths chains are collected. Sub-chains are emitted too (a
        3-op path also yields its 2-op prefix): each is a distinct, shorter
        task variation.
        """
        succ: dict[str, set[str]] = {name: set() for name in self.ops}
        for a, b in self.edges():
            succ[a].add(b)
        chains: list[list[str]] = []

        def dfs(path: list[str]) -> bool:
            """Extend `path`; return True when max_paths is exhausted."""
            if len(path) >= min_len:
                chains.append(list(path))
                if len(chains) >= max_paths:
                    return True
            if len(path) >= max_len:
                return False
            for nxt in sorted(succ[path[-1]]):
                if nxt in path:
                    continue
                if dfs(path + [nxt]):
                    return True
            return False

        for start in sorted(self.ops):
            if dfs([start]):
                break
        return chains
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest hsge/tests/test_operators.py -q`
Expected: 7 passed.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest hsge/tests/ -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add hsge/operators.py hsge/tests/test_operators.py
git commit -m "OperatorGraph.all_chains: bounded, cycle-safe chain enumeration

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Promotion — vocabulary pass-through, tautology gate, `_op_meta`

**Files:**
- Modify: `hsge/webarena/runtime.py` (`__init__`, `_promote_skill_to_operator`)
- Test: Create `hsge/tests/test_operator_promotion.py`

**Interfaces:**
- Consumes: `self.registry.vocabulary()` (Task 1), `induce_operator(..., known_predicates=...)` (Task 2).
- Produces: `self._op_meta: dict[str, dict]` on `WebArenaExplorer` — op name → `{"card_name": str, "description": str, "init_url": str}`, recorded at promotion; `operator_rejected` log event (`skill_id`, `name`, `reason` ∈ {"tautological", "no_effects"}, `preconditions`, `effects_dropped`); `operator_induced` event gains `effects_dropped: list[str]`. Task 5 reads `self._op_meta`.

- [ ] **Step 1: Write the failing tests**

Create `hsge/tests/test_operator_promotion.py`:

```python
"""_promote_skill_to_operator: vocabulary-aware induction wiring, the
eff - pre anti-tautology gate, and _op_meta recording for goal-task
instruction generation.

Run:  python -m pytest hsge/tests/test_operator_promotion.py -q
 (or) PYTHONPATH=. python hsge/tests/test_operator_promotion.py
"""
import json
import os
import tempfile

from hsge.llm import HashingEmbedder, MockLLM
from hsge.schema import SkillCard, Step, SubTrajectory
from hsge.webarena.runtime import WebArenaExplorer


class _ScriptedInducerLLM:
    """Answers induce_operator with a scripted result and grounding with
    empty results; captures the induction payload for assertions."""

    def __init__(self, preconditions, effects, terminal=False):
        self._induced = {"preconditions": preconditions, "effects": effects,
                         "terminal": terminal}
        self.induce_payload = None

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        if "PLANNING OPERATOR" in system:
            self.induce_payload = json.loads(
                prompt.split("<payload>", 1)[1].rsplit("</payload>", 1)[0])
            return dict(self._induced)
        return {"results": []}     # grounding check: nothing confirmed


def _explorer(llm, terminal_goal=None):
    ex = WebArenaExplorer(
        browser_factory=lambda url: None, llm=MockLLM(),
        embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
        allow_pattern=".*", terminal_goal=terminal_goal)
    ex.operator_llm = llm
    return ex


def _install_skill(ex, name="AddToCart", description="add an item to the cart",
                   init_url="http://shop/item.html"):
    steps = [Step(action="click('1')", url=init_url, axtree="before ax"),
             Step(action="click('2')", url="http://shop/cart", axtree="after ax")]
    sub = SubTrajectory(steps=steps, subgoal=name, source_site="shop")
    card = SkillCard(name=name, description=description, slots=[],
                     action_template=["click {btn}"], precondition="",
                     success_predicate="", cluster_id=0, member_ids=[sub.sub_id])
    ex.library.skills[0] = card
    ex.library.subtrajs[sub.sub_id] = sub
    return card


def _log_events(ex):
    path = os.path.join(ex.out_dir, "run_log.jsonl")
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path)]


def test_promotion_passes_registry_vocabulary_to_inducer():
    llm = _ScriptedInducerLLM(["the item page is open"], ["an item is in the cart"])
    ex = _explorer(llm)
    ex.registry.canonical("the user is logged in")     # pre-existing vocabulary
    card = _install_skill(ex)

    ex._promote_skill_to_operator(card.skill_id)

    assert llm.induce_payload["known_predicates"] == ["the user is logged in"]


def test_tautological_operator_is_rejected_and_logged():
    llm = _ScriptedInducerLLM(["a page with history is open"],
                              ["a page with history is open"])
    ex = _explorer(llm)
    card = _install_skill(ex, name="NavHistory")

    ex._promote_skill_to_operator(card.skill_id)

    assert ex.opgraph.ops == {}
    rejected = [e for e in _log_events(ex) if e["event"] == "operator_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "tautological"
    assert rejected[0]["effects_dropped"]              # names the dropped ids


def test_mixed_effects_keep_novel_subset_and_log_dropped():
    llm = _ScriptedInducerLLM(
        ["a comment is displayed entirely unique alpha"],
        ["a comment is displayed entirely unique alpha",
         "a reply is posted entirely unique beta"])
    ex = _explorer(llm)
    card = _install_skill(ex, name="ReplyToComment")

    ex._promote_skill_to_operator(card.skill_id)

    op = ex.opgraph.ops["replytocomment"]
    assert len(op.effects) == 1                        # tautological one dropped
    assert not (op.effects & op.preconditions)
    induced = [e for e in _log_events(ex) if e["event"] == "operator_induced"]
    assert induced[0]["effects_dropped"]


def test_empty_effects_rejected_with_no_effects_reason():
    llm = _ScriptedInducerLLM(["something must hold"], [])
    ex = _explorer(llm)
    card = _install_skill(ex)

    ex._promote_skill_to_operator(card.skill_id)

    assert ex.opgraph.ops == {}
    rejected = [e for e in _log_events(ex) if e["event"] == "operator_rejected"]
    assert rejected[0]["reason"] == "no_effects"


def test_op_meta_recorded_on_promotion():
    llm = _ScriptedInducerLLM(["the item page is open unique gamma"],
                              ["an item is in the cart unique delta"])
    ex = _explorer(llm)
    card = _install_skill(ex, name="AddToCart",
                          description="add an item to the cart",
                          init_url="http://shop/item.html")

    ex._promote_skill_to_operator(card.skill_id)

    meta = ex._op_meta["addtocart"]
    assert meta["card_name"] == "AddToCart"
    assert meta["description"] == "add an item to the cart"
    assert meta["init_url"] == "http://shop/item.html"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
```

Note: the "entirely unique alpha/beta/gamma/delta" phrasings keep HashingEmbedder
token-bags disjoint so the default 0.6 threshold never accidentally merges the
test predicates.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_operator_promotion.py -q`
Expected: FAIL — payload lacks `known_predicates`; tautological op is still promoted; `_op_meta` missing.

- [ ] **Step 3: Implement**

In `hsge/webarena/runtime.py`:

3a. `__init__` — after `self.operator_grounding: dict[str, dict] = {}`, add:

```python
        # op name -> {"card_name", "description", "init_url"}: recorded at
        # promotion, consumed by _goal_task to generate chain instructions.
        self._op_meta: dict[str, dict] = {}
```

3b. In `_promote_skill_to_operator`, replace the block from `induced = induce_operator(...)` through `self.opgraph.add(op)` with:

```python
        induced = induce_operator(self.operator_llm, card, boundary,
                                  known_predicates=self.registry.vocabulary())
        pre = frozenset(self.registry.canonical(p) for p in induced["preconditions"])
        eff_all = frozenset(self.registry.canonical(e) for e in induced["effects"])
        # Anti-tautology gate: an "effect" that restates a precondition encodes
        # no state change (typical for INFO skills that read state rather than
        # change it) -- wa_run_09 had 3/4 operators with effects == preconditions,
        # which can never chain toward anything new.
        eff = eff_all - pre
        effects_dropped = sorted(eff_all & pre)
        if not eff:
            reason = "tautological" if eff_all else "no_effects"
            print(f"    [operator] rejected {_slug(card.name)}: {reason}")
            self._log("operator_rejected", skill_id=skill_id, name=_slug(card.name),
                       reason=reason, preconditions=sorted(pre),
                       effects_dropped=effects_dropped)
            return
        # terminal only when a real terminal goal is configured and a member reached it
        reached_terminal = bool(self.terminal_goal) and any(
            reached(self.terminal_goal, m.steps[-1].url, m.steps[-1].axtree) for m in members)
        op = Operator(_slug(card.name), pre, eff, terminal=induced["terminal"] or reached_terminal)
        self.opgraph.add(op)
        self._op_meta[op.name] = {
            "card_name": card.name,
            "description": card.description or card.name,
            "init_url": members[0].steps[0].url if members else "",
        }
```

3c. Extend the `operator_induced` log call with the new field (same call, one added kwarg):

```python
        self._log("operator_induced", name=op.name, skill_id=skill_id,
                   preconditions=sorted(op.preconditions), effects=sorted(op.effects),
                   effects_dropped=effects_dropped, terminal=op.terminal)
```

(the print line and the grounding-check block below it are unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest hsge/tests/test_operator_promotion.py -q`
Expected: 5 passed.

- [ ] **Step 5: Run the full suite and the dry run**

Run: `python -m pytest hsge/tests/ -q` — Expected: all pass.
Run: `python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2` — Expected: completes; the scripted operator (`preconditions=[]`, real effects) still gets promoted and the GOAL episode still verifies (`GOAL chain=... verified=True`).

- [ ] **Step 6: Commit**

```bash
git add hsge/webarena/runtime.py hsge/tests/test_operator_promotion.py
git commit -m "Promotion: vocabulary-aware induction wiring, anti-tautology gate, _op_meta

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `_goal_task()` rewrite — depth primary, terminal backup, config/CLI

**Files:**
- Modify: `hsge/webarena/runtime.py` (`__init__`, `_goal_task`, GOAL block in `run()`)
- Modify: `run_webarena.py` (DEFAULTS, argparse, `main()`)
- Modify: `config.yaml` (add `goal_chains_per_node: 3` under `run:` — touch nothing else)
- Test: Create `hsge/tests/test_goal_task.py`

**Interfaces:**
- Consumes: `OperatorGraph.all_chains(min_len=2)` (Task 3), `self._op_meta` (Task 4).
- Produces: `WebArenaExplorer(..., goal_chains_per_node: int = 3)`; `self._attempted_chains: set[tuple[str, ...]]`; `_goal_task() -> list[dict]`, each dict `{"goal": str, "difficulty": int, "chain": list[str], "kind": "depth"|"terminal", "goal_predicate": str|None}`; log event `goal_task_selected` (`node_index`, `kind`, `chain`, `goal_predicate`); config key `run.goal_chains_per_node`; CLI `--goal-chains-per-node`.

- [ ] **Step 1: Write the failing tests**

Create `hsge/tests/test_goal_task.py`:

```python
"""_goal_task: depth-based chains are the primary goal source on every site
(attempted once per run, capped per node); the legacy terminal-predicate
plan is the backup when the graph is too shallow; reached()-verification
kicks back in exactly when a depth chain ends at a terminal operator.

Run:  python -m pytest hsge/tests/test_goal_task.py -q
 (or) PYTHONPATH=. python hsge/tests/test_goal_task.py
"""
import tempfile

from hsge.llm import HashingEmbedder, MockLLM
from hsge.operators import Operator
from hsge.webarena.runtime import WebArenaExplorer


def _explorer(terminal_goal=None, goal_chains_per_node=3):
    return WebArenaExplorer(
        browser_factory=lambda url: None, llm=MockLLM(),
        embedder=HashingEmbedder(), out_dir=tempfile.mkdtemp(),
        allow_pattern=".*", terminal_goal=terminal_goal,
        goal_chains_per_node=goal_chains_per_node)


def _add_chain_ops(ex, terminal_last=False):
    ex.opgraph.add(Operator("search", frozenset(), frozenset({"results"})))
    ex.opgraph.add(Operator("add_cart", frozenset({"results"}),
                            frozenset({"in_cart"}), terminal=terminal_last))
    ex._op_meta["search"] = {"card_name": "Search", "description": "search for an item",
                             "init_url": "http://shop/home"}
    ex._op_meta["add_cart"] = {"card_name": "AddToCart",
                               "description": "add the item to the cart",
                               "init_url": "http://shop/item.html"}


def test_shallow_graph_and_no_terminal_goal_yields_nothing():
    ex = _explorer(terminal_goal=None)
    ex.opgraph.add(Operator("lonely", frozenset({"p"}), frozenset({"q"})))

    assert ex._goal_task() == []


def test_shallow_graph_with_terminal_goal_falls_back_to_legacy_task():
    ex = _explorer(terminal_goal="order_confirmed")
    ex.opgraph.add(Operator("purchase", frozenset(),
                            frozenset({"confirmed"}), terminal=True))

    tasks = ex._goal_task()

    assert len(tasks) == 1
    assert tasks[0]["kind"] == "terminal"
    assert tasks[0]["goal_predicate"] == "order_confirmed"
    assert tasks[0]["goal"].startswith("Purchase an item")


def test_deep_graph_yields_depth_task_with_generated_instruction():
    ex = _explorer(terminal_goal=None)
    _add_chain_ops(ex)

    tasks = ex._goal_task()

    depth = [t for t in tasks if t["chain"] == ["search", "add_cart"]]
    assert len(depth) == 1
    t = depth[0]
    assert t["kind"] == "depth"
    assert t["goal_predicate"] is None                 # self-graded + judge
    assert t["difficulty"] == 2
    assert "http://shop/home" in t["goal"]             # init URL of first op
    assert "search for an item" in t["goal"]
    assert "add the item to the cart" in t["goal"]
    assert "Purchase an item" not in t["goal"]         # no hardcoded wording


def test_terminal_chain_end_restores_deterministic_verify():
    ex = _explorer(terminal_goal="order_confirmed")
    _add_chain_ops(ex, terminal_last=True)

    tasks = ex._goal_task()

    t = [t for t in tasks if t["chain"] == ["search", "add_cart"]][0]
    assert t["kind"] == "depth"
    assert t["goal_predicate"] == "order_confirmed"    # backup verify kicks in


def test_each_chain_attempted_once_per_run():
    ex = _explorer(terminal_goal=None)
    _add_chain_ops(ex)

    first = ex._goal_task()
    second = ex._goal_task()

    assert first                                       # emitted once...
    assert second == []                                # ...never again


def test_per_node_cap_defers_extra_chains_to_later_nodes():
    ex = _explorer(terminal_goal=None, goal_chains_per_node=1)
    _add_chain_ops(ex)
    # a third operator so the graph holds >1 distinct chain:
    # [search, add_cart], [add_cart, checkout], [search, add_cart, checkout]
    ex.opgraph.add(Operator("checkout", frozenset({"in_cart"}), frozenset({"ordered"})))
    ex._op_meta["checkout"] = {"card_name": "Checkout", "description": "check out",
                               "init_url": "http://shop/cart"}

    first = ex._goal_task()
    second = ex._goal_task()

    assert len(first) == 1
    assert len(second) >= 1                            # deferred, not lost
    assert first[0]["chain"] != second[0]["chain"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest hsge/tests/test_goal_task.py -q`
Expected: FAIL — `TypeError: WebArenaExplorer.__init__() got an unexpected keyword argument 'goal_chains_per_node'`.

- [ ] **Step 3: Implement runtime changes**

3a. `__init__` — signature gains `goal_chains_per_node: int = 3` (after `task_retries: int = 0`); body stores, next to the other run knobs:

```python
        self.goal_chains_per_node = goal_chains_per_node
        # depth-chains already emitted as goal tasks this run (attempt once each;
        # self-graded repeats mostly duplicate data, unlike the deterministic
        # terminal path which stays retryable every node).
        self._attempted_chains: set[tuple[str, ...]] = set()
```

3b. Replace `_goal_task` entirely:

```python
    def _goal_task(self) -> list[dict]:
        """Goal tasks for the current node, 0..N.

        Depth-based chains over the operator graph are the primary source on
        every site: each simple chain of >= 2 operators becomes one composed
        task (attempted once per run, at most goal_chains_per_node new chains
        per node). Verification is self-graded (send_msg_to_user + offline
        judge) unless the chain's last operator is terminal AND a terminal
        goal is configured -- then the deterministic reached() check applies.
        The legacy terminal-predicate plan is the backup when the graph is
        too shallow to chain (< 2 operators) but a terminal goal exists.
        """
        tasks: list[dict] = []
        for chain in self.opgraph.all_chains(min_len=2):
            if len(tasks) >= self.goal_chains_per_node:
                break
            key = tuple(chain)
            if key in self._attempted_chains:
                continue
            self._attempted_chains.add(key)
            steps_txt = " ".join(
                f"{i}) {self._op_meta.get(op, {}).get('description', op)}."
                for i, op in enumerate(chain, 1))
            init_url = self._op_meta.get(chain[0], {}).get("init_url", "")
            prefix = f"Start by navigating to {init_url}. " if init_url else ""
            ends_terminal = self.opgraph.ops[chain[-1]].terminal
            goal_predicate = self.terminal_goal if (ends_terminal and self.terminal_goal) else None
            tasks.append({
                "goal": f"{prefix}Complete these steps in order: {steps_txt}",
                "difficulty": len(chain), "chain": chain,
                "kind": "depth", "goal_predicate": goal_predicate,
            })
        if tasks:
            return tasks
        # Backup: graph too shallow for chains, but a terminal predicate is
        # configured and plannable -> legacy behavior, unchanged (every node,
        # deterministic reached() verify, original wording).
        if not self.terminal_goal:
            return []
        for goal in sorted(self.opgraph.goal_predicates):
            chain = plan(self.opgraph, frozenset(), goal)
            if chain:
                return [{"goal": "Purchase an item: complete the full checkout to order confirmation.",
                         "difficulty": len(chain), "chain": chain,
                         "kind": "terminal", "goal_predicate": self.terminal_goal}]
        return []
```

3c. Replace the GOAL block in `run()` (currently `gt = self._goal_task()` / `if gt:` through the `print(f"    GOAL chain=...")` line) with:

```python
                # 2) goal-conditioned composed tasks (depth chains; terminal backup)
                for gt in self._goal_task():
                    self._log("goal_task_selected", node_index=node_index,
                               kind=gt["kind"], chain=gt["chain"],
                               goal_predicate=gt["goal_predicate"])
                    (episode_id, steps, final_obs, success, infeasible, attempts,
                     urls_seen) = self._solve_with_retries(
                        browser, gt["goal"], difficulty=gt["difficulty"], tag="GOAL",
                        goal_predicate=gt["goal_predicate"])
                    bucket = "success" if success else ("infeasible" if infeasible else "fail")
                    task_stats["GOAL"][bucket] += 1
                    node_rec["tasks"].append({"episode": episode_id, "tag": "GOAL", "task": gt["goal"],
                                               "success": success, "infeasible": infeasible,
                                               "attempts": attempts, "steps": len(steps)})
                    self._log("task_result", node_index=node_index, episode=episode_id, tag="GOAL",
                               task=gt["goal"], success=success, infeasible=infeasible,
                               attempts=attempts, steps=len(steps), chain=gt["chain"])
                    seen_urls |= urls_seen
                    print(f"    GOAL[{gt['kind']}] chain={gt['chain']} verified={success} "
                          f"steps={len(steps)}")
```

- [ ] **Step 4: Wire config/CLI in `run_webarena.py` and `config.yaml`**

In `run_webarena.py`:
- DEFAULTS `run` dict: add `"goal_chains_per_node": 3,` after `"task_retries": 0,`.
- argparse, after `--task-retries`:

```python
    ap.add_argument("--goal-chains-per-node", type=int, default=None,
                    help="max NEW depth-based goal chains attempted per node "
                         "(default 3; each distinct chain is attempted once per run)")
```

- `main()`: add `goal_chains_per_node = _pick(args.goal_chains_per_node, run["goal_chains_per_node"])` beside the other `_pick` lines, and pass `goal_chains_per_node=goal_chains_per_node,` in the `WebArenaExplorer(...)` call.

In `config.yaml`, add after the `task_retries` comment block (do not touch any other line):

```yaml
  goal_chains_per_node: 3    # max NEW depth-based goal chains attempted per node
                             # (each distinct chain runs once per run)
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest hsge/tests/test_goal_task.py -q`
Expected: 6 passed.

- [ ] **Step 6: Run the full suite and the dry run**

Run: `python -m pytest hsge/tests/ -q` — Expected: all pass (`test_run_timing`/`test_frontier_mining`/`test_node_error_resilience` drive `run()` with no operators → `_goal_task()` returns `[]` → GOAL loop is a no-op, same as before).
Run: `python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2` — Expected: completes; output shows `GOAL[terminal] chain=[...] verified=True` (DryLLM operators have empty preconditions → no chain edges → backup path).

- [ ] **Step 7: Commit**

```bash
git add hsge/webarena/runtime.py run_webarena.py config.yaml hsge/tests/test_goal_task.py
git commit -m "Goal tasks: depth-based chains primary, terminal backup, per-node cap

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Integration — docs, changelog, spec status, end-to-end check

**Files:**
- Modify: `.claude/rules/architecture.md` (operator-promotion + terminal_goal + runtime bullets)
- Modify: `docs/superpowers/specs/2026-07-14-operator-chaining-goal-tasks-design.md` (Status line)
- Modify: `.claude/memory/changelog.md`

**Interfaces:**
- Consumes: everything from Tasks 1–5. No new code interfaces — documentation and verification only.

- [ ] **Step 1: Update `.claude/rules/architecture.md`**

1a. In the paragraph starting `**Operators are derived from verified skills, not raw trajectories.**`, after the sentence ending "An operator is terminal iff a member actually reached the goal state (via `reached`) or the inducer flagged it.", append:

```
Induction is vocabulary-aware: the prompt includes the registry's existing
predicate labels (`PredicateRegistry.vocabulary()`, 25 most-frequent + 25
most-recent, deduplicated) with an instruction to reuse an equivalent
predicate's exact text verbatim -- measured on wa_run_09, embedding-only
canonicalization cannot unify synonyms (the true synonym pair scored 0.570,
below the 0.6 threshold, while a false pair scored 0.606). Promotion applies
an anti-tautology gate: effects that restate a precondition are dropped
(`eff - pre`, logged as `effects_dropped` on the `operator_induced` event);
a skill with no novel effects left is rejected (`operator_rejected` event,
reason `tautological`/`no_effects`) instead of becoming an operator.
```

1b. Replace the paragraph starting `**\`terminal_goal\` is site-aware, not hardcoded.**` (keep its heading sentence, rewrite the body) with:

```markdown
**`terminal_goal` is site-aware, not hardcoded.** It may be `None` (e.g. a
non-shopping site like reddit). Goal tasks no longer depend on it: the primary
mechanism on every site is **depth-based chains** -- `OperatorGraph.all_chains`
(bounded DFS over effect->precondition edges, `min_len=2`, circuit-broken at
`max_len=6`/`max_paths=200`) turns each simple chain of >= 2 operators into one
composed GOAL task with an instruction generated from the chained skills'
descriptions plus the first operator's recorded init URL (`_op_meta`). Each
distinct chain is attempted once per run, at most `run.goal_chains_per_node`
(default 3, CLI `--goal-chains-per-node`) new chains per node. Verification is
self-graded (send_msg_to_user + offline judge) unless the chain's last operator
is terminal AND `terminal_goal` is configured -- then `reached()` verifies
deterministically. `terminal_goal` is the backup: when the graph is too shallow
to chain but a terminal predicate is plannable, the legacy terminal task
(original wording, every node, `reached()` verify) still fires.
`run_webarena.py` resolves it as: `config.run.terminal_goal` explicit >
`"order_confirmed"` auto (when `site == shopping` or `--success-url-re` is set) >
`None`.
```

- [ ] **Step 2: Update the spec status line**

In `docs/superpowers/specs/2026-07-14-operator-chaining-goal-tasks-design.md`, change
`**Status:** approved, awaiting implementation plan` to
`**Status:** implemented (see docs/superpowers/plans/2026-07-14-operator-chaining-goal-tasks.md)`.

- [ ] **Step 3: Changelog entry**

Get the timestamp with `date "+%Y-%m-%d %H:%M"`. Add one entry under the current
date heading in `.claude/memory/changelog.md` (create the heading if the date
changed) covering this task's docs updates only if Tasks 1–5 already logged their
own entries; otherwise summarize the whole feature in one entry naming all files
touched across Tasks 1–6.

- [ ] **Step 4: Full-suite + dry-run verification**

Run: `python -m pytest hsge/tests/ -q`
Expected: all pass (113 pre-existing + 5 + 4 + 7 + 5 + 6 = 140 total).
Run: `python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2`
Expected: completes with `GOAL[terminal] chain=[...] verified=True` and the final
`tasks:` line showing GOAL success >= 1.

- [ ] **Step 5: Commit**

```bash
git add .claude/rules/architecture.md .claude/memory/changelog.md \
        docs/superpowers/specs/2026-07-14-operator-chaining-goal-tasks-design.md
git commit -m "Docs: operator chaining + depth-gated goal tasks (architecture, spec status)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
