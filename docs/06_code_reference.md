# 06 — Code Reference: File-by-File Walkthrough

> Each source file explained: what it does, key inputs/outputs, and how
> the files call each other during an exploration run.

---

## Table of Contents

1. [Call Flow (end-to-end)](#1-call-flow-end-to-end)
2. [Entry Points](#2-entry-points)
3. [WebArena Subsystem](#3-webarena-subsystem)
4. [Core HSGE Library](#4-core-hsge-library)
5. [Supporting Files](#5-supporting-files)

---

## 1. Call Flow (end-to-end)

```
$ python run_webarena.py --root-url "http://host:7770/" --out outputs/wa_run

  run_webarena.py:main()
  │
  ├─ ① Parse CLI args, resolve provider, load .env
  │     → api_key, base_url, explorer_model, solver_model
  │
  ├─ ② Create LLMs & Embedder
  │     │
  │     ├─ OpenAILLM(api_key, base_url, model)   ← hsge/backends.py
  │     └─ STEmbedder()                           ← hsge/backends.py
  │
  ├─ ③ Create browser factory
  │     └─ lambda url: WebArenaBrowser(url)       ← hsge/webarena/browser.py
  │
  ├─ ④ Create WebArenaExplorer(...)               ← hsge/webarena/runtime.py
  │     │
  │     ├─ PageExplorer(explorer_llm)             ← hsge/webarena/agents.py
  │     ├─ Solver(solver_llm)                     ← hsge/webarena/agents.py
  │     ├─ SkillLibrary(llm, embedder)            ← hsge/library.py
  │     ├─ HierarchicalGraph()                    ← hsge/graph.py
  │     ├─ Discovery(library, graph)              ← hsge/discovery.py
  │     └─ OperatorGraph()                        ← hsge/operators.py
  │
  └─ ⑤ explorer.run(root_url)
        │
        │  ┌─────────────────── while frontier ───────────────────────┐
        │  │                                                           │
        │  │  ⑥ browser = browser_factory(url)                        │
        │  │  ⑦ obs = browser.reset()                                 │
        │  │     → {url, axtree, bids, screenshot_base64}             │
        │  │                                                           │
        │  │  ⑧ for task in explorer.explorer.propose(obs):           │
        │  │       → PageExplorer uses LLM to suggest local tasks     │
        │  │                                                           │
        │  │  ⑨ steps, obs_texts, final_obs, success =                │
        │  │         explorer.solver.solve(browser, task)              │
        │  │       → Solver runs web-agent loop (LLM decides actions) │
        │  │                                                           │
        │  │  ⑩ explorer._record(task, steps, ...)                    │
        │  │       → persist trajectory to episodes/ep_NNNN/          │
        │  │                                                           │
        │  │  ⑪ if success:                                           │
        │  │       explorer._mine_operator(task, ...)                  │
        │  │         → extract start/end predicates                   │
        │  │         → add Operator to OperatorGraph                  │
        │  │       explorer.discovery.on_trajectory(steps, ...)        │
        │  │         → segment → abstract → add to SkillLibrary       │
        │  │                                                           │
        │  │  ⑫ explorer._filter_links(browser.links(), queued)       │
        │  │       → template clustering + global quota               │
        │  │       → add ~2-60 filtered URLs to frontier              │
        │  │                                                           │
        │  │  ⑬ browser.close()                                       │
        │  └───────────────────────────────────────────────────────────┘
        │
        └─ outputs/wa_run/
             ├─ run.log               (console mirror)
             ├─ frontier.jsonl        (per-node frontier snapshots)
             ├─ skills.json           (admitted skills)
             └─ episodes/ep_NNNN/
                  ├─ episode_meta.json
                  ├─ episode.jsonl
                  ├─ page_state/step_XXX_axtree.txt
                  └─ screenshots/step_XXX.png (if --screenshot)
```

---

## 2. Entry Points

### `run_webarena.py`
**Purpose**: CLI launcher for WebArena exploration.

| Aspect | Detail |
|--------|--------|
| **Input** | CLI args (`--root-url`, `--provider`, `--model`, `--max-nodes`, ...) + `.env` file |
| **Output** | Calls `WebArenaExplorer.run()`; produces `outputs/wa_run/` directory |
| **Key functions** | `_load_dotenv()`, `_resolve_models()`, `_resolve_api_config()`, `main()` |
| **Calls** | `WebArenaBrowser`, `OpenAILLM`, `STEmbedder`, `WebArenaExplorer` |

### `run_webarena.ps1`
**Purpose**: PowerShell convenience wrapper with provider presets.

### `clean_frontier.py`
**Purpose**: Post-hoc frontier analysis — reads `frontier.jsonl`, applies
`filter_frontier()`, writes `frontier_clean.jsonl`.

| Aspect | Detail |
|--------|--------|
| **Input** | `outputs/wa_run/frontier.jsonl` |
| **Output** | `outputs/wa_run/frontier_clean.jsonl` (filtered + per-node stats) |
| **Key function** | `main()` |
| **Calls** | `filter_frontier()` from `hsge/webarena/frontier_filter.py` |

### `analyze_frontier.py`
**Purpose**: Diagnostic tool — prints template breakdown for a single node's frontier.

### `build_sft_dataset.py`
**Purpose**: Converts episode trajectories into supervised fine-tuning (SFT) training
examples for the web agent. Reads `episodes/` directory, outputs dataset JSONL.

---

## 3. WebArena Subsystem (`hsge/webarena/`)

### `hsge/webarena/browser.py` — `WebArenaBrowser`
**Purpose**: Thin wrapper around BrowserGym's `browsergym/openended` environment.
Provides free-form web browsing (start at any URL, execute arbitrary actions).

| Aspect | Detail |
|--------|--------|
| **Input** | `start_url: str`, `headless: bool`, `timeout_ms: int`, `screenshot: bool` |
| **Key methods** | |
| `reset()` | Opens browser at `start_url`, returns `observation()` dict |
| `observation()` | Returns `{url, axtree (flattened), bids, screenshot_base64}` |
| `act(action)` | Executes a BrowserGym action string, returns new observation |
| `links()` | Extracts all `<a href>` from live DOM via Playwright, same-origin only |
| `close()` | Closes the browser environment |
| **Key output** | `dict` with page state; `links()` returns `list[str]` |
| **Called by** | `WebArenaExplorer.run()` |

### `hsge/webarena/agents.py` — `PageExplorer`, `Solver`
**Purpose**: LLM-powered agents for task proposal and execution.

#### `PageExplorer`
| Aspect | Detail |
|--------|--------|
| **Input** | `observation: dict` (from `WebArenaBrowser.observation()`) |
| **Key method** | `propose(obs) → list[str]`: asks LLM to suggest 2-3 short tasks visible on the current page (e.g., "search for an item", "add item to cart"). System prompt: `PROPOSE_TASKS` |
| **LLM call** | `llm.complete_json(system, prompt)` |

#### `Solver`
| Aspect | Detail |
|--------|--------|
| **Input** | `browser: WebArenaBrowser`, `task: str`, `goal_predicate: str` |
| **Key method** | `solve(browser, task, goal_predicate) → tuple[steps, obs_texts, final_obs, success, screenshots]` |
| **Behavior** | Web-agent loop: observe → LLM decides action → execute → repeat up to `max_steps`. Uses `complete_vision_json()` when screenshots available, else `complete_json()`. System prompt includes: `SOLVER`, web-agent instructions, account hints (`_accounts_hint()`), goal predicate. |
| **LLM call** | `llm.complete_json()` or `llm.complete_vision_json()` |

### `hsge/webarena/predicates.py`
**Purpose**: Extracts symbolic predicates from a page (URL + axtree).

| Key function | Detail |
|--------------|--------|
| `predicates_from(url, axtree) → frozenset[str]` | Parses page state into reusable predicates like `at_checkout`, `cart_has_items`, `on_product_page`. Used for operator mining (start → end predicate delta). |
| `reached(goal_predicate, obs) → bool` | Checks if a goal condition is satisfied on the current page. |

### `hsge/webarena/frontier_filter.py` — **Template Clustering Engine**
**Purpose**: Domain-agnostic URL deduplication. See `docs/05_frontier_filter.md`
for full design document.

| Key function | Input | Output |
|--------------|-------|--------|
| `extract_templates(urls)` | `list[str]` | `dict[str, list[str]]` (template → URLs) |
| `template_priority(tmpl, size)` | `str, int` | `float` (higher = more important) |
| `filter_frontier(frontier, max_output)` | `list[dict]` | `list[dict]` (filtered) |

**Called by**: `WebArenaExplorer._filter_links()`, `clean_frontier.py`

### `hsge/webarena/runtime.py` — `WebArenaExplorer`
**Purpose**: The main orchestration loop. Drives the entire WebArena exploration
process — a frontier-based BFS over URLs that interleaves local task execution,
operator mining, goal-conditioned planning, and HSGE skill discovery.

**What it does (high-level flow):**
1. Start from a `root_url`, maintain a **frontier** (BFS queue) of URLs to visit.
2. At each page, use `PageExplorer` to **propose local tasks** (e.g. "search for
   an item", "add to cart") and solve each with the `Solver` agent.
3. From successful local trajectories, **mine operators** — extract the predicate
   delta (`predicates_from(start_state)` → `predicates_from(end_state)`) and
   register it as an `Operator` in the `OperatorGraph`.
4. Feed successful trajectories into HSGE `Discovery` for skill library building.
5. Once operators exist, **compose a goal-conditioned task** by running a BFS
   planner (`plan()`) over the operator graph toward `terminal_goal` (default:
   `"order_confirmed"`). Solve this composed task with the `Solver`.
6. **Expand the frontier** by collecting all same-origin links from the current
   page and adding those matching `allow_pattern`.
7. Persist every trajectory (both local and goal) in a run-dir layout that
   `build_sft_dataset.py` can read directly.

**Key design insight**: Operators are mined from *predicate deltas* (what changed
between start and end state), not from raw actions. This symbolic abstraction lets
the planner compose long-horizon purchase chains (search → select → cart →
checkout → payment → confirm) from independently-mined page-local operators.

| Aspect | Detail |
|--------|--------|
| **Constructor inputs** | `browser_factory` (callable `url → WebArenaBrowser`), `llm` (for agents), `embedder` (for skill library), `out_dir: str`, `allow_pattern: str` (regex for link filtering), `max_depth: int=6`, `max_nodes: int=20`, `max_steps: int=15`, `terminal_goal: str="order_confirmed"` |
| **Key method** | `run(root_url: str)` — the main BFS frontier loop |
| **Inner methods** | |
| `_record(goal, steps, obs_texts, success, difficulty, tag)` | Persists a trajectory to `episodes/ep_NNNN/` with `episode_meta.json` (goal, outcome, metadata) and `episode.jsonl` (per-step actions + observations). Also writes AXTree snapshots to `page_state/step_NNN_axtree.txt`. Compatible with `build_sft_dataset.py`. |
| `_mine_operator(goal, steps, obs_texts, final_obs)` | Extracts predicates from first-step state and final state → computes delta `end - start` → creates `Operator(name, frozenset(start), frozenset(effects), terminal=...)` and adds to `OperatorGraph`. Operator name is inferred from goal text via `_name_from_goal()`. |
| `_goal_task()` | Calls `plan(opgraph, ∅, terminal_goal)` — BFS over operators from empty initial state toward `"order_confirmed"`. Returns `{"goal": "...", "difficulty": len(chain), "chain": [...]}` or `None` if no plan exists yet. |
| **Output** | `{out_dir}/` directory with `episodes/ep_NNNN/` subdirectories (each containing `episode_meta.json`, `episode.jsonl`, `page_state/`). Skills and operators accumulate in-memory in `self.library` and `self.opgraph`. |
| **Calls** | `PageExplorer.propose(obs)`, `Solver.solve(browser, task)`, `predicates_from()`, `OperatorGraph.add()`, `plan()`, `Discovery.on_trajectory()`, `browser.links()`, `browser.reset()`, `browser.close()` |

---

## 4. Core HSGE Library (`hsge/`)

### `hsge/llm.py` — `LLM`, `Embedder`
**Purpose**: Abstract base classes for LLM and embedding interfaces.

| Class | Key methods | Detail |
|-------|-------------|--------|
| `LLM` | `complete_json()`, `complete_vision_json()`, `complete_text()` | Abstract; `complete_vision_json()` has fallback to `complete_json()` |
| `Embedder` | `embed(texts) → list[list[float]]` | Abstract |

### `hsge/backends.py` — `OpenAILLM`, `STEmbedder`, `HashingEmbedder`
**Purpose**: Concrete LLM and embedder implementations.

| Class | Detail |
|-------|--------|
| `OpenAILLM` | OpenAI-compatible API. Supports `complete_json()`, `complete_vision_json()` (multimodal), `complete_text()`. Handles null content, list-of-blocks responses. |
| `STEmbedder` | Sentence-Transformers embedding (`all-MiniLM-L6-v2` by default) |
| `HashingEmbedder` | Deterministic hash-based embedding (for dry-run) |

### `hsge/schema.py` — `SkillCard`, `TrajectoryStep`, `Segment`
**Purpose**: Core data structures.

| Class | Fields |
|-------|--------|
| `SkillCard` | `skill_id, name, description, precondition, success_predicate, action_template, slots, cluster_id, stats` |
| `TrajectoryStep` | `url, obs_summary, action, ...` |
| `Segment` | Span within a trajectory, linked to a skill |

### `hsge/library.py` — `SkillLibrary`
**Purpose**: Manages skill cards — admission, verification, retrieval.

| Key method | Detail |
|------------|--------|
| `add_or_update(card)` | Tries to admit a new skill with verification |
| `_try_admit(cid, ...)` | Abstracts skill → verifies → admits or rejects |
| `all_skills() → list[SkillCard]` | Returns all verified skills |
| `_on_admit` | Optional callback (set by `WebArenaExplorer`) |

### `hsge/discovery.py` — `Discovery`
**Purpose**: Processes raw trajectories into skills. Entry point for the HSGE pipeline.

| Key method | Detail |
|------------|--------|
| `on_trajectory(steps, site, task)` | Segment → abstract → add to `SkillLibrary` |
| **Calls** | `segment_trajectory()` → `SkillCard` abstraction → `SkillLibrary.add_or_update()` |

### `hsge/segmentation.py`
**Purpose**: Splits a raw trajectory into semantically meaningful segments.

| Key function | Detail |
|--------------|--------|
| `segment_trajectory(steps) → list[Segment]` | LLM-based segmentation. Validates span bounds; skips malformed segments. |

### `hsge/abstraction.py`
**Purpose**: Converts a trajectory segment into a reusable `SkillCard`.

| Key function | Detail |
|--------------|--------|
| Abstract a segment into `{name, description, precondition, ...}` | LLM-based. Returns `None` if abstraction fails (defensive). |

### `hsge/operators.py` — `Operator`, `OperatorGraph`, `plan()`
**Purpose**: Symbolic planning over predicate transitions for task composition.

| Class/Function | Detail |
|----------------|--------|
| `Operator(name, preconditions, effects, terminal)` | A predicate transition: `start_state → end_state` |
| `OperatorGraph` | Collection of operators with `add(op)` method |
| `plan(graph, start_predicates, goal_predicate) → list[Operator]` | Chains operators to reach a terminal goal |
| `plan(graph, start, goal)` | Used by `_goal_task()` to compose purchase chain |

### `hsge/graph.py` — `HierarchicalGraph`
**Purpose**: Hierarchical clustering of skills. Used internally by `Discovery`.

### `hsge/clustering.py`
**Purpose**: Skill clustering algorithms. Used by `SkillLibrary` for deduplication.

### `hsge/transfer.py` — `transfer_...`
**Purpose**: Cross-site skill transfer. (Not used in current WebArena run.)

### `hsge/curriculum.py`
**Purpose**: Deterministic goal-conditioned curriculum generation. It plans from
the initial predicate set to every reachable operator effect, emits one task per
goal, and marks tasks whose goal is a terminal operator effect. `max_len` is an
optional compatibility filter; production export does not truncate plan length.

### `hsge/env.py`
**Purpose**: Environment abstraction layer.

### `hsge/verification.py`
**Purpose**: Skill verification logic. Called by `SkillLibrary` during admission.

---

## 5. Supporting Files

| File | Purpose |
|------|---------|
| `requirements.txt` | Python dependencies |
| `README.md` | Project overview |
| `.env` / `.env.example` | API keys, model config, WebArena accounts |
| `.gitignore` | Excludes outputs, env, caches |
| `docs/01_overview.md` | High-level project description |
| `docs/02_architecture.md` | HSGE architecture |
| `docs/03_running_locally.md` | Local setup instructions |
| `docs/04_webarena_runbook.md` | WebArena deployment guide |
| `docs/05_frontier_filter.md` | Frontier filter design document |
| `docs/06_code_reference.md` | ← This file |
| `docs/09_run_on_webarena.md` | WebArena run instructions |
| `docs/10_changelog.md` | All modifications from baseline |
| `demo.py`, `demo_shopping.py`, etc. | Demo scripts |
| `compare.py`, `compare_three_way.py` | Comparison/evaluation scripts |
| `explore.py` | Exploration utilities |

---

## Quick Reference: Which file calls which

```
run_webarena.py
  └─ hsge/webarena/runtime.py  (WebArenaExplorer)
       ├─ hsge/webarena/browser.py     (WebArenaBrowser)
       ├─ hsge/webarena/agents.py      (PageExplorer, Solver)
       │    └─ hsge/backends.py        (OpenAILLM)
       │         └─ hsge/llm.py        (LLM base)
       ├─ hsge/webarena/predicates.py  (predicates_from, reached)
       ├─ hsge/webarena/frontier_filter.py  (extract_templates, _sample_diverse)
       ├─ hsge/library.py             (SkillLibrary)
       │    ├─ hsge/schema.py         (SkillCard)
       │    ├─ hsge/clustering.py
       │    └─ hsge/verification.py
       ├─ hsge/discovery.py           (Discovery)
       │    ├─ hsge/segmentation.py
       │    └─ hsge/abstraction.py
       ├─ hsge/operators.py           (OperatorGraph, plan)
       └─ hsge/graph.py               (HierarchicalGraph)
```
