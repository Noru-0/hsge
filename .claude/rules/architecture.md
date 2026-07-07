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
  `OpenAILLM` retries transient API errors (rate limit, connection, timeout, 5xx; not
  auth/bad-request) up to 3x with exponential backoff, and accepts an optional
  `image_b64`/`image_detail` for vision-capable models.

**Baselines** for comparison: `flat_baseline.py`, `awm_baseline.py`.

### WebArena runtime (`hsge/webarena/`)

Standalone real-browser runtime, separate from the mock pipeline:
- `browser.py` — `WebArenaBrowser`, a BrowserGym `openended` wrapper. Actions are
  executed via a `HighLevelActionSet` (`action_mapping=to_python_code`), so the
  Solver's `click('bid')`/`fill(...)`/`goto(...)`/`go_back()` strings run for real.
  Surfaces `self.terminated` (env `term`/`trunc`) so the Solver can stop cleanly.
  `screenshot_b64(som=...)` JPEG-encodes the screenshot BrowserGym already computes
  on every observation, optionally overlaying bid-tagged bounding boxes via
  BrowserGym's own `overlay_som` (Set-of-Marks). `storage_state=` (from `auth.py`)
  starts the browser context already logged in.
- `predicates.py` — URL/DOM → terminal-goal checkers (`reached`), used only to score
  episode success; `configure_terminal(url_re, text=None)` overrides the default
  shopping success-URL for non-default instances. Planning predicates are no longer
  hardcoded here (see below).
- `auth.py` — login/auth: `ensure_login(site, root_url)` returns a cached, still-valid
  Playwright `storage_state` path for one of the four account-gated sites
  (reddit/gitlab/shopping/shopping_admin), doing a one-time live login (per-site
  flows ported from `browsergym.webarena.instance.WebArenaInstance.ui_login`) and
  caching it under `.auth/<site>_state.json` if none exists or the cached one has
  expired. Credentials: `WA_<SITE>_USERNAME`/`WA_<SITE>_PASSWORD` in `.env`, falling
  back to the standard published WebArena benchmark test accounts. `None` for sites
  with no login flow (wikipedia, map). HSGE doesn't construct `WebArenaInstance`
  directly — its `__init__` hard-requires all seven `WA_*` site URL env vars to be
  set, even though a given HSGE run only explores one site.
- `agents.py` — `PageExplorer` (proposes INFO/NAV/MOD-classified, specific tasks;
  `read_only=True` drops MOD) + `Solver` (action-planner loop with action-space
  docs, CoT examples, and last-action-error feedback so it can recover instead of
  aborting the episode). Both accept `vision`/`som`/`image_detail` (see below) and,
  when a vision-attached call returns empty (refusal/content-filter), retry once
  text-only before giving up.
  `PageExplorer` asks the LLM for structured `{"tasks": [{"text": ..., "type":
  "INFO"|"NAV"|"MOD"}, ...]}` objects rather than a `[TAG]`-prefixed string (a real
  run showed 89% of tasks came back with no bracket at all; gpt-4o's natural
  tendency is to put the classification in a `type` field instead, which the old
  code discarded). `_parse_task()` reads the `type` field, falls back to a legacy
  leading `[TAG]` bracket for models that still emit one, and tags anything with
  neither as `UNKNOWN`; `read_only` drops `UNKNOWN` along with `MOD` (fail-closed —
  an unclassifiable task might be a MOD the model forgot to tag) instead of the old
  literal-substring-on-`[MOD]` check, which an untagged real MOD task would have
  slipped past. One `PageExplorer` instance lives for the whole run, so it also
  remembers every task text it has already proposed (normalized, tag stripped) and
  both echoes recent ones back into the prompt as negative context and drops
  code-level near-duplicates — a real run had 46% of all proposed tasks be
  near-identical sitewide-nav-menu boilerplate ("Go to the Forums/Wiki/Home page")
  re-proposed at nearly every page. When truncating to `max_tasks`, INFO is still
  what gets dropped first, never NAV/MOD (INFO never grows the frontier — no
  navigation happens when solving one).
  `Solver` also tracks whether each executed action actually changed the
  observation (url/axtree before vs. after) and what target (bid/url) it acted
  on. A trailing run of actions hitting the *same target* with *no observable
  change* — not just an identical action string, since a real run showed the
  model retry a stuck dropdown with different-looking-but-equally-wrong
  arguments (`select_option('378', 'Forum Name')` then `'Another Forum
  Name'`), and requiring "no change" (not just "same target") is what keeps
  this from misfiring on a legitimate multi-step sequence that happens to
  reuse the same bid across different pages — first gets a warning in the
  prompt (`_WARN_AFTER_REPEATS`, default 2) and then, since a real run showed
  the model doesn't reliably obey a text nudge alone (it kept clicking an
  inert link for the full 15-step budget with the warning present from the
  3rd call onward), a hard stop (`_MAX_REPEATS`, default 4) that ends the
  episode without spending any more LLM calls on a target that clearly isn't
  moving.
