# HSGE — Hierarchical Skill-Graph Exploration

HSGE is a framework for web agents that discover **reusable, verified skills**
during exploration and **compose** them into long-horizon tasks. It maintains a
two-level graph — concrete page states/actions at the low level, abstract skills
with precondition/effect edges at the high level — discovers skills online, admits
only those that execute successfully, transfers them to unseen sites, and generates
an easy→hard curriculum whose deepest chains are full transactions (e.g. a purchase).

This repository is a **runnable skeleton with deterministic mock backends**: the
whole pipeline runs with no API keys, GPU, or live browser. Real backends
(LLM, embedder, WebArena browser) are subclass swaps, not rewrites — the
standalone WebArena runtime under `hsge/webarena/` runs the same discovery
pipeline against a real browser.

## Quickstart (mock, no keys)

```bash
pip install numpy
python explore.py                  # run the exploration loop (frontier → discover → compose → verify)
python demo_shopping.py            # shopping domain: plan → execute → verify a purchase
python demo.py                     # login/search domain: discover → verify → transfer
python demo_purchase.py            # planning + curriculum (operator/precondition model)
python compare_three_way.py        # Flat baseline vs AWM vs HSGE on identical input
python compare.py                  # pairwise baseline comparison
PYTHONPATH=. python hsge/tests/test_clustering.py
```

Run everything from this directory (the one containing `hsge/`).

## Real WebArena run

Secrets (API keys, account passwords, `WA_*` site URLs) go in a git-ignored
`.env`; non-secret run parameters (site, max_nodes/steps/tasks, maturity, LLM
provider/model per role, vision) go in the committed `config.yaml`. Precedence
is **CLI flag > config.yaml > .env > built-in default**.

```bash
pip install -r requirements.txt        # sentence-transformers, openai, browsergym, ...
playwright install chromium

# Dry-run (scripted LLM + fake browser) — exercises the full wiring, no keys needed
python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2

# Real run — everything from config.yaml + .env
python run_webarena.py

# Real run with overrides
python run_webarena.py --site shopping --max-nodes 15 --max-depth 6 --max-steps 15
python run_webarena.py --site gitlab --headed
python run_webarena.py --provider deepseek --model deepseek-v4-flash   # override every role
python run_webarena.py --maturity 3 --predicate-sim 0.65               # tune skill discovery

# Read-only mode (INFO/NAV only, drops MOD + UNKNOWN) — safe for shared sites
python run_webarena.py --read-only --max-nodes 5 --max-steps 10

# Explicit root URL (when not using WA_* env vars)
python run_webarena.py \
    --root-url "http://your-host:7770" \
    --out outputs/wa_run \
    --allow "http://your-host:7770.*" \
    --max-nodes 15 --max-depth 6 --max-steps 15
```

### Per-role LLM configuration

Each helper can use a different model via `llm.agents.<role>` in `config.yaml`:

```yaml
llm:
  provider: deepseek
  temperature: 0.2
  agents:
    page_explorer:          # task proposal — stronger model recommended
      model: gpt-4o
      vision: true
      som: true
    solver:                 # action selection — cheaper model
      model: gpt-4o-mini
      vision: true
      som: true
    trajectory_segmenter:
      model: deepseek-v4-flash
    skill_abstractor:
      model: deepseek-v4-flash
    operator_inducer:
      model: deepseek-v4-flash
    episode_judge:
      model: deepseek-v4-flash
    thought_reannotator:
      model: deepseek-v4-flash
```

### Turning a run into training data

```bash
# Optional: catch false-positive "success" with a stronger LLM
python judge_episodes.py outputs/wa_run_XX
python judge_episodes.py outputs/wa_run_XX --limit 20

# Optional: rewrite each step's thought into structured form
python reannotate_thoughts.py outputs/wa_run_XX
python reannotate_thoughts.py outputs/wa_run_XX --limit 20 --axtree-sim 0.5

# Build SFT dataset (--require-judge: only keep judge-verified successes)
python build_sft_dataset.py outputs/wa_run_XX/episodes train.jsonl
python build_sft_dataset.py outputs/wa_run_XX/episodes train.jsonl --require-judge
```

`judge_episodes.py`/`reannotate_thoughts.py` write into `episode_meta.json`/
`episode.jsonl` in place (additively — `outcome.success`/`thought` are never
touched), so run them against a scratch copy of `outputs/wa_run_XX` first if
you want to keep that run's original artifacts untouched. Both are optional:
skipping them and running `build_sft_dataset.py outputs/wa_run_XX/episodes
train.jsonl` alone still works exactly as before. `--require-judge` only has
an effect once episodes have actually been judged — without it (or before
running `judge_episodes.py`), every declared-success episode is kept as
before.

### Key CLI flags

