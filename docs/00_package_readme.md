# HSGE — Hierarchical Skill-Graph Exploration

**HSGE** is a framework for building web agents that discover *reusable, verified
skills* during exploration and *compose* them into long-horizon tasks.

HSGE maintains a two-level graph. The low level is concrete page states and
actions; the high level is abstract skills whose precondition/effect edges let
the system plan composed tasks of increasing difficulty. Skills are discovered
online, admitted only after they execute successfully, and transferred to unseen
sites.

Core ideas:
- **Online skill discovery** — recurring sub-trajectories are clustered into
  reusable skills *during* exploration (nonparametric, no fixed cluster count).
- **Verification-gated admission** — a discovered skill enters the library only
  after it *executes successfully* in held-out contexts. Unverified inductions
  are rejected and decayers are pruned.
- **Hierarchical skill graph** — skills are options ⟨I, π, β⟩ wired to the
  low-level graph with `skill→skill` composition edges derived from
  precondition/effect matching.
- **Cross-domain transfer** — verified skills are retrieved and re-grounded on
  unseen sites with no fresh exploration.
- **Curriculum generation** — planning over the skill graph emits easy→hard
  tasks; the deepest chains are full transactions (e.g. a purchase).

This repo is a *runnable skeleton*: every component has a clean interface and a
deterministic **mock backend**, so the whole pipeline executes with no API keys,
no GPU, and no live browser. Swap the mocks for real backends to scale up.

```
pip install numpy
python demo.py                # login/search domain, full discover->verify->transfer
python demo_shopping.py       # shopping domain, plan->execute->verify a purchase
python demo_purchase.py       # planning + curriculum only (operator model)
python compare_three_way.py   # Flat baseline vs AWM vs HSGE on identical input
PYTHONPATH=. python hsge/tests/test_clustering.py   # tests
```

## Module map

| File | Role |
|------|------|
| `schema.py` | `Step`, `SubTrajectory`, `SkillCard` (option ⟨I,π,β⟩), `Task` |
| `clustering.py` | streaming nonparametric clusterer (cosine-threshold / DP-means style) |
| `segmentation.py` | URL-boundary + LLM trajectory segmentation |
| `abstraction.py` | lift a cluster → parameterized skill |
| `verification.py` | ground + execute + ≥k-success admission gate |
| `library.py` | observe→cluster→abstract→verify→admit, retrieval, pruning |
| `graph.py` | low-level state graph + high-level skill nodes/edges |
| `operators.py` | skills as preconditions/effects + planner (composition) |
| `transfer.py` | retrieve → re-ground → verify on a new site |
| `curriculum.py` | compose skills, order by difficulty |
| `discovery.py` | the online hook called from inside an exploration loop |
| `llm.py`, `env.py` | pluggable backends + deterministic mocks |
| `flat_baseline.py`, `awm_baseline.py` | baselines for the comparison harness |

## Swapping in real backends

- **LLM** (`llm.py`): subclass `LLM.complete_json` (Claude/OpenAI sketches in the docstring).
- **Embedder** (`llm.py`): subclass `Embedder.encode` with sentence-transformers.
- **Environment** (`env.py`): subclass `WebEnv` over a real browser-automation env;
  the pipeline only needs `reset()`, `step(action)`, `check(predicate)`.

## Design notes a reviewer will probe

- **No fixed k.** Clustering is nonparametric; the one knob is an interpretable
  cosine cutoff.
- **Verification is the quality story.** Skills must execute before entering the
  library; this distinguishes HSGE from offline workflow-induction methods that
  reuse unverified inductions.
- **Cost accounting.** Discovery and verification call the LLM; efficiency claims
  must net out that overhead.