- `runtime.py` — `WebArenaExplorer`: frontier loop, skill→operator promotion, goal
  tasks, persistence. Skips re-exploring a node whose initial axtree hashes
  identical to an already-visited one (two different URLs can render the same
  content). Dumps `skills.json`/`operators.json`/`graph.json`/`predicates.json`
  (canonical `p0`/`p1`/... id → original NL text)/`nodes.json` (per-node task
  pass/fail)/`summary.json` under `out_dir` after every node (not just at the end,
  so an interrupted run still leaves a consistent snapshot), and mirrors every
  event to `out_dir/run_log.jsonl`.

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

**Frontier expansion** uses a **priority queue** (`heapq`) with two tiers of
candidates (see `docs/superpowers/specs/2026-07-07-frontier-href-mining-design.md`):
- **Tier 0 — URLs the agent actually reached** while solving a task (each `Step.url` +
  the final observation) plus open tabs (`browser.links()` / `open_pages_urls`).
  Admitted directly (only the allow/deny/visited guards), highest priority, no dedup.
- **Tier 1 — mined `<a href>`** off the page via `WebArenaBrowser.page_hrefs()`
  (Playwright `eval_on_selector_all`, since the flattened axtree drops hrefs). This is
  the fix for the old frontier-starvation gap: growth no longer depends solely on
  solved-task navigation, so a node of all-`[INFO]` tasks still contributes its links.
  Gated by a **per-template cap** (`run.per_template_cap`, default 3): `_url_template`
  normalizes a URL into a shape (drop scheme/query/fragment; wildcard id-like/digit
  segments and everything after them, e.g. `/f/AskReddit/comments/*/*`) so
  near-identical pages (per-post/-comment/-user) can't flood the frontier while
  distinct forums/types are still all explored. The cap is re-checked **lazily at pop
  time** (a template's visited count grows during the run). `run.mine_hrefs` (default
  `true`) is the master toggle; `false` reproduces the old navigated-only behavior.
  `run.max_hrefs_per_page` (default 100) caps hrefs mined per page.

Priority key `(tier, novelty, depth, seq, url)`: tier 0 before tier 1; within tier 1,
lower visited-count-of-template first (unseen templates lead); shallower depth next
(BFS breadth); `seq` for FIFO tiebreak.

**`--read-only`** makes `PageExplorer` propose only INFO/NAV tasks (drops MOD and
anything it can't classify), for smoke-testing a shared, stateful site without
writing to it (no posting, voting, cart/checkout actions).

**`max_tasks`** (config `run.max_tasks` / `--max-tasks`, default 6) caps how many
tasks `PageExplorer` proposes per node.

**Vision** (`vision`/`som`/`image_detail`, resolved per role the same way as the LLM
routing below via `run_webarena.py::_resolve_agent_vision`) lets `page_explorer`/
`solver` attach a screenshot (optionally Set-of-Marks-annotated) alongside the axtree
to a vision-capable model. Off by default for every role; `config.yaml` turns it on
for `page_explorer` (`gpt-4o`) and `solver` (`gpt-4o-mini`).

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
