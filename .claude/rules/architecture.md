# Architecture

Two-level graph: **low level** = concrete page states + trajectory edges (flat
exploration graph); **high level** = abstract skills (options ⟨I, π, β⟩) wired to
states by initiation/effect edges plus `skill→skill` composition edges. Planning
runs as graph search over the high level toward a terminal predicate.

**Discovery pipeline** (the core data flow) — each stage is one module in `hsge/`:

```
exploration loop (env.py)
  → segmentation.py    candidate cuts (URL change + axtree-similarity drop, run.seg_axtree_sim)
                       → LLM-arbitrated cut points (validated; 1-step nav segments
                       merged into a neighbor) → SubTrajectories
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
  executed via a `HighLevelActionSet` (`action_mapping=to_python_code`), with the
  `chat`/`bid`/`infeas`/`nav`/`tab` subsets enabled, so the Solver's
  `click('bid')`/`fill(...)`/`press('bid','key')`/`goto(...)`/`go_back()`/
  `new_tab()`/`tab_focus(index)`/`tab_close()` strings all run for real.
  `observation()` flattens the axtree with `filter_visible_only=True` (hidden
  elements dropped before the text ever reaches a prompt), reducing how often the
  6000-char cap below is hit — it does not bound the length outright, since
  `flatten_axtree_to_str` is not viewport-scoped (a `scroll` action would not
  change what it returns, which is why HSGE doesn't expose one).
  Surfaces `self.terminated` (env `term`/`trunc`) so the Solver can stop cleanly.
  `act()` raises `ActionError` when the action failed in the page: BrowserGym
  itself never raises — `BrowserEnv.step` catches the exception and returns it as
  the `last_action_error` observation key — so a failed action used to be
  indistinguishable from a successful one (`Solver`'s error-recovery prompt was
  dead code and `build_sft_dataset.py` exported failed actions as correct SFT
  targets). `_last_obs`/`terminated` are updated before the raise.
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
  text-only before giving up. `ACTIONS_DOC` documents all 10 actions the executor
  accepts: `click`/`fill`/`select_option`/`press`/`goto`/`go_back`/`new_tab`/
  `tab_focus`/`tab_close`/`send_msg_to_user`/`report_infeasible`. `_cap_axtree()`
  truncates the axtree shown in any prompt at 6000 chars, appending an explicit
  `[TRUNCATED: N more characters not shown]` marker rather than silently chopping
  it — used by both `PageExplorer.propose()` and every `Solver.solve()` prompt, and
  reused (imported, not duplicated) by `build_sft_dataset.py`'s offline SFT prompt
  builder so a training example's PAGE block never shows content the model
  wouldn't see at inference time. `step_outcome(pre_url, pre_axtree, url, axtree)`
  is the single shared "what happened after this action" helper (`"now at
  <url>"`/`"page changed"`/`"no change"`), used identically by `Solver.solve`'s
  live history, `build_sft_dataset.py`'s offline history, and
  `reannotate_thoughts.py`'s reflection prompts.
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
  When an episode ends exhausted (hard stop or max_steps) on a non-predicate
  task, the Solver makes one text-only "wrap-up" call -- history is shown
  with per-action outcomes (`-> now at <url>` / `-> no change`) -- that may
  only answer send_msg_to_user (declared done -> success) or
  report_infeasible; anything else is discarded. report_infeasible is a
  first-class outcome (allowed in ACTIONS_DOC, never executed in the
  browser, counted in its own `infeasible` bucket, never fed to Discovery,
  never retried).
  `solve()` returns a 7th value, `stop_reason`: `""` when the episode ended on
  a terminal action it chose while solving, else the guard that stopped it
  (`budget`/`stuck`/`novelty`), meaning the terminal action came from the
  wrap-up call above. `runtime.py` persists it as `outcome.stop_reason`, and
  `build_sft_dataset.py` refuses a wrap-up `report_infeasible` as a training
  target — the model was told it had stopped and rationalized, it did not
  conclude the task was impossible (27 of 56 infeasible shopping_admin
  episodes ended at exactly the step budget).
  A `[MOD]`/`[COMPOSITE]` task cannot be a success unless some executed action
  actually changed the page (url or axtree): a real episode declared "[MOD]
  Send an email confirmation for order #000000299" done in one step with zero
  browser actions. `[INFO]`/`[NAV]` are unaffected — answering off the landing
  page is what an INFO task looks like.
- `runtime.py` — `WebArenaExplorer`: frontier loop, skill→operator promotion, goal
  tasks, persistence. Skips re-exploring a node whose initial axtree hashes
  identical to an already-visited one (two different URLs can render the same
  content). Dumps `skills.json`/`operators.json`/`graph.json`/`predicates.json`
  (canonical `p0`/`p1`/... id → original NL text)/`nodes.json` (per-node task
  pass/fail)/`summary.json` under `out_dir` after every node (not just at the end,
  so an interrupted run still leaves a consistent snapshot), and mirrors every
  event to `out_dir/run_log.jsonl`.
  `run.task_retries` (default 0, CLI `--task-retries`) retries a failed task
  up to N more times via `_solve_with_retries`; every attempt is recorded as
  its own episode, `nodes.json`/`task_result` events carry
  `attempts`/`infeasible`, and task_stats counts each task once by final
  outcome (success / fail / infeasible). A node whose `browser_factory(url)`
  or `browser.reset()` raises (flaky/slow/unreachable URL -- a live run hit
  a Playwright navigation timeout) is caught, logged as `node_error`,
  recorded in `nodes.json` with an `error` field, and skipped -- it does not
  crash the run, unlike an unexpected exception anywhere else in node
  processing, which still propagates through the whole-loop `try/except`
  (`run_error` event, `summary.json` `status: "error"`, re-raised).
  `_solve_with_retries`'s own `browser.reset()` (called once per task, to
  return to a clean page before every Solver run, not just the node's first
  visit) is guarded the same way -- a reset failure there is logged
  (`task_reset_error`), bounded by `task_retries`, and returns a clean
  no-episode-recorded failure instead of crashing. `reset()` is the only
  `WebArenaBrowser` method without its own internal fail-soft handling
  (`close`/`screenshot_b64`/`links`/`page_hrefs` all catch-and-default
  inside `browser.py`), since a real navigation failure there has no safe
  observation to fall back to -- both of its call sites in `runtime.py` are
  now guarded.

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

