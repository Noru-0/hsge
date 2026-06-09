# 02 — Architecture

## Layers

- **Backends (mockable):** `llm.py` (LLM for segmentation/abstraction/grounding +
  embedder for clustering), `env.py` (browser environment; `reset`/`step`/`check`).
- **Discovery pipeline:** `segmentation.py` → `clustering.py` → `abstraction.py` →
  `verification.py` → `library.py`.
- **Hierarchical graph:** `graph.py` (state + skill nodes/edges), `operators.py`
  (precondition/effect skills + planner).
- **Generation & reuse:** `curriculum.py` (compose easy→hard), `transfer.py`
  (retrieve + reground + verify on a new site).
- **Online hook:** `discovery.py` — call `Discovery.on_trajectory(...)` from inside
  an exploration loop.
- **Baselines & tooling:** `flat_baseline.py`, `awm_baseline.py`, the `compare_*`
  and `demo_*` scripts, `explore.py`, `build_sft_dataset.py`.

## Module map

| File | Role |
| --- | --- |
| `schema.py` | `Step`, `SubTrajectory`, `SkillCard` (option ⟨I,π,β⟩), `Task` |
| `clustering.py` | streaming nonparametric clusterer (cosine-threshold / DP-means) |
| `segmentation.py` | URL-boundary + LLM trajectory segmentation |
| `abstraction.py` | lift a cluster → parameterized `SkillCard` |
| `verification.py` | ground + execute + ≥k-success admission gate |
| `library.py` | observe→cluster→abstract→verify→admit, retrieval, pruning |
| `graph.py` | low-level state graph + high-level skill nodes/edges |
| `operators.py` | skills as preconditions/effects + BFS planner |
| `transfer.py` | retrieve → re-ground → verify on a new site |
| `curriculum.py` | compose skills, order by difficulty |
| `discovery.py` | the online hook into an exploration loop |
| `llm.py`, `env.py` | pluggable backends + deterministic mocks |
| `flat_baseline.py`, `awm_baseline.py` | comparison baselines |

## Data flow

```
exploration loop (env)
  -> trajectories (Step lists)
     -> segmentation        -> candidate SubTrajectories
        -> online clustering -> growing clusters
           -> abstraction    -> parameterized SkillCard (hypothesis)
              -> verification -> admit iff >= k successes in held-out contexts
                 -> SkillLibrary + HierarchicalGraph (skill nodes, skill->skill edges)
                    -> curriculum (plan to goal predicates, easy->hard)
                    -> transfer  (retrieve + reground + verify on new sites)
```

## The hierarchical graph

Two levels. Low: state nodes (URLs/DOM states) and trajectory edges — the flat
exploration graph. High: skill nodes (options) wired to the low level by initiation
(state→skill) and effect (skill→state) edges, plus `skill→skill` composition edges
derived from precondition/effect matching. Planning over the high-level graph turns
"collect a transaction" into a graph search to a terminal predicate.

## Swapping in real backends

- **LLM** (`llm.py`): subclass `LLM.complete_json` (Claude/OpenAI sketches in the docstring).
- **Embedder** (`llm.py`): subclass `Embedder.encode` (e.g. sentence-transformers).
- **Environment** (`env.py`): subclass `WebEnv` over BrowserGym/WebArena; the
  pipeline only needs `reset()`, `step(action)`, `check(predicate)`.
