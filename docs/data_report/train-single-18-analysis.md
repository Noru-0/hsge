# Training Data Report: `train-single-18.jsonl`

**Date:** 2026-06-24  
**Source:** `training/train-single-18.jsonl` (built from `outputs/wa_run_18/episodes`)  
**Size:** ~14.2 MB, 750 samples, ~3.5M estimated tokens

---

## Summary

| Metric | Value |
|--------|-------|
| Total samples | 750 |
| Structure per sample | `[system, user, assistant]` — **single-turn** |
| Avg. user message size | ~16K chars (full accessibility tree) |
| Unique page titles | 85 |
| Unique products | 109 |
| Unique categories | 15 |

---

## Issues Identified

### 1. Severe Intra-Trajectory Duplication

Multiple consecutive samples share the **exact same goal** because they come from different steps within the same exploration trajectory. For example, the first 5 samples all have the goal:

> *"Click on the 'Add to Wish List' button for the 'Sceptre E195BD-SRR 19-Inch 720P LED TV, True Black (2017)'."*

This means the dataset contains redundant near-duplicates that differ only in page state (e.g., login page → product page → wishlist). When used for SFT, this inflates certain task patterns and risks overfitting.

**Recommendation:** Use `--multiturn` flag in `build_sft_dataset.py` to produce one sample per trajectory, or deduplicate by grouping consecutive samples with identical goals.

---

### 2. Task Imbalance

The dataset is heavily skewed toward simple, single-click tasks:

| Task type | Count | % |
|-----------|-------|---|
| Add to Wish List | 163 | 21.7% |
| Search / Fill Search | 141 | 18.8% |
| Add to Compare | 81 | 10.8% |
| Click Details / Open Product | 76 | 10.1% |
| Add to Cart | 69 | 9.2% |
| Sort by Price | 29 | 3.9% |
| Report Reviews | 15 | 2.0% |
| Compare Products (multi-item) | 17 | 2.3% |
| Other / Unclassified | 99 | 13.2% |

**Missing or underrepresented:**
- Multi-step purchase checkout flows
- Form filling (beyond simple login)
- Product filtering & faceted navigation
- Reading and extracting product details
- Cart management (update quantity, remove items)
- Cross-category browsing

**Recommendation:** Extend exploration to cover longer-horizon tasks (checkout, multi-item cart, form-based filtering) or weight sampling during training to balance task types.

---

### 3. Login/Logout State Noise

~101 samples (13.5%) start on the **Customer Login** page. The assistant must first authenticate before performing the intended action. While this teaches login recovery, it also means:

- The login action (`fill('1378', ...) + fill('1383', ...) + click('1390')`) appears ~30 times as the main assistant response.
- The model may learn to log in as a first resort rather than detecting an already-authenticated session.

**Recommendation:** Either pre-filter samples where the first turn is just a login redirect, or mark them with a `requires_auth` flag for controlled training.

---

### 4. Single-Turn Only — No Multi-Step Reasoning

Every sample is structured as `[system, user, assistant]` with exactly one assistant turn. This means:

- No multi-turn decision-making or error recovery
- No "plan → execute → observe → replan" loops
- The model only learns to map `(page state, goal) → single action`

For real web agents that need multi-step execution, this format is insufficient.

**Recommendation:** Produce a `train-multi-18.jsonl` using `--multiturn` to capture full trajectory rollouts with intermediate observations. Combine single-turn and multi-turn data for hybrid training.

---

### 5. Limited Category Diversity (15 Categories)

Categories are dominated by Electronics (81) and Grocery (53). Categories like Office Products, Tools & Home Improvement, and Toys & Games are absent or barely represented.

**Recommendation:** Run additional exploration episodes targeting underrepresented WebArena categories. Consider category-stratified sampling during dataset construction.

---

## Action Items

| Priority | Action |
|----------|--------|
| 🔴 High | Build multiturn variant to reduce intra-trajectory duplication |
| 🔴 High | Balance task distribution (oversample rare tasks or extend exploration) |
| 🟡 Medium | Filter or flag login-redirect samples |
| 🟡 Medium | Add multi-step tasks (checkout, cart flow, form fill) |
| 🟢 Low | Expand category coverage beyond current 15 categories |
