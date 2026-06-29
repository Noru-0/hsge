# 09 — Running HSGE Exploration on WebArena (standalone)

This is the standalone WebArena runtime built into the HSGE project — it is
self-contained and drives a real browser via BrowserGym, proposes and
solves tasks with an LLM, mines operators, composes goal-conditioned tasks, and
writes trajectories that `build_sft_dataset.py` consumes.

## Components (under `hsge/`)

| Module | Role |
| --- | --- |
| `backends.py` | `OpenAILLM` (OpenAI-compatible) + `STEmbedder` (sentence-transformers) |
| `webarena/browser.py` | `WebArenaBrowser` — BrowserGym `openended` wrapper (open URL, read AXTree, act) |
| `webarena/predicates.py` | URL/DOM → canonical predicates + terminal-goal checkers |
| `webarena/agents.py` | `PageExplorer` (task proposal) + `Solver` (action-planner loop) |
| `webarena/runtime.py` | `WebArenaExplorer` — frontier loop, operator mining, goal tasks, persistence |
| `run_webarena.py` | CLI entry point (real run + `--dry-run`) |

## Dry run (no browser, no network) — verify the wiring

```bash
python run_webarena.py --dry-run --out /tmp/wa_dry --max-nodes 2
python build_sft_dataset.py /tmp/wa_dry/episodes train.jsonl
```
Uses a scripted LLM + fake browser to exercise the full loop and persistence.

## Real run on WebArena

1. Host the shopping site and verify it (see `04_webarena_runbook.md`).
2. Install the extras:
   ```bash
   pip install browsergym-core browsergym-webarena openai sentence-transformers
   playwright install chromium
   ```
3. Copy & edit `.env`:
   ```bash
   cp .env.example .env   # then edit .env with your keys
   ```
   Set `LLM_PROVIDER=deepseek` or `LLM_PROVIDER=openai` and fill the corresponding keys.

   **DeepSeek** (OpenAI-compatible, rẻ hơn):
   ```bash
   LLM_PROVIDER=deepseek
   DEEPSEEK_API_KEY=sk-...
   DEEPSEEK_MODEL=deepseek-chat
   ```

   **OpenAI**:
   ```bash
   LLM_PROVIDER=openai
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4o-mini
   ```

   **Dùng model riêng cho explorer (rẻ) & solver (mạnh):**
   ```bash
   EXPLORER_MODEL=deepseek-chat      # hoặc gpt-4o-mini
   SOLVER_MODEL=deepseek-reasoner    # hoặc gpt-4o
   ```

4. Run:
   ```bash
   # Dùng provider từ .env
   # KHÔNG screenshot (mặc định) — text-only, dùng được với DeepSeek & OpenAI
   python run_webarena.py --root-url "http://192.168.1.31:7770/" --out outputs/wa_run --max-nodes 50

   # CÓ screenshot — CẦN model hỗ trợ vision (gpt-4o, gpt-4o-mini)
   python run_webarena.py --provider openai --explorer-model gpt-4o-mini --solver-model gpt-4o \
    --screenshot --root-url "http://192.168.1.31:7770/" --out outputs/wa_run --max-nodes 50

   # Hoặc override provider qua CLI
   python run_webarena.py --provider deepseek --root-url "http://host:7770/" --out outputs/wa_run

   # Dùng model riêng cho explorer & solver
   python run_webarena.py --explorer-model deepseek-chat --solver-model deepseek-reasoner ...

   # Hoặc dùng PowerShell helper (Windows)
   .\run_webarena.ps1 -Provider deepseek
   .\run_webarena.ps1 -Provider openai -ExplorerModel gpt-4o-mini -SolverModel gpt-4o
   ```

   **Các option chính:**

   | Flag | Mô tả |
   | --- | --- |
   | `--provider deepseek\|openai\|custom` | Chọn preset LLM provider |
   | `--model MODEL` | Model cho cả explorer & solver |
   | `--explorer-model MODEL` | Model riêng cho PageExplorer |
   | `--solver-model MODEL` | Model riêng cho Solver |
   | `--root-url URL` | URL gốc WebArena shopping site |
   | `--max-nodes N` | Số node tối đa trong frontier |
   | `--max-depth N` | Độ sâu tối đa |
   | `--max-steps N` | Số bước tối đa mỗi episode |
   | `--dry-run` | Test pipeline không cần browser |

## What happens each node

1. `PageExplorer` proposes local tasks for the page.
2. `Solver` attempts each and stores exact pre/post URL, AXTree-derived predicates,
   semantic target identity, and extractor schema per action. Successful
   trajectories are fed to `Discovery`.
3. Execution verification may admit a reusable skill. Only effects observed in
   enough verification contexts make that skill planner-ready and add an operator.
4. Once mined operators admit a plan to `order_confirmed`, a goal-conditioned
   composed task is proposed, solved, and **terminal-verified** (reward 1 only if
   the run reaches the order-confirmation page).
5. Allowed child links extend the frontier. Prefix replay validates the original
   BID fingerprint and re-grounds a unique changed BID by role/accessibility name.

## Output

```
outputs/wa_run/episodes/ep_XXXX/
  episode_meta.json        # goal, outcome.success/reward, difficulty, tags
  episode.jsonl            # per-step action + observation path
  page_state/step_*.txt    # AXTree text per step
  page_state/final_axtree.txt # exact post-state evidence (new runs)
```

`graph.json`, `curriculum.json`, `curriculum_diagnostics.json`, and
`metrics_latest.json` exist from run start and refresh atomically after every
planner-ready admission. For legacy runs, use
`python remine_planning_artifacts.py SOURCE OUTPUT`; missing final AXTree evidence
is marked incomplete and never converted into a synthetic effect.
Feed straight into training:
```bash
python build_sft_dataset.py outputs/wa_run/episodes train.jsonl
```

## Limits / honesty

- This runtime has **not** been tested against a live WebArena instance from the
  authoring environment (no browser/site there); the dry-run validates the wiring
  and persistence. Expect to tune prompts and `predicates.py` against your real DOM.
- Skill *verification* here is by terminal outcome (did the episode reach the goal
  state), not the mock's held-out-context execution gate.
- Run a single worker; WebArena sites are shared mutable state. Reset between runs.
- Confirm the checkout reaches `checkout/onepage/success` without a real charge, or
  no purchase episode can ever verify.
