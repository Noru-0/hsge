# HSGE — Hierarchical Skill-Graph Exploration

HSGE is a framework for web agents that discover **reusable, verified skills**
during exploration and **compose** them into long-horizon tasks. It maintains a
two-level graph — concrete page states/actions at the low level, abstract skills
with precondition/effect edges at the high level — discovers skills online, admits
only those that execute successfully, transfers them to unseen sites, and generates
an easy→hard curriculum whose deepest chains are full transactions (e.g. a purchase).

The core pipeline runs with **deterministic mock backends**: no API keys,
GPU, or live browser needed to explore the code. Real backends (LLM, embedder,
WebArena browser) are subclass swaps, not rewrites — the standalone WebArena
runtime under `hsge/webarena/` runs the same discovery pipeline against a
real browser and real websites.

This has been run for real: four WebArena sites (Shopping, Shopping Admin,
GitLab, Reddit) explored end to end, turned into a 4,605-example SFT dataset,
used to LoRA-fine-tune Qwen3.5-9B, and evaluated on WebArena's own 655-task
benchmark — **20.8% success vs. 13.3% for the same base model unfine-tuned**
(+7.5 points, statistically significant on 3/4 sites; see
`training/README.md` and the tracked `outputs/eval/` results for the full
numbers and caveats).

## Quickstart (mock, no keys)

```bash
pip install numpy
python explore.py             # run the exploration loop (frontier -> discover -> compose -> verify)
python demo_shopping.py       # shopping domain: plan -> execute -> verify a purchase
python demo.py                # login/search domain: discover -> verify -> transfer
python compare_three_way.py   # Flat baseline vs AWM vs HSGE on identical input
python -m pytest hsge/tests/ -q   # or: PYTHONPATH=. python hsge/tests/test_clustering.py
```

Run everything from this directory (the one containing `hsge/`).

## Real WebArena run

Secrets (API keys, account passwords, `WA_*` site URLs) go in a git-ignored
`.env`; non-secret run parameters (site, max_nodes/steps/tasks, maturity, LLM
provider/model per role, vision) go in the committed `config.yaml`. Precedence
is **CLI flag > config.yaml > built-in default**.

```bash
pip install -r requirements.txt        # sentence-transformers, openai, browsergym, ...
playwright install chromium

python run_webarena.py                               # everything from config.yaml + .env
python run_webarena.py --site shopping --max-nodes 5 --headed
python run_webarena.py --provider deepseek --model deepseek-chat   # override every role
python run_webarena.py --read-only --max-nodes 2 --max-steps 4     # smoke-test a shared
                                                                   # site without writes
python run_webarena.py --dry-run --out /tmp/wa_dry   # scripted LLM + fake browser,
                                                     # exercises the full wiring
```

### Turning a run into training data

```bash
python judge_episodes.py outputs/wa_run_XX                 # optional: catch false-positive "success"
python reannotate_thoughts.py outputs/wa_run_XX             # optional: richer per-step thoughts
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

### Fine-tuning and evaluating on WebArena

`training/` takes a built `train.jsonl` the rest of the way: LoRA-fine-tune a
model with LLaMA-Factory, merge the adapter, serve it with vLLM, and evaluate
it against WebArena's official per-site tasks — including running a base vs.
fine-tuned comparison across multiple sites in parallel on separate GPU boxes.

```bash
python training/merge_datasets.py datasets/train_reddit.jsonl datasets/train_shopping.jsonl \
    datasets/train_shopping_admin.jsonl datasets/train_gitlab.jsonl -o datasets/train_all.jsonl
