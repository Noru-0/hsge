# 10 — Session Report: Real WebArena Wiring + Skill-Derived Operators

Covers commits `138ab2d`..`0bef15f` on branch `original`. Goal: take the WebArena
runtime from "dry-run only" to "actually runnable against a hosted WebArena instance
with a real LLM", and fix the design gap where planning operators were mined from raw
trajectories instead of the skills HSGE already discovers and verifies.

## 1. Operators are now derived from verified skills, not raw trajectories

**Problem.** `runtime.py` had two independent tracks per successful episode: one mined
an `Operator` directly from the trajectory's start/end predicate delta
(`_mine_operator`), and a separate one fed HSGE `Discovery` to grow the skill library.
Operators were noisy (every successful episode, not just recurring behavior) and
predicates came from a hardcoded 6-word vocabulary (`predicates.py`) that couldn't
generalize past the shopping site.

**Fix.**
- `_mine_operator` is gone. `runtime.py::_promote_skill_to_operator` now runs only on
  skill ids that `Discovery.on_trajectory(...)` actually admits (i.e. a cluster that
  recurred `maturity` times and passed the library's gate).
- `hsge/operator_induction.py` (new): asks the LLM for a skill's preconditions/effects
  in free NL, from its `SkillCard` (name/description/action_template) plus the
  boundary axtrees (before/after) of a couple of cluster members.
- `hsge/predicate_registry.py` (new): wraps `OnlineClusterer` (the same streaming
  cosine-threshold clusterer the skill library uses) to canonicalize those free-form
  NL predicates into stable ids (`p0`, `p1`, ...). Merging is disabled
  (`merge_threshold=2.0`) so an id, once assigned, never gets silently reassigned to a
  different operator.
- `operators.py`'s BFS planner is untouched — it still does set operations
  (`effects & preconditions`) over `frozenset[str]`; the only change is that the
  strings are now embedding-learned canonical ids instead of a hand-written
  vocabulary.
- An operator is `terminal` iff the LLM flagged it, or a member's trajectory actually
  reached the terminal goal via `predicates.reached()` (ground truth, not LLM opinion).
- `schema.Step` gained an optional `axtree: str = ""` field so the boundary states are
  available; `Solver` populates it.

Files: `hsge/predicate_registry.py`, `hsge/operator_induction.py`, `hsge/schema.py`,
`hsge/webarena/agents.py`, `hsge/webarena/runtime.py`.

## 2. Real backend wiring: BrowserGym action execution + LLM

**Problem.** The `Solver` emitted high-level action strings (`click('a51')`,
`fill('bid','x')`) but `WebArenaBrowser.act()` passed them straight into
`env.step()` — BrowserGym's `openended` env needs a `HighLevelActionSet` +
`action_mapping` to translate those into executable Python. Without it, the very
first real action would fail.

**Fix.**
- `hsge/webarena/browser.py`: construct `HighLevelActionSet(subsets=["chat","bid",
  "infeas","nav"])`, pass `action_mapping=action_set.to_python_code` to `gym.make(...)`.
  Verified offline against installed `browsergym 0.14.3` that `click/fill/goto/
  go_back` all map to valid Python. Also: richer axtree (`extra_element_properties`,
  visible+hidden), optional `PW_EXTRA_HEADERS` via `pw_context_kwargs`, and
  `self.terminated` surfaced from the env's `term`/`trunc` so the Solver can stop
  cleanly instead of hammering a dead episode.
- `hsge/backends.py`'s `OpenAILLM`/`STEmbedder` were already complete (lazy-imported,
  read `OPENAI_API_KEY`/`OPENAI_BASE_URL`/`HSGE_MODEL`); no changes needed there beyond
  a stderr warning when a response can't be parsed as JSON, so failures are visible
  instead of silently becoming `{}`.
- `predicates.py::configure_terminal(url_re, text=None)` lets a non-default WebArena
  instance override the checkout success-URL/text used for terminal verification.
