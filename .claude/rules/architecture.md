# Architecture

Two-level graph: **low level** = concrete page states + trajectory edges (flat
exploration graph); **high level** = abstract skills (options ⟨I, π, β⟩) wired to
states by initiation/effect edges plus `skill→skill` composition edges. Planning
runs as graph search over the high level toward a terminal predicate.

**Discovery pipeline** (the core data flow) — each stage is one module in `hsge/`:

```
exploration loop (env.py)
  → segmentation.py    URL-boundary + LLM trajectory segmentation → SubTrajectories
  → clustering.py      streaming nonparametric clusterer (cosine-threshold / DP-means)
  → abstraction.py     lift a cluster → parameterized SkillCard
  → verification.py    ground + execute + admit iff ≥k successes in held-out contexts
  → library.py         SkillLibrary: observe→cluster→abstract→verify→admit, retrieval, pruning
  → graph.py           HierarchicalGraph: skill nodes + skill→skill edges
     → curriculum.py   compose skills into easy→hard tasks
     → transfer.py     retrieve → re-ground → verify a skill on a new site
```

`discovery.py` (`Discovery.on_trajectory(...)`) is the **online hook** that drives
the pipeline above from inside any exploration loop. `operators.py` models skills as
precondition/effect operators with a BFS planner; `operator_induction.py` +
`predicate_registry.py` supply those preconditions/effects for the WebArena path as
LLM-authored, embedding-canonicalized NL predicates instead of a fixed vocabulary.
`schema.py` defines the shared data types (`Step`, `SubTrajectory`, `SkillCard`,
`ParamSlot`, `Task`).

**Backends are the seam for going real** — everything else is backend-agnostic:
- `llm.py` — `LLM.complete_json` (segmentation/abstraction/grounding) and
  `Embedder.encode` (clustering). Mocks: `MockLLM`, `HashingEmbedder`.
- `env.py` — `WebEnv` with `reset()` / `step(action)` / `check(predicate)`; the
  pipeline needs nothing more. Mock: `demo_sites()`.
- `backends.py` — real implementations: `OpenAILLM` (OpenAI-compatible) + `STEmbedder`.

**Baselines** for comparison: `flat_baseline.py`, `awm_baseline.py`.

### WebArena runtime (`hsge/webarena/`)

Standalone real-browser runtime, separate from the mock pipeline:
- `browser.py` — `WebArenaBrowser`, a BrowserGym `openended` wrapper.
- `predicates.py` — URL/DOM → terminal-goal checkers (`reached`), used only to score
  episode success. Planning predicates are no longer hardcoded here (see below).
- `agents.py` — `PageExplorer` (proposes tasks) + `Solver` (action-planner loop).
- `runtime.py` — `WebArenaExplorer`: frontier loop, skill→operator promotion, goal
  tasks, persistence.

**Operators are derived from verified skills, not raw trajectories.** When Discovery
admits a skill (a cluster that recurred `--maturity` times), `runtime.py`
(`_promote_skill_to_operator`) turns it into a planning `Operator`:
`operator_induction.py` asks the LLM for the skill's NL preconditions/effects (from its
SkillCard + boundary axtrees of a few members), and `predicate_registry.py`
canonicalizes those free-form NL predicates into stable ids via the same
cosine-threshold clusterer as the skill library — so the BFS planner in `operators.py`
keeps its unchanged precondition/effect set logic. An operator is terminal iff a member
actually reached the goal state (via `reached`) or the inducer flagged it.

Verification here is by **terminal outcome** (did the episode reach the goal state,
e.g. `checkout/onepage/success`), not the mock's held-out-context execution gate.
Run a single worker — WebArena sites are shared mutable state; reset between runs.
