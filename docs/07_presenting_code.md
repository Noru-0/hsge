# 07 — Presenting HSGE: A Guided Tour of the Codebase

> **Audience:** Someone new to the project who needs to understand what's
> happening under the hood — concepts, architecture, and where to start reading.
>
> **Time to read:** ~15 minutes.

---

## 1. What does this project do? (30 seconds)

HSGE = **H**ierarchical **S**kill **G**eneration for **E**xploration.

An LLM-powered agent explores a website (like a Magento shop, Wikipedia, or GitLab) by browsing pages, trying small tasks ("search for an item", "add to cart"), and **learning reusable skills** from successful attempts. Over time it chains these skills to accomplish complex goals like "complete a full purchase checkout."

```
                      ┌──────────────┐
                      │   LLM Agent  │
                      │  (GPT-4o)    │
                      └──────┬───────┘
                             │ observes page, decides action
                             ▼
┌──────────┐   browse    ┌──────────┐   mine skills   ┌───────────────┐
│ Website  │ ◄────────── │ Explorer │ ──────────────► │  SkillLibrary │
│ (WebArena│  frontier   │  (BFS)   │                 │  (knowledge)  │
│  Magento)│             └──────────┘                 └───────────────┘
└──────────┘                                               │
      ▲                                                    │ chains skills
      │                       ┌──────────┐                 │
      └───────────────────────│ Planner  │ ◄───────────────┘
          composed task        │ (operators)│
                               └──────────┘
```

---

## 2. The Big Ideas (concepts)

### 2.1 Frontier Exploration (BFS over URLs)

The explorer doesn't know which pages are useful ahead of time. It starts at the home page and follows links breadth-first — but with a twist: it filters URLs by **structural similarity** so it doesn't waste time on 50 nearly-identical subcategory pages.

```
Homepage → 334 links → Filter to 60 diverse links → Process each
                                                       │
  /electronics.html          → explore, mine skills    │
  /checkout/cart             → explore, mine skills    │
  /electronics/camera.html   → explore, mine skills    │
  ...                                                  │
                                                       ▼
                                              Repeat for depth=2,3,...
```

### 2.2 Operator Mining (predicate deltas)

Each successful task produces **predicates** — symbolic descriptions of page state:

```
Task: "add an item to cart"
  Start page:  predicates = {on_product_page, product_listed}
  End page:    predicates = {on_cart_page, item_in_cart, cart_not_empty}

  → Operator:  add_to_cart(start={on_product_page}, end={item_in_cart})
```

These operators form a **plan graph**. Once you have `add_to_cart` and `checkout`, the planner can chain them:

```
Goal = "order_confirmed"
  Plan:  search_product → open_product → add_to_cart → checkout → order_confirmed
```

### 2.3 Skill Library (knowledge that grows)

The system doesn't just execute — it **learns**. Successful trajectories are segmented, abstracted into reusable **skill cards**, verified, and stored:

```python
SkillCard(
    name="add_to_cart",
    description="Click 'Add to Cart' on a product detail page",
    precondition="on_product_page",
    success_predicate="item_in_cart",
    action_template="click add-to-cart button",
    slots=[{"name": "product_name", "slot_type": "string"}],
)
```

Skills are clustered hierarchically so similar skills are merged, preventing bloat.

---

## 3. Project Structure (where is what)

```
hsge_project/
│
├── run_webarena.py          ◄── Entry point: CLI launcher
├── run_webarena.ps1              PowerShell helper
├── clean_frontier.py             Post-hoc frontier analysis tool
├── build_sft_dataset.py          Convert trajectories → training data
│
├── hsge/                         ◄── Core library
│   ├── llm.py                    Abstract LLM interface
│   ├── backends.py               OpenAI / SentenceTransformers impls
│   ├── schema.py                 Data structures (SkillCard, etc.)
│   ├── library.py                SkillLibrary: admission, verification
│   ├── discovery.py              Discovery pipeline: segment → abstract → admit
│   ├── segmentation.py           LLM-based trajectory segmentation
│   ├── abstraction.py            Segment → SkillCard
│   ├── operators.py              Symbolic planning over predicate transitions
│   ├── graph.py                  Hierarchical skill clustering
│   ├── clustering.py             Clustering algorithms
│   ├── verification.py           Skill verification
│   ├── transfer.py               Cross-site skill transfer
│   ├── curriculum.py             Curriculum learning
│   ├── env.py                    Environment abstraction
│   │
│   └── webarena/                 ◄── WebArena-specific subsystem
│       ├── browser.py            BrowserGym wrapper (Playwright)
│       ├── agents.py             PageExplorer + Solver (LLM agents)
│       ├── predicates.py         Page → symbolic predicates
│       ├── runtime.py            Main BFS loop (WebArenaExplorer)
│       └── frontier_filter.py    URL deduplication engine
│
├── docs/                         ◄── Documentation
│   ├── 01_overview.md            High-level project overview
│   ├── 02_architecture.md        HSGE architecture
│   ├── 03_running_locally.md     Local setup
│   ├── 04_webarena_runbook.md    WebArena deployment
│   ├── 05_frontier_filter.md     Filter design (deep dive)
│   ├── 06_code_reference.md      File-by-file API reference
│   ├── 07_presenting_code.md     ◄── This file
│   ├── 09_run_on_webarena.md     Run instructions
│   └── 10_changelog.md           All changes from baseline
│
├── outputs/                      ◄── Run outputs (gitignored)
│   └── wa_run/
│       ├── run.log               Console mirror
│       ├── frontier.jsonl        Frontier snapshots per node
│       ├── skills.json           Admitted skills
│       └── episodes/ep_NNNN/     Trajectory data
│
└── requirements.txt              Dependencies
```

---

## 4. Data Flow: What happens during one exploration node