| Flag | Description | Default |
|---|---|---|
| `--site` | Site name (shopping, gitlab, reddit, ...) | From config.yaml |
| `--root-url` | Explicit start URL (overrides `--site`) | null |
| `--out` | Output directory | outputs/wa_run |
| `--allow` | Regex of allowed child URLs | Derived from root URL |
| `--denylist` | Regex of blocked child URLs | "logout\|\\?p=\|..." |
| `--max-nodes` | Max nodes to visit | 500 |
| `--max-depth` | Max crawl depth | 300 |
| `--max-steps` | Max steps per episode | 15 |
| `--max-tasks` | Max tasks proposed per node | 9 |
| `--maturity` | Times a skill must recur before admission | 2 |
| `--task-retries` | Retry failed tasks (0 = off) | 0 |
| `--headed` | Show browser window | false |
| `--read-only` | INFO/NAV only, drop MOD + UNKNOWN | false |
| `--dry-run` | Scripted LLM + fake browser, no network | false |
| `--provider` | LLM provider (openai, deepseek) | From .env |
| `--model` | Default model for all roles | From .env |

### Output artifacts

After a run, the output directory contains:

| File | Contents |
|---|---|
| `skills.json` | Verified skills |
| `operators.json` | Planning operators (derived from skills) |
| `graph.json` | Operator graph (effect→precondition edges) |
| `predicates.json` | Canonicalized predicates (p0, p1, ...) |
| `nodes.json` | Per-node task results |
| `summary.json` | Run summary |
| `run_log.jsonl` | Event log |
| `episodes/` | Per-episode directories |
| `episodes/ep_XXXX/episode_meta.json` | Goal, outcome, reward |
| `episodes/ep_XXXX/episode.jsonl` | Per-step action + observation |
| `episodes/ep_XXXX/page_state/` | AXTree + screenshot per step |

Highlights of the runtime (see `.claude/rules/architecture.md` for the full map):

- **Skill → operator promotion**: once a skill recurs enough to be admitted
  (`--maturity`), an LLM induces its NL preconditions/effects, which an embedding
  registry canonicalizes into stable predicate ids; a BFS planner composes the
  resulting operators toward a terminal goal (e.g. `order_confirmed` on shopping).
- **Per-role LLMs**: each helper can use a different model via `llm.agents.<role>`
  in `config.yaml`. Optional per-role **vision** (screenshot + Set-of-Marks) for
  vision-capable models.
- **Frontier**: priority queue mixing URLs the agent actually reached (tier 0)
  with `<a href>` links mined off each page (tier 1, bounded by a per-URL-template
  cap so link-dense pages can't flood the frontier).
- **Login/auth**: one-time login per account-gated site (reddit/gitlab/shopping/
  shopping_admin), session cached under `.auth/`.
- **Persistence**: all artifacts rewritten after **every** node, so an interrupted
  run still leaves a consistent snapshot.
- **Structured task types**: tasks are classified as INFO/NAV/MOD via a structured
  `type` field (not free-text brackets); `--read-only` drops MOD + UNKNOWN
  (fail-closed).
- **Stuck-loop detection**: solver tracks repeated no-progress actions on the same
  target; after a threshold, the episode is terminated instead of wasting steps.

## Scripts

| Script | What it does |
| --- | --- |
| `explore.py` | Mock exploration loop (frontier → discover → compose → verify) |
| `demo.py` | Full discover→cluster→abstract→verify→transfer on mock sites |
| `demo_shopping.py` | End-to-end shopping: plan → execute → verify |
| `demo_purchase.py` | Planning + curriculum only (operator/precondition model) |
| `compare.py`, `compare_three_way.py` | Baseline comparisons (Flat / AWM / HSGE) |
| `run_webarena.py` | Standalone WebArena exploration (real run + `--dry-run`) |
| `judge_episodes.py` | LLM re-checks declared-success episodes |
| `reannotate_thoughts.py` | Rewrites each step's thought into structured form |
| `replay_segmentation.py` | Replays segmentation over recorded episodes (compare old vs new) |
| `build_sft_dataset.py` | Converts trajectories into curriculum-ordered SFT data |

## Documentation (`docs/`)

| Doc | Read it for |
| --- | --- |
| `01_overview.md` | The method, contributions, and what makes it different |
| `02_architecture.md` | Module map, data flow, the hierarchical-graph model |
| `03_running_locally.md` | Running every script + interpreting the output |
| `04_webarena_runbook.md` | Hosting WebArena and running real exploration |
| `06_training.md` | The collect → SFT → fine-tune → evaluate pipeline |
| `09_run_on_webarena.md` | The standalone WebArena runtime (**stale** — predates docs 10–12) |
| `10_webarena_real_wiring_session.md` | Real WebArena wiring, skill-derived operators, config.yaml/.env split |
| `11_vision_auth_hardening_session.md` | Node dedup, persisted artifacts, vision + Set-of-Marks, retry/backoff, login/auth |
| `12_real_run_bug_fixes_session.md` | Task-diversity dedup, structured INFO/NAV/MOD, Solver stuck-loop fix |
| `13_run02_reddit_exploration_log.md` | Real reddit run: frontier-starvation root cause + operator quality |
| `14_vast_ai_training_eval_tutorial.md` | Training on vast.ai: setup, fine-tune, serve, evaluate |

## The pipeline at a glance

```
explore / run_webarena.py (collect verified, composed trajectories)
   -> judge_episodes.py        (optional: catch false-positive "success")
   -> reannotate_thoughts.py   (optional: richer per-step thoughts)
   -> build_sft_dataset.py     (curriculum-ordered SFT data)
      -> fine-tune a model
         -> evaluate on WebArena
            -> re-collect with the improved agent   (iterated bootstrap)
```
