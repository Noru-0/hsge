# CLAUDE.md

## Project Overview

HSGE (Hierarchical Skill-Graph Exploration) is a research framework that extends
flat web exploration with online skill discovery, verification-gated admission, a
hierarchical skill graph, cross-domain transfer, and curriculum generation. It
enables web agents to discover reusable skills and compose them into long-horizon
tasks like completing a purchase.

The pipeline runs entirely with deterministic mock backends — no API keys, GPU, or
browser needed for development.

## Commands

```bash
# Run all tests
python -m pytest hsge/tests/ -v

# Run a single test file
python -m pytest hsge/tests/test_clustering.py -v

# Run demos (all offline, no keys needed)
python explore.py              # Exploration loop: frontier → discover → compose → verify
python demo.py                 # Discover → cluster → abstract → verify → transfer
python demo_shopping.py        # Shopping domain: plan → execute → verify purchase
python demo_purchase.py        # Operator/precondition planning only
python compare.py              # Flat baseline vs HSGE
python compare_three_way.py    # Flat vs AWM vs HSGE

# WebArena dry-run (no live instance, no browser needed)
python run_webarena.py --dry-run --out /tmp/test_dry --max-nodes 2

# WebArena real run (requires live WebArena shopping site + .env with API keys)
python run_webarena.py --provider deepseek --root-url "http://host:7770/" --out outputs/wa_run --max-nodes 50
python run_webarena.py --provider openai --explorer-model gpt-4o-mini --solver-model gpt-4o \
  --screenshot --root-url "http://host:7770/" --out outputs/wa_run --max-nodes 50

# Build SFT dataset from collected trajectories (Go-Browse style: JSON + narrative thought)
python build_sft_dataset.py outputs/wa_run/episodes train.jsonl --action-format webarena_json

# Multi-turn: one sample per trajectory
python build_sft_dataset.py outputs/wa_run/episodes train.jsonl --action-format webarena_json --multiturn
```

Always run from the project root. Set `PYTHONPATH=.` when invoking scripts or
tests directly.

## Architecture

### Layers

1. **Backends** (`hsge/llm.py`, `hsge/env.py`) — Pluggable, mockable. `LLM`,
   `Embedder`, and `WebEnv` are ABCs with deterministic mock implementations.

2. **Discovery pipeline** — `segmentation.py` → `clustering.py` → `abstraction.py`
   → `verification.py` → `library.py`. Converts raw trajectories into a verified
   skill library.

3. **Hierarchical graph** — `graph.py` (state + skill nodes/edges) and
   `operators.py` (precondition/effect skills + BFS planner).

4. **Generation & reuse** — `curriculum.py` (easy→hard composition) and
   `transfer.py` (retrieve → reground → verify on new sites).

5. **Online hook** — `discovery.py`. Call `Discovery.on_trajectory(...)` from
   inside an exploration loop.

### Data Flow

```
exploration loop → trajectories → segmentation → candidate SubTrajectories
  → online clustering → growing clusters → abstraction → parameterized SkillCards
    → verification (≥k successes) → SkillLibrary + HierarchicalGraph
      → curriculum (plan to goals, easy→hard) + transfer (reground on new sites)
```

### Core Data Types (`hsge/schema.py`)

- **`Step`** — One (action, observation) pair with URL, DOM signature
- **`SubTrajectory`** — Contiguous slice of steps with a subgoal, clustered into skills
- **`SkillCard`** — An option ⟨I, π, β⟩: initiation set, parameterized policy,
  termination/success predicate
- **`Task`** — Goal-conditioned composed task for curriculum

## Key Design Principles

- **Domain generality.** All improvements, abstractions, and heuristics must be
  domain-agnostic. Never hardcode assumptions about specific web domains (e.g.
  shopping, forums, documentation). Skills, clustering, segmentation, and
  planning must transfer across unrelated sites without modification. If a
  change would only help one domain, it belongs in a domain-specific config or
  plugin, not in the core pipeline.

- **Verification is the quality gate.** Skills are hypotheses; they enter the
  library only after successful execution in held-out contexts (≥k).

- **No fixed k in clustering.** Uses cosine-threshold / DP-means streaming
  clusterer. The one knob is an interpretable cosine threshold.

