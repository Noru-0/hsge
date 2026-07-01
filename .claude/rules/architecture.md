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
precondition/effect operators with a BFS planner. `schema.py` defines the shared
data types (`Step`, `SubTrajectory`, `SkillCard`, `ParamSlot`, `Task`).

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
- `predicates.py` — URL/DOM → canonical predicates + terminal-goal checkers.
- `agents.py` — `PageExplorer` (proposes tasks) + `Solver` (action-planner loop).
- `runtime.py` — `WebArenaExplorer`: frontier loop, operator mining, goal tasks, persistence.

Verification here is by **terminal outcome** (did the episode reach the goal state,
e.g. `checkout/onepage/success`), not the mock's held-out-context execution gate.
Run a single worker — WebArena sites are shared mutable state; reset between runs.
