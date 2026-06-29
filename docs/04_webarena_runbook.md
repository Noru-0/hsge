# Runbook — Hosting WebArena for HSGE Exploration

A step-by-step guide to stand up WebArena and point HSGE exploration at it. Sites are self-hosted; once the
URLs and env vars are set, the existing CLI drives the frontier loop.

> Your pipeline uses **BrowserGym**, so you need the **`WA_`-prefixed** environment
> variables (BrowserGym wrappers), not the raw WebArena ones.

---

## 0. Prerequisites

- A host with Docker (local workstation or a cloud box). WebArena sites are heavy;
  budget ~16 GB RAM and tens of GB disk if hosting all of them. Shopping-only is lighter.
- Python 3.10+ for the agent side.
- An OpenAI-compatible LLM endpoint + key for the LLM agents.
- For collection you mostly need the **shopping** site (OneStopShop / Magento).

---

## 1. Host the WebArena sites

WebArena is not a hosted service — you run the dockerized websites yourself. The
WebArena repo ships Docker resources and an AWS AMI.

- Repo + hosting guide: https://github.com/web-arena-x/webarena (see its
  "host your own environment" page).
- Bring up at least the shopping site. Typical default ports (raw WebArena):

  | Site | Default port |
  | --- | --- |
  | shopping (OneStopShop) | 7770 |
  | shopping_admin (Magento admin) | 7780/admin |
  | reddit / forum | 9999 |
  | gitlab | 8023 |
  | map | 3000 |
  | wikipedia | 8888 |
  | homepage | 4399 |

Whatever ports you expose, you'll map them into the `WA_*` variables below.

Smoke-test connectivity before going further:

```bash
curl -I "$WA_SHOPPING"        # expect HTTP 200/302 from the storefront
```

---

## 2. Install the BrowserGym integration

```bash
pip install browsergym-webarena
playwright install chromium
```

---

## 3. Set environment variables

Put these in the env file your CLI loads via `load_env_file()` (e.g. `.env`):

```bash
BASE_URL=http://your-server

# WebArena URLs for BrowserGym (ports must match how you hosted them)
export WA_SHOPPING="$BASE_URL:7770/"
export WA_SHOPPING_ADMIN="$BASE_URL:7780/admin"
export WA_REDDIT="$BASE_URL:9999"
export WA_GITLAB="$BASE_URL:8023"
export WA_WIKIPEDIA="$BASE_URL:8888/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing"
export WA_MAP="$BASE_URL:3000"
export WA_HOMEPAGE="$BASE_URL:4399"

# Optional full-reset endpoint; leave empty if your instance doesn't offer it
export WA_FULL_RESET=""

# Optional: extra HTTP headers for Playwright (e.g. an access token for a secured instance)
# export PW_EXTRA_HEADERS="/path/to/headers.json"

# LLM for the agents
export OPENAI_API_KEY="sk-..."
# export OPENAI_BASE_URL="https://your-openai-compatible-endpoint/v1"   # if not OpenAI
```

If a domain isn't running, set its URL to `todo` and filter those tasks out — for
shopping-only collection you don't need gitlab/reddit/map up.

---

## 4. Verify the BrowserGym ↔ WebArena link

```python
import gymnasium as gym
import browsergym.webarena            # registers browsergym/webarena.* tasks

env = gym.make("browsergym/webarena.0")
obs, info = env.reset()
print("connected; current url:", obs.get("url"))
env.close()
```

If `reset()` hangs or errors, your `WA_*` URLs/ports are wrong or a site is down.

---

## 5. Reset procedure (do this between runs)

WebArena sites are **stateful and shared**. Exploration performs writes (add to
cart, checkout, create issues) that mutate the sites. Reset to the initial state
between collection runs, following WebArena's reset instructions. If your instance
exposes the full-reset service, set `WA_FULL_RESET` and BrowserGym can trigger it;
otherwise reset the Docker volumes/containers manually per the WebArena docs.

---

## 6. Run HSGE exploration

Once a site is up and the env vars are set, run the standalone runtime:

```bash
set -a; source .env; set +a
python run_webarena.py \
    --root-url "$WA_SHOPPING" \
    --out outputs/wa_run \
    --allow "http://<your-host>:7770.*" \
    --max-nodes 15 --max-depth 6 --max-steps 15
```

See `09_run_on_webarena.md` for a full description of the runtime and a `--dry-run`
mode that verifies the wiring with no browser or network.

## 7. Output artifacts

```
outputs/wa_run/episodes/ep_XXXX/
  episode_meta.json        # goal, outcome.success/reward, difficulty, tags
  episode.jsonl            # per-step action + observation path
  page_state/step_*.txt    # accessibility-tree text per step
```

Feed straight into training:
```bash
# Go-Browse style: JSON output + narrative thought
python build_sft_dataset.py outputs/wa_run/episodes train.jsonl \
  --action-format webarena_json

# Multi-turn: one sample per trajectory
python build_sft_dataset.py outputs/wa_run/episodes train.jsonl \
  --action-format webarena_json --multiturn
```

## 10. Caveats and troubleshooting

`events.jsonl` là log machine-readable theo component/event. Xem
`nodes/node_N/summary.json` để biết Solver tạo bao nhiêu navigation, unique URL,
eligible URL và bao nhiêu URL thực sự vào Frontier. `metrics_latest.json` được
cập nhật cùng checkpoint. Điều chỉnh độ chi tiết bằng
`--event-log-level debug|info|summary|warning|error` (mặc định `info`).

| Symptom / risk | Cause | Fix |
| --- | --- | --- |
| Purchase tasks never verify | checkout can't reach success page | Confirm Magento accepts dummy payment (check/money order) and lands on `checkout/onepage/success`; key the terminal checker on that URL |
| Non-reproducible trajectories | parallel workers on shared mutable sites | Run a **single worker** for collection |
| Frontier explodes on results pages | faceted/paginated filter URLs | Add `denylist_patterns` for `?p=`, `?product_list_*`, sort/filter query params |
| State drift across runs | sites not reset | Reset between runs (Step 5) |
| `reset()` hangs | wrong `WA_*` URL/port or site down | Re-check Step 1 + Step 4 |
| Slow throughput | headed browser | `export BROWSERGYM_HEADLESS=true` (debug first runs headed) |
| Auth/logout loops | agent clicks logout | Denylist logout URLs |
| Action như `hover` giữ node quá lâu | Navigation timeout bị dùng làm action timeout hoặc target stale | Giữ `browser.timeout_ms` cho navigation và đặt `browser.action_timeout_ms` khoảng 5000; action error được ghi vào episode và `solver.completed` event |

---

## 11. Recommended first run

1. Host **only** the shopping site; set its `WA_SHOPPING` URL, others to `todo`.
2. Verify with the Step-4 snippet and reach `checkout/onepage/success` by hand once.
3. Run with `max_depth` low and `goal_conditioned_phase: false` to confirm vanilla
   collection works and writes artifacts.
4. Turn on `goal_conditioned_phase: true` and confirm one verified multi-step
   purchase trajectory appears.
5. Scale up depth / products, then loop into `build_sft_dataset.py` → fine-tune.

---

### Sources
- BrowserGym WebArena integration: https://github.com/ServiceNow/BrowserGym/blob/main/browsergym/webarena/README.md
- WebArena hosting + reset: https://github.com/web-arena-x/webarena
- `browsergym-webarena` on PyPI: https://pypi.org/project/browsergym-webarena/