- **Precondition/effect matching** drives composition, not page similarity or
  co-occurrence. `skill→skill` edges come from "B's preconditions are satisfied by
  A's effects."

- **Terminal verification, not self-report.** Success means reaching a goal state
  programmatically (e.g. `order_confirmed`), not just "search done."

- **Pluggable backends.** Swap mocks for real by subclassing `LLM.complete_json`,
  `Embedder.encode`, and `WebEnv.reset/step/check`.

## File Map

| File | Purpose |
|------|---------|
| `hsge/schema.py` | `Step`, `SubTrajectory`, `SkillCard`, `ParamSlot`, `Task` |
| `hsge/llm.py` | `LLM`/`MockLLM`, `Embedder`/`HashingEmbedder` |
| `hsge/env.py` | `WebEnv`, `PageState`, mock `demo_sites` |
| `hsge/segmentation.py` | URL-boundary + LLM trajectory segmentation |
| `hsge/clustering.py` | `OnlineClusterer` — streaming nonparametric clustering |
| `hsge/abstraction.py` | Cluster → `SkillCard` abstraction |
| `hsge/verification.py` | Execute + ≥k-success admission gate |
| `hsge/library.py` | `SkillLibrary` — full observe→admit pipeline + retrieval |
| `hsge/graph.py` | `HierarchicalGraph` — two-level state+skill graph |
| `hsge/operators.py` | `Operator`, `OperatorGraph`, `plan()` BFS planner |
| `hsge/transfer.py` | `transfer_to_site()` — cross-domain skill transfer |
| `hsge/curriculum.py` | `generate_curriculum()` — compose + difficulty ordering |
| `hsge/discovery.py` | `Discovery` — online hook for exploration loops |
| `hsge/backends.py` | Backend factory/registry |
| `hsge/webarena/` | WebArena integration (browser, agents, scoring, frontier filter) |

## Tests

Tests live in `hsge/tests/`. They use pytest with a `conftest.py` that adds the
project root to `sys.path`. Test files:

- `test_clustering.py` — Online clusterer unit tests
- `test_action_validation.py` — WebArena action validation
- `test_build_sft_dataset.py` — SFT dataset builder
- `test_hsge_prompt_constructor.py` — Prompt construction tests

## WebArena

The WebArena runtime is at `run_webarena.py`. Supporting modules are in
`hsge/webarena/`:
- `browser.py` — BrowserGym environment wrapper
- `agents.py` — Agent implementations (PageExplorer, Solver, etc.)
- `frontier_filter.py` — Frontier filtering logic
- `action_validation.py` — Action validation and safety checks
- `predicates.py` — Goal predicates for verification
- `scoring.py` — Task scoring and evaluation
- `verification_context.py` — Context for terminal verification

The reference WebArena implementation lives in `webarena-main-lora/`.

### Key CLI Flags

| Flag | Description |
|------|-------------|
| `--provider deepseek\|openai\|custom` | LLM provider preset |
| `--model MODEL` | Model for both explorer & solver |
| `--explorer-model MODEL` | PageExplorer model (cheap, e.g. `deepseek-chat`) |
| `--solver-model MODEL` | Solver model (strong, e.g. `deepseek-reasoner`) |
| `--root-url URL` | WebArena shopping site root |
| `--max-nodes N` | Max frontier nodes |
| `--max-depth N` | Max exploration depth |
| `--max-steps N` | Max steps per episode |
| `--screenshot` | Enable vision mode (needs vision-capable model) |
| `--dry-run` | Test pipeline without browser |

### .env Configuration

```bash
# DeepSeek (OpenAI-compatible)
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-chat

# OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Separate models for explorer (cheap) & solver (strong)
EXPLORER_MODEL=deepseek-chat
SOLVER_MODEL=deepseek-reasoner
```

## Documentation

Comprehensive docs in `docs/`:
- `01_overview.md` — Method, contributions, comparison to baselines
- `02_architecture.md` — Module map, data flow, hierarchical graph model
- `03_running_locally.md` — Running every script + interpreting output
- `04_webarena_runbook.md` — Hosting WebArena + real exploration
- `06_training.md` — Collect → SFT → fine-tune → evaluate → loop pipeline
- `09_run_on_webarena.md` — Standalone WebArena exploration runtime
