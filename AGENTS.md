# AGENTS.md — Agent Instructions for HSGE

## Project

**HSGE** — Hierarchical Skill-Graph Exploration. A research framework for web agents
that discover reusable, verified skills during exploration and compose them into
long-horizon tasks (e.g. purchases). Maintains a two-level graph: concrete
page-state/action nodes at the low level, abstract skill nodes with
precondition/effect edges at the high level.

The whole pipeline runs with deterministic mock backends — no API keys, GPU, or
live browser needed for development and testing.

## Agent Rules

1. **Always run from the project root** (the directory containing `hsge/`). Set
   `PYTHONPATH=.` when running tests or scripts.

2. **Use mock backends by default.** The pipeline uses `MockLLM` and
   `HashingEmbedder` in `hsge/llm.py`. Do not swap to real backends unless
   explicitly asked.

3. **Tests use pytest.** Run them with:
   ```bash
   python -m pytest hsge/tests/ -v
   ```
   Individual test file:
   ```bash
   python -m pytest hsge/tests/test_clustering.py -v
   ```

4. **No external services required for dev.** The mock demos (`explore.py`,
   `demo.py`, `demo_shopping.py`, `demo_purchase.py`, `compare.py`) all run
   offline.

5. **When editing `hsge/` modules**, keep the pluggable-backend pattern: abstract
   base classes in `llm.py` (`LLM`, `Embedder`) and `env.py` (`WebEnv`) with mock
   subclasses. Real backends subclass these ABCs.

6. **Schema stability.** Core data structures live in `hsge/schema.py` (`Step`,
   `SubTrajectory`, `SkillCard`, `ParamSlot`, `Task`). Changing these affects the
   entire pipeline — check all consumers before modifying.

7. **Outputs are in `outputs/`.** Each run creates a directory like
   `outputs/wa_run_XX/` containing `coverage.json`, `domain.json`,
   `frontier.jsonl`, `skills.json`, and `episodes/`.

8. **WebArena integration** lives in `hsge/webarena/`. The standalone runtime is
   `run_webarena.py`. Dry-run mode (`--dry-run`) needs no live WebArena instance.

9. **Domain generality.** All improvements, abstractions, and heuristics must be
   domain-agnostic. Never hardcode assumptions about specific web domains (e.g.
   shopping, forums, documentation). Skills, clustering, segmentation, and
   planning must transfer across unrelated sites without modification. If a
   change would only help one domain, it belongs in a domain-specific config or
   plugin, not in the core pipeline.

## Build & Test Commands

```bash
# Install (minimal)
pip install numpy

# Install (full, for WebArena real runs)
pip install -r requirements.txt
pip install browsergym-core browsergym-webarena sentence-transformers openai

# Run all tests
python -m pytest hsge/tests/ -v

# Run demos (mock, offline)
python explore.py
python demo.py
python demo_shopping.py
python demo_purchase.py
python compare.py

# WebArena dry-run (no live instance needed)
python run_webarena.py --dry-run --out /tmp/test_dry --max-nodes 2

# WebArena real run (requires live WebArena shopping site)
python run_webarena.py --provider deepseek --root-url "http://host:7770/" --out outputs/wa_run --max-nodes 50
python run_webarena.py --provider openai --explorer-model gpt-4o-mini --solver-model gpt-4o \
  --screenshot --root-url "http://host:7770/" --out outputs/wa_run --max-nodes 50

# Build SFT dataset from collected trajectories (Go-Browse style: JSON + narrative thought)
python build_sft_dataset.py outputs/wa_run/episodes train.jsonl --action-format webarena_json

# Multi-turn: one sample per trajectory
python build_sft_dataset.py outputs/wa_run/episodes train.jsonl --action-format webarena_json --multiturn
```

## Module Map (quick reference)

| Module | Role |
|--------|------|
| `hsge/schema.py` | Core data types: `Step`, `SubTrajectory`, `SkillCard`, `Task` |
| `hsge/llm.py` | Pluggable LLM + Embedder backends with mocks |
| `hsge/env.py` | Browser environment abstraction + mock store pages |
| `hsge/segmentation.py` | Trajectory → candidate sub-trajectories |
| `hsge/clustering.py` | Streaming nonparametric clusterer (cosine-threshold / DP-means) |
| `hsge/abstraction.py` | Cluster → parameterized `SkillCard` |
| `hsge/verification.py` | Ground + execute + ≥k-success admission gate |
| `hsge/library.py` | SkillLibrary: observe → cluster → abstract → verify → admit |
| `hsge/graph.py` | Two-level hierarchical graph (state nodes + skill nodes) |
| `hsge/operators.py` | Skills as precondition/effect operators + BFS planner |
| `hsge/transfer.py` | Cross-domain skill transfer (retrieve → reground → verify) |
| `hsge/curriculum.py` | Compose skills, order by difficulty |
| `hsge/discovery.py` | Online hook into exploration loop |
| `hsge/webarena/` | WebArena integration: browser, agents, scoring, frontier filter |

### WebArena Flags (key)

| Flag | Description |
|------|-------------|
| `--provider deepseek\|openai` | LLM provider preset |
| `--model MODEL` | Model for both explorer & solver |
| `--explorer-model MODEL` | PageExplorer model |
| `--solver-model MODEL` | Solver model |
| `--root-url URL` | WebArena shopping site root |
| `--max-nodes N` | Max frontier nodes |
| `--screenshot` | Enable vision (needs vision-capable model) |
| `--dry-run` | Test pipeline without browser |

## Key Design Patterns

- **Pluggable backends:** `LLM`, `Embedder`, `WebEnv` are ABCs. Mocks are
  deterministic. Real backends subclass and override `complete_json` / `encode` /
  `reset`+`step`+`check`.

- **Verification-gated admission:** A discovered skill is a hypothesis. It enters
  the library only after ≥k successful executions in held-out contexts.

- **Streaming clustering:** `OnlineClusterer` in `clustering.py` processes
  sub-trajectories one at a time — no batch, no fixed k.

- **Precondition/effect planning:** `plan()` in `operators.py` does BFS over the
  operator graph to find chains from current state to goal predicate.

## Documentation

All docs are in `docs/`. Start with `01_overview.md` → `02_architecture.md` →
`03_running_locally.md`. WebArena-specific: `04_webarena_runbook.md`,
`09_run_on_webarena.md`. Training pipeline: `06_training.md`.