Induction is vocabulary-aware: the prompt includes the registry's existing
predicate labels (`PredicateRegistry.vocabulary()`, 25 most-frequent + 25
most-recent, deduplicated) with an instruction to reuse an equivalent
predicate's exact text verbatim -- measured on wa_run_09, embedding-only
canonicalization cannot unify synonyms (the true synonym pair scored 0.570,
below the 0.6 threshold, while a false pair scored 0.606). Promotion applies
an anti-tautology gate: effects that restate a precondition are dropped
(`eff - pre`, logged as `effects_dropped` on the `operator_induced` event);
a skill with no novel effects left is rejected (`operator_rejected` event,
reason `tautological`/`no_effects`) instead of becoming an operator. Because
that gate and the page-state vocabulary pull against each other for a
*page-local* skill (entry state == exit state -> effect dropped -> operator
thrown away; 3 of 6 shopping_admin skills died this way), the prompt requires
the exit page-state to DIFFER from the entry one by naming the same page
**qualified** by what the skill established ("on the product edit page" -> "on
the product edit page with a save confirmation"), never a bare repetition and
never an element-level fallback ("the description field is filled"), which no
other skill can phrase as its entry precondition.

`verify_operator_grounding` then **gates effects**, rather than only logging as
it used to: an effect confirmed on fewer than `_EFFECT_GROUNDING_MIN` (0.5) of
the skill's members is dropped (`effects_ungrounded`), and an operator left with
none is rejected with reason `ungrounded`. shopping_admin admitted
`enter_new_description` with effect accuracy **0.0** — an effect that held on no
member at all — and planned over it. Preconditions are scored but never dropped:
removing a shaky one makes the operator applicable everywhere, which is worse
than being over-conservative. When `member_count` is 0 (no usable member steps)
the gate is skipped rather than rejecting everything.

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

**Unprefixed sampling** (`run.unprefixed_sampling` / `--unprefixed`, Go-Browse
Alg.3 l.24-26) re-solves every task that **succeeded** at a node a second time,
starting from the **site root** (`_unprefixed_pass`), so the trajectory contains
the navigation to the page as well as the task itself. Every other episode HSGE
records is *prefixed* — `_solve_with_retries` resets to the node, i.e. the agent
starts already standing on the right page — which is why 287 of the 465
successes in `outputs/wa_eval_shopping_1` were exactly **one** step. Failed
tasks are never re-run (a task the agent could not do on the right page will not
get easier from the root). Episodes are tagged `UNPREFIXED`, recorded at
`difficulty=2` so `build_sft_dataset.py`'s curriculum sorts them after LOCAL,
counted in their own `task_stats` bucket, and fed to Discovery like any other
success — solving one task from two starting points is also what makes a cluster
recur enough to reach `maturity` and become an operator. Uses `goal_max_steps`
(an unprefixed task is a LOCAL task plus navigation). Costs +1 episode per
solved task and one extra browser per node; a root browser that fails to load is
logged as `unprefixed_error` and skips the pass, never the run.

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

**SFT dataset assembly is a three-stage offline pipeline**, run after
`run_webarena.py` finishes collecting `episodes/`:
`judge_episodes.py` (optional) re-checks every declared-success episode
against its own final state with a strong LLM and appends
`outcome.judge_verified`/`outcome.judge_reason` to `episode_meta.json` in
place (additive; `outcome.success` is left untouched) — catches the agent
grading its own homework (declaring done without actually satisfying the
goal). `reannotate_thoughts.py` (optional) rewrites each step's `thought`
into a `thought_v2` field: a terse state assessment, a reflection when the
prior action made no progress, and — only on a task's terminal step — a
completion check, composed with the step's subgoal from an offline replay
of `segment_trajectory()` (the same segmentation `Discovery` uses live).
The subgoal only ever appears in the assistant *target*, never in
`build_sft_dataset.py`'s user prompt, since there is no retrieval/grounding
pipeline at inference time to supply "the current subgoal" as an input.
`build_sft_dataset.py` then turns `episodes/` into `train.jsonl`: its
system/user prompt is byte-for-byte the live Solver's (`SYSTEM =
SOLVER_SYS`, imported not duplicated), its PAGE block is capped via the same
`_cap_axtree()` the live Solver uses (so a step whose axtree exceeded 6000
chars trains on the same truncated-with-marker text the model would ever
see, not the raw persisted tree), history lines are outcome-annotated
via the same `step_outcome()` helper `Solver.solve` uses, a leading
`[INFO]/[NAV]/[MOD]` goal tag is stripped (a real WebArena eval goal never
carries one), each example carries `trajectory_id`/`step_index`/
`total_steps` for downstream trajectory-aware batching, a step whose
recorded thought carries `"[action error:"` is excluded from both training
targets and later steps' history (it was the mistake, not the recovery, and
was never in the live Solver's own history either), `report_infeasible`
episodes are kept as valid targets, and `--require-judge` restricts
declared-success episodes to `judge_verified is True` (never-judged
episodes are dropped, not silently trusted).

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