```
                    NODE LOOP (one URL processed)
                    ═══════════════════════════════

  ① browser = WebArenaBrowser(url)
         │
         ▼
  ② obs = browser.reset()
     → {url, axtree (text), bids (interactive elements), screenshot?}
         │
         ▼
  ③ PageExplorer.propose(obs)
     → ["search for an item", "add an item to cart", "browse category"]
         │
         ▼  (for each proposed task)
  ④ Solver.solve(browser, "search for an item")
         │
         │  ┌─ Web-agent loop ──────────────────────────┐
         │  │  observe → LLM decides → browser.act() →  │
         │  │  repeat up to max_steps=15                 │
         │  └────────────────────────────────────────────┘
         │
         ▼
  ⑤ _record(task, steps, obs_texts, success, screenshots)
     → writes: episodes/ep_NNNN/episode_meta.json
               episodes/ep_NNNN/episode.jsonl
               episodes/ep_NNNN/page_state/step_XXX_axtree.txt
               episodes/ep_NNNN/screenshots/step_XXX.png
         │
         ▼  (if success)
  ⑥ _mine_operator(task, steps, obs_texts, final_obs)
     → extract start/end predicates
     → add Operator to OperatorGraph
         │
  ⑦ discovery.on_trajectory(steps, site=url, task=task)
     → segment_trajectory(steps)          [hsge/segmentation.py]
     → abstract each segment → SkillCard  [hsge/abstraction.py]
     → SkillLibrary.add_or_update(card)   [hsge/library.py]
         │
         ▼
  ⑧ _filter_links(browser.links(), queued)
     → extract_templates(links)           [frontier_filter.py]
     → check global quota per template
     → pick diverse sample
     → add ~2-60 new URLs to frontier
         │
         ▼
  ⑨ browser.close()
```

---

## 5. Where to Start Reading

**If you have 5 minutes** — understand the core loop:

1. `hsge/webarena/runtime.py` — `WebArenaExplorer.run()` (the `while frontier` loop)
2. `hsge/webarena/agents.py` — `Solver.solve()` (the web-agent loop)

**If you have 15 minutes** — add the learning pipeline:

3. `hsge/discovery.py` — `Discovery.on_trajectory()` (trajectory → skill)
4. `hsge/operators.py` — `OperatorGraph` and `plan()` (composing tasks)

**If you have 30 minutes** — understand the whole system:

5. `hsge/library.py` — `SkillLibrary` (skill admission & verification)
6. `hsge/webarena/frontier_filter.py` — `extract_templates()` (URL dedup)
7. `hsge/schema.py` — data structures
8. `run_webarena.py` — how it all wires together

**Deep dive** (when you need to modify):

9. `hsge/segmentation.py` — LLM trajectory segmentation
10. `hsge/abstraction.py` — segment → SkillCard abstraction
11. `hsge/backends.py` — OpenAI API integration
12. `hsge/webarena/browser.py` — BrowserGym/Playwright wrapper

---

## 6. Key Configuration Points

| What | Where | Example |
|------|-------|---------|
| LLM provider & model | `.env` or CLI args | `--provider openai --model gpt-4o` |
| Separate explorer/solver models | `.env` or CLI args | `--explorer-model gpt-4o-mini --solver-model gpt-4o` |
| WebArena URL | CLI arg | `--root-url "http://host:7770/"` |
| Max nodes to explore | CLI arg | `--max-nodes 30` |
| Max depth | CLI arg | `--max-depth 6` |
| Frontier filter budget | `runtime.py` `_frontier_max` | Default: 60 URLs per node |
| Template quota | `runtime.py` `_template_max` | Default: 2 URLs per template |
| Screenshots (vision) | CLI flag | `--screenshot` |
| WebArena accounts | `.env` | `WA_ACCOUNT_SHOPPING_USERNAME=...` |

---

## 7. Glossary

| Term | Meaning |
|------|---------|
| **Frontier** | Queue of (URL, depth) pairs to visit next. Processed BFS. |
| **Operator** | A predicate transition: "if page has X, doing Y leads to Z". |
| **SkillCard** | A learned, reusable skill: name, description, precondition, action template. |
| **Predicate** | A symbolic fact about a page, e.g. `on_product_page`, `cart_not_empty`. |
| **Template** | URL structure with variables replaced: `/electronics/{slug}.html`. |
| **Episode** | One trajectory — a task attempt from start to finish. |
| **Segment** | A sub-sequence of a trajectory linked to one skill. |
| **Axtree** | Flattened accessibility tree of the page (text representation of DOM). |
| **BID** | BrowserGym interactive element ID — used in actions like `click('a51')`. |

---

## 8. Common Questions

**Q: Why filter the frontier? Why not visit every page?**
A: A Magento shop has 300+ links from the homepage, 90% are structurally identical subcategories. Exploring 2-3 per category gives the same information as all 50. The frontier filter reduces 334 URLs to ~60 without losing coverage.

**Q: What's the difference between `PageExplorer` and `Solver`?**
A: `PageExplorer` is cheap (can use `gpt-4o-mini`) — it just looks at the page and says "here are 3 things you could try". `Solver` is expensive (should use `gpt-4o`) — it actually executes the task step-by-step.

**Q: How does the system know if a task succeeded?**
A: `Solver.solve()` checks if the `goal_predicate` is satisfied on the final page (via `predicates.py:reached()`). For composed tasks, the terminal goal is `"order_confirmed"`.

**Q: Can this work on sites other than Magento?**
A: Yes. The frontier filter and predicate extractor are domain-agnostic. The system has been designed to work on Wikipedia, GitLab, and any HTML-based website via BrowserGym.

**Q: Where are the API keys?**
A: In `.env` (not committed to git). Copy `.env.example` → `.env` and fill in your keys.
