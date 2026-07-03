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
3. Set env:
   ```bash
   export WA_SHOPPING="http://<your-host>:7770"
   export OPENAI_API_KEY="sk-..."           # or OPENAI_BASE_URL for a compatible endpoint
   export HSGE_MODEL="gpt-4o-mini"          # or your model
   ```
   Models can be assigned per helper in `config.yaml`. Each helper inherits any
   omitted field from the shared `llm` block:
   ```yaml
   llm:
     provider: deepseek
     temperature: 0.2
     agents:
       page_explorer:        # propose page-local tasks
         model: deepseek-v4-flash
       solver:               # choose browser actions
         model: deepseek-v4-flash
       trajectory_segmenter: # split successful trajectories into subgoals
         model: deepseek-v4-flash
       skill_abstractor:     # build a SkillCard from a mature cluster
         model: deepseek-v4-flash
       skill_verifier:       # ground and verify a SkillCard
         model: deepseek-v4-flash
       operator_inducer:     # infer planning preconditions/effects
         model: deepseek-v4-flash
   ```
   A role may also override `provider`, `base_url`, or `temperature`. API keys
   remain in `.env` as `${PROVIDER}_API_KEY`. Global CLI flags such as `--model`
   intentionally override every role for quick experiments.
4. Run:
   ```bash
   python run_webarena.py \
       --root-url "$WA_SHOPPING" \
       --out outputs/wa_run \
       --allow "http://<your-host>:7770.*" \
       --max-nodes 15 --max-depth 6 --max-steps 15
   ```

## What happens each node

1. `PageExplorer` proposes local tasks for the page.
2. `Solver` attempts each; successful trajectories are saved and fed to HSGE
   `Discovery`; an operator is mined from the start→end predicate delta.
3. Once mined operators admit a plan to `order_confirmed`, a goal-conditioned
   composed task is proposed, solved, and **terminal-verified** (reward 1 only if
   the run reaches the order-confirmation page).
4. Allowed child links extend the frontier.

## Output

```
outputs/wa_run/episodes/ep_XXXX/
  episode_meta.json        # goal, outcome.success/reward, difficulty, tags
  episode.jsonl            # per-step action + observation path
  page_state/step_*.txt    # AXTree text per step
```
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