python training/prepare_dataset.py datasets/train_all.jsonl --name all --out-dir training/data/all
llamafactory-cli train training/qwen35_9b_lora_all.yaml
llamafactory-cli export training/merge_lora_all.yaml         # or merge_lora_peft.py (no train venv needed)
bash training/serve_vllm.sh /path/to/merged-model
python training/eval_webarena.py --site reddit --site-url https://<tunnel> --out outputs/eval/reddit/finetuned
python training/eval_status.py outputs/eval/reddit/finetuned          # progress / sanity checks
python training/analyze_eval_traces.py outputs/eval/reddit/finetuned  # failure-cause breakdown
```

`datasets/` holds the per-domain and merged SFT exports (see
`datasets/README.md`) — `train_all.jsonl` is what the shipped `checkpoint-536`
result above was trained on. `training_data/` is a separate, full-column
audit copy of the same train/val split (`build_sft_dataset.py`'s
`--keep-all-fields` output), useful for inspecting an example by eye without
regenerating it.

`training/README.md` is the full, tested command reference (vast.ai setup,
per-domain parallel eval, troubleshooting); `docs/14_vast_ai_training_eval_tutorial.md`
narrates the same pipeline with the reasoning and gotchas behind each step.
The curated results this repo ships under `outputs/eval/` (per-task JSON +
anomaly reports, no screenshots) back the numbers quoted above; the raw
exploration/eval run directories (multi-GB, per-step screenshots) are not
tracked.

Highlights of the runtime (see `.claude/rules/architecture.md` for the full map):

- **Skill → operator promotion**: once a skill recurs enough to be admitted
  (`--maturity`), an LLM induces its NL preconditions/effects, which an embedding
  registry canonicalizes into stable predicate ids; a BFS planner composes the
  resulting operators toward a terminal goal (e.g. `order_confirmed` on shopping).
  Non-shopping sites run exploration-only.
- **Per-role LLMs**: each helper (`page_explorer`, `solver`, `trajectory_segmenter`,
  `skill_abstractor`, `skill_verifier`, `operator_inducer`) can use a different
  model via `llm.agents.<role>` in `config.yaml`. Optional per-role **vision**
  (screenshot + Set-of-Marks) for vision-capable models.
- **Frontier**: priority queue mixing URLs the agent actually reached (tier 0)
  with `<a href>` links mined off each page (tier 1, bounded by a per-URL-template
  cap so link-dense pages can't flood the frontier).
- **Login/auth**: one-time login per account-gated site (reddit/gitlab/shopping/
  shopping_admin), session cached under `.auth/`.
- **Persistence**: `skills.json` / `operators.json` / `predicates.json` /
  `graph.json` / `nodes.json` / `summary.json` + `run_log.jsonl` are rewritten
  after every node, so an interrupted run still leaves a consistent snapshot.

## Scripts

| Script | What it does |
| --- | --- |
| `explore.py` | The exploration loop: frontier expansion, skill discovery, goal-conditioned composed episode, terminal verification |
| `demo.py` | Full discover→cluster→abstract→verify→transfer on mock login/search sites |
| `demo_shopping.py` | End-to-end shopping: plan a purchase, execute it, verify at order-confirmation |
| `demo_purchase.py` | Planning + curriculum only (operator/precondition model) |
| `compare.py`, `compare_three_way.py` | Baseline comparisons (Flat / AWM / HSGE) |
| `run_webarena.py` | Standalone WebArena exploration (real run + `--dry-run`) |
| `judge_episodes.py` | Optional: LLM re-checks declared-success episodes, catches false positives |
| `reannotate_thoughts.py` | Optional: rewrites each step's thought into a state/subgoal/reflection/completion-check template |
| `build_sft_dataset.py` | Converts collected trajectories into curriculum-ordered SFT data (prompt byte-for-byte matches the live Solver; `--require-judge` to only keep judge-verified successes) |
| `replay_segmentation.py` | Replays segmentation over recorded episodes to compare the URL-only baseline against the URL+axtree-similarity+LLM algorithm |

`training/` has its own set of scripts (dataset merge/prepare, LoRA configs,
vLLM serving, WebArena evaluation, trace analysis) — see
`training/README.md` for what each one does.

## Documentation (`docs/`)

| Doc | Read it for |
| --- | --- |
| `01_overview.md` | The method, contributions, and what makes it different |
| `02_architecture.md` | Module map, data flow, the hierarchical-graph model |
| `03_running_locally.md` | Running every script + interpreting the output |
| `04_webarena_runbook.md` | Hosting WebArena and running real exploration |
| `06_training.md` | The collect → SFT → fine-tune → evaluate → loop pipeline |
| `09_run_on_webarena.md` | The standalone WebArena runtime (**stale** — predates docs 10–12) |
| `10_webarena_real_wiring_session.md` | Real WebArena wiring, skill-derived operators, config.yaml/.env split |
| `11_vision_auth_hardening_session.md` | Node dedup, persisted artifacts, vision + Set-of-Marks, retry/backoff, login/auth |
| `12_real_run_bug_fixes_session.md` | Task-diversity dedup, structured INFO/NAV/MOD classification, Solver stuck-loop fix |
| `13_run02_reddit_exploration_log.md` | Real reddit run: frontier-starvation root cause + operator quality via grounding check |
| `14_vast_ai_training_eval_tutorial.md` | LoRA fine-tuning + WebArena eval on rented vast.ai GPUs, narrated (venv isolation, template gotchas, parallel-eval technique) |
| `15_seed_refinement_improvement_plan.md` | Seed-conditioned bottom-up refinement roadmap (planning only) |
| `16_phaseBC_verification_refinement_plan.md` | Verification-first / solver-competence roadmap, reprioritized from a real seed run (planning only) |
| `17_phaseC_solver_competence_plan.md` | Solver-competence tasks (subgoal-guided GOAL solving, anti-wandering, grounded operators), reprioritized from a second real run (planning only) |
| `go-browse.md` | Full text of the Go-Browse paper — the closest related work, kept for reference |
| `00_package_readme.md` | The original package-level README |

`training/README.md` is the terse command reference for the fine-tune →
merge → serve → evaluate loop (see "Fine-tuning and evaluating on WebArena"
above); `docs/14_...` is the narrated version of the same pipeline.

## The pipeline at a glance

```
explore / run_webarena.py (collect verified, composed trajectories)
   -> judge_episodes.py        (optional: catch false-positive "success")
   -> reannotate_thoughts.py   (optional: richer per-step thoughts)
   -> build_sft_dataset.py (curriculum-ordered SFT data, train_<site>.jsonl)
      -> training/merge_datasets.py + prepare_dataset.py
         -> llamafactory-cli train (LoRA)   -> llamafactory-cli export (merge)
            -> training/serve_vllm.sh
               -> training/eval_webarena.py   (official WebArena tasks)
                  -> training/eval_status.py / analyze_eval_traces.py
                     -> re-collect with the improved agent   (iterated bootstrap)
```
