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
- `browser.py` — `WebArenaBrowser`, a BrowserGym `openended` wrapper. Actions are
  executed via a `HighLevelActionSet` (`action_mapping=to_python_code`), so the
  Solver's `click('bid')`/`fill(...)`/`goto(...)`/`go_back()` strings run for real.
  Surfaces `self.terminated` (env `term`/`trunc`) so the Solver can stop cleanly.
- `predicates.py` — URL/DOM → terminal-goal checkers (`reached`), used only to score
  episode success; `configure_terminal(url_re, text=None)` overrides the default
  shopping success-URL for non-default instances. Planning predicates are no longer
  hardcoded here (see below).
- `agents.py` — `PageExplorer` (proposes `[INFO]/[NAV]/[MOD]`-tagged, specific tasks;
  `read_only=True` drops `[MOD]`) + `Solver` (action-planner loop with action-space
  docs, CoT examples, and last-action-error feedback so it can recover instead of
  aborting the episode).
- `runtime.py` — `WebArenaExplorer`: frontier loop, skill→operator promotion, goal
  tasks, persistence.

**Operators are derived from verified skills, not raw trajectories.** When Discovery
admits a skill (a cluster that recurred `--maturity` times), `runtime.py`
(`_promote_skill_to_operator`) turns it into a planning `Operator`:
`operator_induction.py` asks the LLM for the skill's NL preconditions/effects (from its
SkillCard + boundary axtrees of a few members), and `predicate_registry.py`
canonicalizes those free-form NL predicates into stable ids via the same
cosine-threshold clusterer as the skill library (`predicate_sim` threshold, merging
disabled so ids stay stable once assigned) — so the BFS planner in `operators.py`
keeps its unchanged precondition/effect set logic. An operator is terminal iff a member
actually reached the goal state (via `reached`) or the inducer flagged it.

**`terminal_goal` is site-aware, not hardcoded.** It may be `None` (e.g. a
non-shopping site like reddit): the run is then exploration-only — skills/operators
are still discovered, but `_goal_task` returns `None` and no goal-conditioned episode
is attempted. `run_webarena.py` resolves it as: `config.run.terminal_goal` explicit >
`"order_confirmed"` auto (when `site == shopping` or `--success-url-re` is set) >
`None`.

**Frontier expansion** does not rely on `browser.links()` (BrowserGym's
`open_pages_urls`, which is only open tabs) as its main source — it accumulates every
URL the agent actually loads while solving a task (each `Step.url` + the final
observation), plus open tabs, and admits the allow/deny-filtered ones as frontier
candidates bounded by `max_depth`. This is what lets a real run explore beyond the
root page.

**`--read-only`** makes `PageExplorer` propose only `[INFO]`/`[NAV]` tasks (never
`[MOD]`), for smoke-testing a shared, stateful site without writing to it (no posting,
voting, cart/checkout actions).

**Each LLM-backed helper can use a different model**, configured per role in
`config.yaml`'s `llm.agents.<role>` (see `AGENT_ROLES` in `run_webarena.py`):
`page_explorer`, `solver`, `trajectory_segmenter`, `skill_abstractor`,
`skill_verifier`, `operator_inducer`. A role inherits any field (`provider`/`model`/
`base_url`/`temperature`) it doesn't override from the shared `llm.*` block, which in
turn falls back to `${PROVIDER}_*` env vars. `run_webarena.py::_resolve_agent_llms`
builds one `OpenAILLM` per role and `WebArenaExplorer(agent_llms=...)` routes each to
its component (`self.explorer`, `self.solver`, `self.library.abstraction_llm` /
`.verification_llm`, `self.discovery.segmentation_llm`, `self.operator_llm`). A
**global CLI flag** (`--provider`/`--model`/`--base-url`) overrides every role at
once; there's no per-role CLI override, only `config.yaml`. This lets you route
cheap/fast local tasks to a cheaper model and reserve a stronger one for the
solver or operator induction. See `hsge/tests/test_multi_llm.py` for the exact
precedence/wiring contract.

Verification here is by **terminal outcome** (did the episode reach the goal state,
e.g. `checkout/onepage/success`), not the mock's held-out-context execution gate.
Run a single worker — WebArena sites are shared mutable state; reset between runs.