- `runtime.py` gained a `deny_pattern` (denylist wins over allow) to keep the frontier
  from exploding on pagination/filter/logout URLs.

Files: `hsge/webarena/browser.py`, `hsge/webarena/predicates.py`,
`hsge/webarena/runtime.py`, `hsge/backends.py`.

## 3. Config split: `config.yaml` (committed) vs `.env` (secrets, git-ignored)

**Problem.** All run parameters were CLI-only; there was no way to track a run
configuration in git without leaking secrets, and the docs referenced a
`load_env_file()` that didn't exist.

**Fix.**
- `config.yaml` (new, committed): `run.*` (site, out_dir, allow/denylist, max_nodes/
  depth/steps, maturity, predicate_sim, headed, terminal_goal, success_url_re,
  full_reset_url), `llm.*` (provider/model/base_url/temperature), `embedder.model`.
- `.env` (git-ignored via a new `.gitignore`): API keys, `WA_*` site URLs,
  `WA_ACCOUNT_*` credentials. `run_webarena.py` calls `load_dotenv()` on start.
- Precedence: **CLI flag > config.yaml > built-in default** (`_pick()` helper; CLI
  args default to `None` so they only override when explicitly passed).
- Provider switch: `config.llm.provider` (or `$LLM_PROVIDER`, default `openai`)
  resolves `${PROVIDER}_API_KEY` / `_BASE_URL` / `_MODEL` from `.env` — verified this
  correctly resolves `deepseek` → `deepseek-v4-flash @ api.deepseek.com/v1`. Both
  OpenAI and Deepseek are OpenAI-compatible, so one `OpenAILLM` class covers both.
- New CLI flags: `--config`, `--site`, `--provider`, `--base-url`, `--headed`,
  `--denylist`, `--full-reset-url`, `--success-url-re`, `--maturity`, `--read-only`.

Files: `config.yaml`, `.gitignore`, `run_webarena.py`, `requirements.txt` (added
`pyyaml`, `python-dotenv`, `requests`; uncommented the real-backend deps section).

## 4. Bug found via first real run: abstraction crashed on off-schema LLM output

**Symptom** (from the user's own terminal, against a real reddit instance):
```
KeyError: 'name'
  File ".../hsge/abstraction.py", line 37, in abstract_cluster
    name=out["name"],
```

**Root cause.** `abstract_cluster`'s system prompt said only "Return JSON" with no
schema. `MockLLM` always happens to return every expected key, so this never
surfaced in dry runs; a real LLM (deepseek) omitted `name`/`action_template`/etc. and
the hard `out["name"]` indexing crashed the whole run.

**Fix.**
- `hsge/abstraction.py`: system prompt now spells out the exact JSON shape; every
  field is read via `.get()` with a payload-derived fallback (name from the dominant
  subgoal, template from the action verbs, etc.) — a missing/malformed key degrades
  gracefully instead of crashing. Slots are validated field-by-field.
- `hsge/segmentation.py`: iterates the code-computed URL-boundary spans (authoritative)
  and only takes the subgoal *label* from the LLM by index, instead of trusting the
  LLM to echo back `span` correctly.
- Verified with an `EmptyLLM`/`PartialLLM` test harness that both paths now degrade to
  a sane fallback `SkillCard` instead of raising.

Files: `hsge/abstraction.py`, `hsge/segmentation.py`.

## 5. Explorer/Solver prompt quality + frontier/terminal robustness

Prompted by two research/review sub-agents: one studying `references/Go-Browse-main/`
(a more elaborate multi-agent exploration framework) for prompt patterns, one
reviewing this codebase for real-run bugs.

- **Frontier actually expands.** `browser.links()` (BrowserGym's `open_pages_urls`)
  is effectively just the current tab, so a real run previously explored exactly one
  node regardless of `--max-nodes`. `runtime.py::run()` now accumulates every URL the
  agent visits *while solving* (each `Step.url`, the final observation, plus open
  tabs) as frontier candidates, bounded by `max_depth`. This is the single biggest
  fix for real exploration coverage.
- **Site-aware terminal.** `terminal_goal` can be `None` — non-shopping sites (e.g.
  reddit) run exploration-only (skills/operators still discovered) with an explicit
  `[goal] no terminal predicate for this run -> exploration-only` notice, instead of
  silently producing `verified=False` forever. Resolution order: `config.run.
  terminal_goal` explicit > `"order_confirmed"` auto (shopping, or when
  `--success-url-re` is set) > `None`.
- **Better prompts** (`hsge/webarena/agents.py`), borrowing patterns from Go-Browse:
  - `PageExplorer`: demands *specific* tasks ("Add the Sony PS5 to the cart", not
    "add item to cart"), tagged `[INFO]`/`[NAV]`/`[MOD]` in that proposal order.
  - `Solver`: documents the action space inline, adds worked CoT examples, and now
    feeds the last action's error back into the next prompt so the agent can recover
    — it `continue`s past a failed action instead of aborting the whole episode.
  - `PageExplorer(read_only=True)` / `--read-only` CLI flag: instructs the LLM to
    propose only `[INFO]`/`[NAV]` and filters out any `[MOD]` task as a second
    safeguard, so a smoke run against a real shared site never posts, comments,
    votes, or checks out.
- **Robustness:** `predicate_sim` (the predicate-registry cosine threshold) is now
  config-wired instead of stuck at the default; empty operator-boundary states are
  logged instead of silently inducing from nothing; `Solver.solve`'s docstring was
  fixed to match its actual 4-tuple return.

Files: `hsge/webarena/agents.py`, `hsge/webarena/browser.py`,
`hsge/webarena/runtime.py`, `run_webarena.py`, `config.yaml`.

## What's verified vs. not

**Verified in this session:**
- Mock pipeline stays green and deterministic throughout (`pytest hsge/tests/ -q`,
  4 tests) — every change here is additive/defensive for the real path.
- `--dry-run` exercises the full loop end to end, including the new multi-node
  frontier logic and skill→operator promotion.
- `HighLevelActionSet.to_python_code` verified offline against the installed
  `browsergym 0.14.3` for `click/fill/goto/go_back`.
- `_resolve_llm` verified offline to correctly read the deepseek provider config
  from `.env`.
- One real run (user's machine, against a live reddit instance) exercised: chromium
  launch, deepseek LLM calls, real action execution via the action set, and
  segmentation/clustering — which is what surfaced the abstraction `KeyError`
  (fixed, see §4).

**Not verified (needs the user's environment):**
- End-to-end multi-node frontier growth against a real site (the frontier fix landed
  after the one real run that happened; needs a fresh run to confirm).
- Real purchase completion on the shopping site (`WA_SHOPPING` was returning
  HTTP 502 / a Cloudflare interstitial during this session, not the storefront).
- `--read-only` end-to-end against reddit — could not be exercised from this
  environment because `WA_REDDIT` is a LAN address (`192.168.1.31:8880`) unreachable
  from the sandboxed shell used here; the user needs to run it directly.

## Suggested next steps (not started)

From the code-review sub-agent, still open:
- `_promote_skill_to_operator` only looks at the first 2 `member_ids`; if both happen
  to have empty `steps`, the operator is induced with zero page context (now at least
  logged, not silent).
- Consider requiring some objective evidence of progress (URL change / predicate
  fired) before trusting a local task's self-declared `send_msg_to_user` success,
  since a real LLM can declare "done" prematurely and that trajectory currently feeds
  straight into skill discovery.
- Heavier Go-Browse patterns not adopted here: a separate feasibility-checker pass
  before solving, a vision-based LLM-as-judge evaluator, and a dedicated
  `NavExplorerAgent`. These are bigger lifts (~half a day each) and were deliberately
  left out of this session's scope.
