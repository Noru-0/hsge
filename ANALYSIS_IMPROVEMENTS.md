# Phân tích thiếu sót & Đề xuất cải tiến cho HSGE Improved

> Tài liệu này phân tích những vấn đề trong bản cải tiến hiện tại và đề xuất hướng hoàn thiện. Mỗi mục đều có: vấn đề → phân tích → giải pháp đề xuất.

---

## Mục lục

1. [Skill Hints — Cơ chế chính bị hỏng](#1-skill-hints--cơ-chế-chính-bị-hỏng)
2. [SkillLibrary — Verification gate vô hiệu](#2-skilllibrary--verification-gate-vô-hiệu)
3. [Operator Mining — Predicate không đồng bộ](#3-operator-mining--predicate-không-đồng-bộ)
4. [HierarchicalGraph vs OperatorGraph — Hai graph song song](#4-hierarchicalgraph-vs-operatorgraph--hai-graph-song-song)
5. [Curriculum — Không dùng planner](#5-curriculum--không-dùng-planner)
6. [Discovery — Skill edge sai ngữ nghĩa](#6-discovery--skill-edge-sai-ngữ-nghĩa)
7. [Segmentation — URL boundary không đủ](#7-segmentation--url-boundary-không-đủ)
8. [Abstraction — Action template không dùng được](#8-abstraction--action-template-không-dùng-được)
9. [Transfer — Chỉ có retrieval, không có execution](#9-transfer--chỉ-có-retrieval-không-có-execution)
10. [Checkpoint/Resume — Không đồng bộ state](#10-checkpointresume--không-đồng-bộ-state)
11. [Frontier Filter — Thiếu context-aware filtering](#11-frontier-filter--thiếu-context-aware-filtering)
12. [Error Handling — Thiếu graceful degradation](#12-error-handling--thiếu-graceful-degradation)
13. [Monitoring — Không có metrics](#13-monitoring--không-có-metrics)
14. [Bản đồ cải tiến tổng thể](#14-bản-đồ-cải-tiến-tổng-thể)

---

## 1. Skill Hints — Cơ chế chính bị hỏng

### Vấn đề

`_build_skill_hints()` dùng `library.retrieve(query, top_k=5)` để tìm skills liên quan, nhưng **retrieve dùng cosine similarity trên embedding của `SubTrajectory.text_for_embedding()`**:

```python
# schema.py
def text_for_embedding(self) -> str:
    return f"GOAL: {self.subgoal} | ACTIONS: {self.action_signature()}"
```

Vấn đề:
1. **Query là task description** (e.g., "search for an item") nhưng embedding được train trên `"GOAL: ... | ACTIONS: click > fill > ..."` — format khác hoàn toàn → similarity thấp
2. **Skill chỉ có name + description** trong hint, nhưng **không có action_template đúng format** để agent dùng
3. **Agent không biết cách instantiate template**: action_template chứa `{slot_name}` nhưng agent không được hướng dẫn cách bind

### Biểu hiện lỗi

```
AVAILABLE SKILLS (already learned, may help with this task):
  - search_product: Search for a product by keyword
    action: fill('#search', '{query}')
```

Agent thấy `fill('#search', '{query}')` nhưng không biết `{query}` cần được thay bằng giá trị gì, và không biết `#search` có tồn tại trên page hiện tại không.

### Giải pháp đề xuất

#### a) Cải tiến retrieval: dùng skill name + description làm embedding text

```python
# library.py
class SkillLibrary:
    def _rebuild_skill_embeddings(self):
        """Build embeddings from skill card text (not sub-trajectory text)."""
        for cid, card in self.skills.items():
            text = f"{card.name}: {card.description}. Precondition: {card.precondition}. Effect: {card.success_predicate}"
            # Lưu riêng embedding cho skill card
            self._skill_embeddings[cid] = self.embedder.encode([text])[0]

    def retrieve(self, query, top_k=3):
        """Retrieve by skill card embedding (not sub-trajectory)."""
        if not self.skills:
            return []
        # Fallback nếu chưa build skill embeddings
        if not hasattr(self, '_skill_embeddings') or not self._skill_embeddings:
            self._rebuild_skill_embeddings()
        q = self.embedder.encode([query])[0]
        scored = []
        for cid, card in self.skills.items():
            emb = self._skill_embeddings.get(cid)
            if emb is None:
                continue
            scored.append((float(emb @ q), card))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [card for _, card in scored[:top_k]]
```

#### b) Cải tiến skill hints format: hướng dẫn agent cách dùng

```python
def _build_skill_hints(self, page_url="", task=""):
    skills = self.library.all_skills()
    if not skills:
        return ""
    query = task or page_url or "web task"
    relevant = self.library.retrieve(query, top_k=5)
    if not relevant:
        return ""
    lines = [
        "You have previously learned the following skills. "
        "You MAY use them as reference for action patterns, but you MUST "
        "adapt selectors/values to the current page's actual element IDs.",
        ""
    ]
    for s in relevant:
        lines.append(f"Skill: {s.name}")
        lines.append(f"  Description: {s.description}")
        lines.append(f"  When: {s.precondition}")
        lines.append(f"  Action pattern: {s.action_template}")
        lines.append(f"  Success when: {s.success_predicate}")
        lines.append("")
    return "\n".join(lines)
```

#### c) Nâng cấp lên Tool-Use (Function Calling) — ƯU TIÊN CAO

Đây là cải tiến quan trọng nhất. Thay vì nhét skill vào text prompt, đăng ký skill như **tool/function** mà LLM có thể gọi:

```python
# agents.py
def _build_tools(skills: list[SkillCard]) -> list[dict]:
    """Convert admitted skills to OpenAI/DeepSeek tool definitions."""
    tools = []
    for s in skills:
        properties = {}
        for slot in s.slots:
            properties[slot.name] = {
                "type": "string",
                "description": slot.description
            }
        tools.append({
            "type": "function",
            "function": {
                "name": s.name,
                "description": f"{s.description}. Precondition: {s.precondition}. Success: {s.success_predicate}",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": [slot.name for slot in s.slots if slot.slot_type == "value"]
                }
            }
        })
    return tools
```

Khi LLM gọi tool, runtime sẽ:
1. Bind parameters vào action_template
2. Execute từng step
3. Kiểm tra success_predicate
4. Trả về kết quả cho LLM

---

## 2. SkillLibrary — Verification gate vô hiệu

### Vấn đề

Trong `runtime.py`:
```python
self.library = SkillLibrary(
    _explorer_llm, embedder,
    verify_contexts_fn=lambda: [],  # ← LUÔN trả về list rỗng!
    maturity=3, verify_k=2
)
```

Vì `verify_contexts_fn` luôn trả về `[]`, nên trong `verification.py`:
```python
if not contexts:
    skill.verified = True  # ← ADMIT NGAY, KHÔNG VERIFY!
    return True
```

**Mọi skill đều được admit mà không qua verification gate.** Đây là lỗi nghiêm trọng: toàn bộ điểm khác biệt của HSGE so với AWM (verification gate) bị vô hiệu hóa.

### Giải pháp đề xuất

#### a) Verification bằng replay trên episodes đã có

```python
class WebArenaExplorer:
    def __init__(self, ...):
        # Thay vì lambda: [], dùng method thật
        self.library = SkillLibrary(
            _explorer_llm, embedder,
            verify_contexts_fn=self._build_verify_contexts,
            maturity=3, verify_k=2
        )
    
    def _build_verify_contexts(self) -> list:
        """Build verification contexts from existing successful episodes.
        
        Returns a list of (steps, obs_texts) pairs from DIFFERENT pages/sites
        that can be used to ground-and-execute a candidate skill.
        """
        contexts = []
        ep_dir = os.path.join(self.out_dir, "episodes")
        if not os.path.isdir(ep_dir):
            return contexts
        # Lấy episodes từ các pages khác nhau
        seen_urls = set()
        for ep_name in sorted(os.listdir(ep_dir)):
            if not ep_name.startswith("ep_"):
                continue
            meta_path = os.path.join(ep_dir, ep_name, "episode_meta.json")
            if not os.path.isfile(meta_path):
                continue
            with open(meta_path) as f:
                meta = json.load(f)
            if not meta.get("outcome", {}).get("success"):
                continue
            # Mỗi URL gốc chỉ lấy 1 context
            url = meta.get("goal", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            # Tạo WebEnv mock từ episode data
            contexts.append(_EpisodeContext(ep_dir, ep_name))
            if len(contexts) >= 5:  # Giới hạn số contexts
                break
        return contexts
```

#### b) Verification bằng browser thật (optional)

Khi có nhiều browser instances, verification có thể dùng browser thật:

```python
def _build_verify_contexts(self) -> list:
    """Use a separate browser to verify on DIFFERENT pages."""
    if not hasattr(self, '_verify_browser'):
        return []
    contexts = []
    for test_url in self._test_urls:  # URLs đã biết là ổn định
        browser = self.browser_factory(test_url)
        contexts.append(_BrowserContext(browser))
    return contexts
```

---

## 3. Operator Mining — Predicate không đồng bộ

### Vấn đề

Trong `_mine_operator()`:
```python
start = predicates_from(start_url, obs_texts[0] if obs_texts else "")
end = predicates_from(final_obs.get("url", ""), final_obs.get("axtree", ""))
eff = end - start
```

`predicates_from()` trích xuất predicates từ URL + AXTree text. Vấn đề:
1. **Predicate extraction không chuẩn hóa**: cùng URL có thể trả về predicates khác nhau tùy theo AXTree
2. **Set difference không đủ**: nếu start có `{cart_empty}` và end có `{cart_empty, cart_nonempty}`, diff ra `{cart_nonempty}` — OK. Nhưng nếu có predicate biến mất (e.g., `loading` → hết loading) thì không được ghi nhận
3. **Không có negative effects**: operator chỉ ghi nhận effects được THÊM, không ghi nhận effects bị XÓA

### Giải pháp đề xuất

```python
def _mine_operator(self, goal, steps, obs_texts, final_obs):
    if not steps or not hasattr(steps[0], 'url'):
        return
    start_url = getattr(steps[0], 'url', '')
    if not start_url:
        return
    
    # Lấy predicates từ nhiều steps (không chỉ first/last)
    all_start = set()
    for i in range(len(steps) // 2):  # Nửa đầu trajectory
        all_start |= predicates_from(
            steps[i].url, 
            obs_texts[i] if i < len(obs_texts) else ""
        )
    
    all_end = set()
    for i in range(len(steps) // 2, len(steps)):  # Nửa cuối
        all_end |= predicates_from(
            steps[i].url,
            obs_texts[i] if i < len(obs_texts) else ""
        )
    
    added = all_end - all_start
    removed = all_start - all_end
    
    if not added and not removed:
        return
    
    name = _name_from_goal(goal)
    terminal = self.terminal_goal in added
    
    # Operator với cả added (+) và removed (-) effects
    self.opgraph.add(Operator(
        name, 
        preconditions=frozenset(all_start),
        effects=frozenset(added),  # positive effects
        # Có thể thêm negative_effects nếu cần
        terminal=terminal
    ))
```

---

## 4. HierarchicalGraph vs OperatorGraph — Hai graph song song

### Vấn đề

Có **2 graph riêng biệt**:
- `HierarchicalGraph` (trong `graph.py`): lưu URL states + skill nodes + edges
- `OperatorGraph` (trong `operators.py`): lưu operators với precondition/effect semantics

**Không có cơ chế đồng bộ** giữa 2 graph:
- `Discovery.on_trajectory()` chỉ update `HierarchicalGraph`
- `_mine_operator()` chỉ update `OperatorGraph`
- `_write_graph()` chỉ export `HierarchicalGraph` (bỏ qua OperatorGraph)
- `plan()` dùng `OperatorGraph`, không dùng `HierarchicalGraph`

### Hậu quả

- Curriculum sinh từ `HierarchicalGraph.successors()` dùng composition edges (co-occurrence)
- Planner dùng `OperatorGraph` với precondition/effect edges
- Hai nguồn skill chain khác nhau → không nhất quán

### Giải pháp đề xuất

#### Hợp nhất: OperatorGraph làm graph chính

```python
# runtime.py
class WebArenaExplorer:
    def __init__(self, ...):
        self.opgraph = OperatorGraph()  # Graph CHÍNH
        self.graph = HierarchicalGraph()  # Graph PHỤ (chỉ cho export)
        # Đồng bộ: khi operator được thêm, cập nhật cả HierarchicalGraph
    
    def _mine_operator(self, ...):
        op = Operator(name, preconditions, effects, terminal)
        self.opgraph.add(op)
        # Đồng bộ HierarchicalGraph
        self._sync_to_hierarchical_graph(op)
    
    def _sync_to_hierarchical_graph(self, op: Operator):
        """Sync operator to HierarchicalGraph for export compatibility."""
        # Tạo SkillCard ảo từ operator
        card = SkillCard(
            name=op.name,
            description=f"Operator: {op.name}",
            slots=[],
            action_template="",
            precondition=" | ".join(op.preconditions),
            success_predicate=" | ".join(op.effects),
            cluster_id=f"op_{op.name}",
        )
        self.graph.skills[card.skill_id] = card
        # Edge từ precondition states
        for state in op.preconditions:
            self.graph.state_to_skill[state].add(card.skill_id)
        # Edge đến effect states
        for state in op.effects:
            self.graph.skill_to_state[card.skill_id].add(state)
        # Composition edges từ effect/precondition matching
        for other_name, other_op in self.opgraph.ops.items():
            if other_name == op.name:
                continue
            if op.effects & other_op.preconditions:
                # op → other_op (op thiết lập điều kiện cho other_op)
                other_id = self._op_to_skill_id(other_name)
                if other_id:
                    self.graph.skill_to_skill[card.skill_id].add(other_id)
            if other_op.effects & op.preconditions:
                # other_op → op
                other_id = self._op_to_skill_id(other_name)
                if other_id:
                    self.graph.skill_to_skill[other_id].add(card.skill_id)
```

---

## 5. Curriculum — Không dùng planner

### Vấn đề

`generate_curriculum()` dùng DFS trên `HierarchicalGraph.successors()` — enumerates **composition edges** (co-occurrence), không phải **precondition/effect edges**:

```python
def _chains(graph: HierarchicalGraph, max_len: int) -> list[list[str]]:
    for nxt in graph.successors(path[-1]):  # successors = composition edges
        ...
```

Trong khi `plan()` trong `operators.py` dùng BFS trên precondition/effect matching — đây mới là cách đúng để tìm skill chain.

### Hậu quả

Curriculum tasks không đảm bảo tính khả thi: skill A → skill B có edge trong HierarchicalGraph chỉ vì chúng xuất hiện cùng nhau trong 1 trajectory, không phải vì A thiết lập precondition cho B.

### Giải pháp đề xuất

#### Curriculum từ OperatorGraph planner

```python
# curriculum.py
def generate_curriculum_from_operators(
    opgraph: OperatorGraph,
    max_len: int = 3,
    site: str = "",
) -> list[Task]:
    """Generate curriculum by PLANNING, not by enumerating composition edges.
    
    For each operator, try to plan from empty state to that operator's 
    preconditions. The plan length = difficulty. This guarantees every
    chain is executable (precondition-satisfying).
    """
    tasks = []
    initial = frozenset()
    
    # Single-skill tasks (difficulty 1)
    for op in opgraph.ops.values():
        if op.preconditions <= initial:
            tasks.append(Task(
                instruction=f"Complete the '{op.name}' task.",
                skill_chain=[op.name],
                difficulty=1,
                site=site,
            ))
    
    # Multi-skill tasks: plan from initial to each operator's preconditions
    for op in opgraph.ops.values():
        if op.preconditions <= initial:
            continue
        chain = plan(opgraph, initial, list(op.preconditions)[0] if op.preconditions else "")
        if chain and len(chain) <= max_len:
            tasks.append(Task(
                instruction=_instruction_from_chain(chain, opgraph),
                skill_chain=chain + [op.name],
                difficulty=len(chain) + 1,
                site=site,
            ))
    
    # Terminal goal task (full purchase chain)
    for op in opgraph.ops.values():
        if op.terminal:
            chain = plan(opgraph, initial, list(op.effects)[0])
            if chain and len(chain) <= max_len:
                tasks.append(Task(
                    instruction="Complete the full purchase: " + " → ".join(chain),
                    skill_chain=chain,
                    difficulty=len(chain),
                    site=site,
                ))
    
    tasks.sort(key=lambda t: t.difficulty)
    return tasks


def _instruction_from_chain(chain: list[str], opgraph: OperatorGraph) -> str:
    names = [opgraph.ops[op].name for op in chain]
    if len(names) == 1:
        return f"Complete the '{names[0]}' task."
    return " → ".join(names)
```

---

## 6. Discovery — Skill edge sai ngữ nghĩa

### Vấn đề

```python
# discovery.py
for a, b in zip(just_admitted_in_order, just_admitted_in_order[1:]):
    self.graph.link_skills(a, b)  # composition edge từ co-occurrence
```

**Consecutive skills trong cùng trajectory ≠ composition relationship.** Skill A (login) và skill B (search) xuất hiện cạnh nhau chỉ vì task yêu cầu cả hai, không phải vì login là precondition của search.

### Giải pháp đề xuất

```python
# discovery.py
class Discovery:
    def on_trajectory(self, steps, site, task, subgoal_hints=None):
        # ... segment + library observe ...
        
        # KHÔNG tạo composition edges từ co-occurrence
        # Thay vào đó, để OperatorGraph quản lý edges qua precondition/effect
        
        # Chỉ tạo state→skill và skill→state edges
        for sub, sid in self._segment_skill_pairs(subs):
            if sid is None:
                continue
            cid = self._cid_of(sid)
            card = self.library.skills.get(cid)
            init = [sub.steps[0].url] if sub.steps else []
            effect = [sub.steps[-1].url] if sub.steps else []
            if card:
                self.graph.add_skill(card, init_states=init, effect_states=effect)
        
        # KHÔNG gọi link_skills ở đây
        # Composition edges sẽ được sync từ OperatorGraph sau
        
        return admitted
```

---

## 7. Segmentation — URL boundary không đủ

### Vấn đề

```python
def _url_boundary_segments(steps: list[Step]) -> list[tuple[int, int]]:
    """Split where the URL changes; each run of same-URL steps is one segment."""
```

**URL boundary là heuristic quá thô**: nhiều actions khác nhau có thể xảy ra trên cùng URL (e.g., fill form → click submit → vẫn cùng URL chờ redirect). Và nhiều steps trên các URLs khác nhau có thể là 1 subgoal (e.g., search flow: home → search?q=x → results).

### Giải pháp đề xuất

```python
def segment_trajectory(llm, steps, site, task, subgoal_hints=None):
    # Dùng LLM để segment thay vì URL boundary
    # Cung cấp cho LLM: action sequence + URL changes + DOM summaries
    action_sequence = [
        f"{i}. [{s.action_kind()}] {s.url}" 
        for i, s in enumerate(steps)
    ]
    
    prompt = (
        f"Task: {task}\n\n"
        f"Split this action sequence into coherent sub-goals. "
        f"Each sub-goal should be a meaningful unit of work "
        f"(e.g., 'log in', 'search for product', 'add to cart').\n\n"
        + "\n".join(action_sequence)
    )
    
    out = llm.complete_json(_SEGMENT_SYS, prompt)
    # Parse segments từ LLM output
    # Fallback: nếu LLM fail, dùng URL boundary + action heuristic
    
    # Action heuristic fallback:
    # - click + URL change → likely new subgoal
    # - fill + same URL → same subgoal
    # - Multiple clicks without URL change → likely 1 subgoal
```

---

## 8. Abstraction — Action template không dùng được

### Vấn đề

`SkillCard.action_template` là `list[str]` — danh sách các templated actions. Nhưng:
1. **Template không có cấu trúc**: chỉ là string như `fill('#search', '{query}')` — LLM phải tự suy luận
2. **Không có execution context**: không biết action này chạy trên page nào, cần precondition gì
3. **Không có fallback**: nếu selector `#search` không tồn tại trên page mới, skill fail hoàn toàn

### Giải pháp đề xuất

```python
# schema.py
@dataclass
class SkillCard:
    name: str
    description: str
    slots: list[ParamSlot]
    action_template: list[str]  # Giữ nguyên cho backward compatibility
    # THÊM: structured execution plan
    execution_plan: list[ExecutionStep] = field(default_factory=list)
    # THÊM: alternative selectors cho robustness
    alternative_templates: list[list[str]] = field(default_factory=list)


@dataclass
class ExecutionStep:
    """Một step trong execution plan của skill."""
    action_type: str  # "click" | "fill" | "select" | "goto"
    target_desc: str  # Mô tả element cần tìm, e.g., "search input field"
    value_ref: str | None = None  # Reference đến slot name nếu cần value
    fallback_instructions: str = ""  # Hướng dẫn nếu element không tìm thấy
    success_check: str = ""  # Làm sao để biết step này thành công
```

Khi abstraction, LLM sẽ trả về structured execution plan thay vì template string:

```python
# abstraction.py - improved prompt
_SYS = (
    "You ABSTRACT several concrete sub-trajectories into ONE reusable skill.\n"
    "Return JSON:\n"
    '{\n'
    '  "name": "skill_name",\n'
    '  "description": "...",\n'
    '  "slots": [{"name":"...", "slot_type":"selector|value", "description":"..."}],\n'
    '  "execution_plan": [\n'
    '    {"action_type": "click|fill|goto", "target_desc": "description of element",\n'
    '     "value_ref": "slot_name_or_null", "fallback": "what to try if element missing"}\n'
    '  ],\n'
    '  "precondition": "...",\n'
    '  "success_predicate": "..."\n'
    '}'
)
```

---

## 9. Transfer — Chỉ có retrieval, không có execution

### Vấn đề

`transfer_eval()` chỉ gọi `library.retrieve()` và log kết quả. Không có:
1. **Ground-and-execute thực tế**: không mở browser trên target site
2. **Adaptation**: không thử alternative selectors khi skill fail
3. **Feedback loop**: không cập nhật library dựa trên kết quả transfer

### Giải pháp đề xuất

```python
def transfer_and_adapt(
    self, 
    target_url: str, 
    query: str, 
    top_k: int = 5
) -> TransferResult:
    """Transfer skills to a new site with actual execution and adaptation."""
    cards = self.library.retrieve(query, top_k=top_k)
    transferred = []
    
    for card in cards:
        # Mở browser trên target site
        browser = self.browser_factory(target_url)
        browser.reset()
        
        # Thử ground-and-execute
        success = self._try_ground_and_execute(browser, card)
        
        if success:
            transferred.append(card.skill_id)
            card.stats.sites_seen.add(target_url)
        else:
            # Thử adaptation: hỏi LLM điều chỉnh plan
            adapted = self._adapt_skill(browser, card)
            if adapted:
                # Lưu adapted version như skill variant
                self._save_adapted_skill(card, adapted, target_url)
                transferred.append(adapted.skill_id)
        
        browser.close()
    
    return TransferResult(
        site=target_url,
        attempted=len(cards),
        succeeded=len(transferred),
        transferred_skill_ids=transferred,
    )


def _adapt_skill(self, browser, card: SkillCard) -> SkillCard | None:
    """Ask LLM to adapt a skill to the current page."""
    obs = browser.observation()
    prompt = (
        f"Skill '{card.name}' failed on this page.\n"
        f"Original template: {card.action_template}\n"
        f"Current page URL: {obs['url']}\n"
        f"Current page AXTree: {obs['axtree'][:3000]}\n\n"
        f"Adapt the action template to work on this page. "
        f"Return new action_template with correct selectors."
    )
    out = self.solver.llm.complete_json(_ADAPT_SYS, prompt)
    if not out or "action_template" not in out:
        return None
    # Tạo adapted skill card
    adapted = SkillCard(
        name=f"{card.name}_adapted",
        description=f"{card.description} (adapted for {browser.url})",
        slots=card.slots,
        action_template=out["action_template"],
        precondition=card.precondition,
        success_predicate=card.success_predicate,
        cluster_id=card.cluster_id,
    )
    return adapted
```

---

## 10. Checkpoint/Resume — Không đồng bộ state

### Vấn đề

Checkpoint lưu frontier/visited/queued nhưng **không lưu**:
1. **OperatorGraph state**: operators đã mine được
2. **HierarchicalGraph state**: graph structure
3. **Discovery state**: cluster states, skill states
4. **Episode counter**: `self.episode` được phục hồi nhưng không verify tính đúng đắn

### Hậu quả

Khi resume, `_replay_episodes()` replay lại episodes để rebuild library. Nhưng:
- `_mine_operator()` được gọi lại → operators bị duplicate
- `Discovery.on_trajectory()` được gọi lại → graph bị rebuild từ đầu
- Tốn thời gian và có thể tạo duplicate data

### Giải pháp đề xuất

```python
def save_checkpoint(self, frontier, visited, queued):
    """Full state checkpoint."""
    ckpt = {
        "frontier": [[u, d] for u, d in frontier],
        "visited": sorted(visited),
        "queued": sorted(queued),
        "nodes_processed": self._nodes_done,
        "episode": self.episode,
        "template_quota": self._template_quota,
        # THÊM: graph state
        "operator_graph": {
            "ops": {
                name: {
                    "preconditions": sorted(op.preconditions),
                    "effects": sorted(op.effects),
                    "terminal": op.terminal,
                }
                for name, op in self.opgraph.ops.items()
            }
        },
        # THÊM: clusterer state (centroids, etc.)
        "clusterer": self._serialize_clusterer(),
    }
    with open(self._checkpoint_path, "w") as f:
        json.dump(ckpt, f, indent=2)


def _resume_from_checkpoint(self, ckpt):
    """Restore full state from checkpoint."""
    self.episode = ckpt.get("episode", 0)
    self._template_quota = ckpt.get("template_quota", {})
    
    # Restore operator graph
    for name, op_data in ckpt.get("operator_graph", {}).get("ops", {}).items():
        op = Operator(
            name=name,
            preconditions=frozenset(op_data["preconditions"]),
            effects=frozenset(op_data["effects"]),
            terminal=op_data["terminal"],
        )
        self.opgraph.add(op)
    
    # Restore clusterer
    self._deserialize_clusterer(ckpt.get("clusterer", {}))
    
    # Restore logs
    for log_file, log_attr in [
        ("skills.json", "_skills_log"),
        ("curriculum.json", "_curriculum_log"),
        ("transfer.json", "_transfer_log"),
    ]:
        path = os.path.join(self.out_dir, log_file)
        if os.path.isfile(path):
            with open(path) as f:
                setattr(self, log_attr, json.load(f))
    
    # KHÔNG cần replay episodes nếu đã lưu graph state
    # Chỉ replay nếu cần rebuild library từ episodes
    if not self.opgraph.ops:
        self._replay_episodes()
```

---

## 11. Frontier Filter — Thiếu context-aware filtering

### Vấn đề

`_filter_links()` dùng template clustering + global quota, nhưng:
1. **Không biết skill library**: có thể filter mất URLs cần thiết để học skill mới
2. **Không ưu tiên URLs chưa explore**: tất cả templates được đối xử như nhau
3. **Template max=10 là hardcoded**: không adapt theo số nodes đã explore

### Giải pháp đề xuất

```python
def _filter_links(self, links, already_queued, current_url=""):
    """Context-aware frontier filter."""
    if not links:
        return []
    
    # 1. Deduplicate
    links = list(dict.fromkeys(links))
    
    # 2. Extract templates
    batch_templates = extract_templates(links)
    
    # 3. Score with context awareness
    scored = []
    for tmpl, urls in batch_templates.items():
        base_score = template_priority(tmpl, len(urls))
        
        # THÊM: boost nếu template chưa từng thấy (khám phá mới)
        novelty_boost = 2.0 if tmpl not in self._template_quota else 0.0
        
        # THÊM: boost nếu URL pattern gợi ý functional page
        func_boost = 0.0
        for kw in ['checkout', 'cart', 'payment', 'account', 'product']:
            if kw in tmpl.lower():
                func_boost += 0.5
        
        # THÊM: penalty nếu template quá sâu
        depth_penalty = max(0, tmpl.count('/') - 6) * 0.5
        
        scored.append((
            tmpl, 
            base_score + novelty_boost + func_boost - depth_penalty,
            urls
        ))
    
    # 4. Adaptive budget: càng explore nhiều → quota càng nhỏ
    progress = self._nodes_done / max(self.max_nodes, 1)
    adaptive_max = max(3, int(self._template_max * (1 - progress * 0.5)))
    
    # 5. Sample
    scored.sort(key=lambda x: -x[1])
    kept = []
    budget = self._frontier_max
    
    for tmpl, score, urls in scored:
        if budget <= 0:
            break
        already = self._template_quota.get(tmpl, 0)
        remaining = adaptive_max - already
        if remaining <= 0:
            continue
        candidates = [u for u in urls if u not in already_queued]
        if not candidates:
            continue
        sampled = _sample_diverse(
            [{'url': u, 'depth': 0} for u in candidates],
            min(remaining, budget)
        )
        sampled_urls = [it['url'] for it in sampled]
        kept.extend(sampled_urls)
        self._template_quota[tmpl] = already + len(sampled_urls)
        budget -= len(sampled_urls)
    
    return kept
```

---

## 12. Error Handling — Thiếu graceful degradation

### Vấn đề

Nhiều chỗ không có error handling:
1. **Browser crash mid-exploration**: exception không được catch → cả run crash
2. **LLM timeout**: `complete_json()` có thể treo vô hạn
3. **Disk full**: write episodes fail → mất data
4. **URL không parse được**: `_norm()` crash

### Giải pháp đề xuất

```python
# runtime.py - improved run loop
def run(self, root_url):
    # ... setup ...
    
    while frontier and nodes_processed < self.max_nodes:
        url, depth = frontier.pop(0)
        if url in visited or depth > self.max_depth:
            continue
        
        try:
            self._process_node(url, depth, visited, frontier, queued, nodes_processed)
        except Exception as e:
            # Graceful degradation: log error, skip node, continue
            msg = f"[ERROR] node {nodes_processed} ({url}): {e}"
            print(msg)
            if self._log_file:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            # Save emergency checkpoint
            self.save_checkpoint(frontier, visited, queued)
            continue
        
        nodes_processed += 1
        # Normal checkpoint
        if nodes_processed % 3 == 0:
            self.save_checkpoint(frontier, visited, queued)


def _process_node(self, url, depth, visited, frontier, queued, node_num):
    """Process one node with full error isolation."""
    visited.add(url)
    
    # Browser với timeout
    browser = self._create_browser_with_timeout(url)
    if browser is None:
        return
    
    try:
        obs = browser.reset()
        # ... exploration logic ...
    finally:
        try:
            browser.close()
        except Exception:
            pass


def _create_browser_with_timeout(self, url, timeout=30):
    """Create browser with timeout protection."""
    import signal
    
    class TimeoutError(Exception):
        pass
    
    def handler(signum, frame):
        raise TimeoutError("Browser creation timed out")
    
    # signal.signal(signal.SIGALRM, handler)
    # signal.alarm(timeout)
    try:
        return self.browser_factory(url)
    except Exception as e:
        print(f"  [browser] Failed to create browser for {url}: {e}")
        return None
    # finally:
    #     signal.alarm(0)
```

---

## 13. Monitoring — Không có metrics

### Vấn đề

Không có metrics để đánh giá quality của run:
- Không biết bao nhiêu skills được học / verified / pruned
- Không biết transfer rate
- Không biết exploration coverage
- Không biết LLM cost (token usage)

### Giải pháp đề xuất

```python
# runtime.py - thêm metrics tracking
@dataclass
class RunMetrics:
    """Track run statistics."""
    nodes_visited: int = 0
    tasks_proposed: int = 0
    tasks_solved: int = 0
    skills_discovered: int = 0
    skills_verified: int = 0
    operators_mined: int = 0
    goal_tasks_attempted: int = 0
    goal_tasks_solved: int = 0
    total_llm_calls: int = 0
    total_llm_tokens: int = 0
    start_time: float = 0.0
    
    def summary(self) -> str:
        elapsed = time.time() - self.start_time
        return (
            f"\n{'='*50}"
            f"\n  Run Summary ({elapsed:.0f}s)"
            f"\n  Nodes visited: {self.nodes_visited}"
            f"\n  Tasks: {self.tasks_solved}/{self.tasks_proposed} solved"
            f"\n  Skills: {self.skills_discovered} discovered, {self.skills_verified} verified"
            f"\n  Operators: {self.operators_mined}"
            f"\n  Goal tasks: {self.goal_tasks_solved}/{self.goal_tasks_attempted}"
            f"\n  LLM calls: {self.total_llm_calls}, tokens: {self.total_llm_tokens}"
            f"\n{'='*50}"
        )


class WebArenaExplorer:
    def __init__(self, ...):
        self.metrics = RunMetrics()
        self.metrics.start_time = time.time()
    
    def _on_skill_admitted(self, card):
        self.metrics.skills_verified += 1
        # ... existing logic ...
```

---

## 14. Go-Browse Architecture — Bài học cho HSGE

### Tổng quan go-browse

Go-browse là một web exploration framework khác, có cách tiếp cận hoàn toàn khác với HSGE về cơ chế phát hiện URL và exploration. Các điểm khác biệt chính:

### 14.1 URL Discovery: Callback-based (không phải DOM query)

**HSGE hiện tại**: Sau khi task hoàn thành, query DOM tìm tất cả `<a href>` → thêm vào frontier queue.

**Go-browse**: Callback `process_open_urls_callback` chạy **sau mỗi step** của agent, đọc `obs['open_pages_urls']` — URL mà browser **đang ở**:

```python
def process_open_urls_callback(agent, step_num, goal, env, graph, node, traj, obs, ...):
    open_urls = obs['open_pages_urls']  # ← URL browser đang mở
    
    for url in open_urls:
        if graph.check_if_url_allowed(url):
            # URL này ĐÃ ĐƯỢC VISIT — state còn nguyên
            prefix = Trace.from_trajectory_steps(
                steps=traj.steps,
                start_url=node.url,
                end_url=url,
            )
            graph.add_url(url, parent=node, prefixes=[prefix])
```

**Kết quả**: URL được phát hiện NGAY KHI agent vừa click link đến đó. Không có khoảng cách thời gian giữa phát hiện và xác thực URL → **không bao giờ gặp vấn đề state thay đổi**.

### 14.2 Prefix: Đường đi đã được xác thực

Mỗi URL mới được phát hiện kèm theo **prefix** — trace các steps từ node cha đến URL đó. Prefix này là bằng chứng URL tồn tại và accessible. Khi graph chọn URL này để explore sau, nó biết chắc chắn URL đó từng hoạt động.

```python
# Lưu prefix (trace từ node hiện tại đến URL mới)
prefix = Trace.from_trajectory_steps(
    steps=traj.steps,      # ← Các steps đã thực thi thành công
    start_url=node.url,    # ← Trang xuất phát
    end_url=url,           # ← Trang đích (đã được visit)
)
```

### 14.3 Frontier Scoring (UVD) thay vì FIFO queue

Go-browse không dùng FIFO queue. Nó dùng **scored frontier** — mỗi node được tính điểm và chọn node cao nhất:

```python
def get_next_node(self):
    scored_nodes = [
        (node, self.scorer.breakdown(node))
        for node in self.unexplored_nodes
    ]
    scored_nodes.sort(key=lambda x: x[1]["score"], reverse=True)
    return scored_nodes[0]  # Node có score cao nhất
```

Score = **U (Uncertainty) + V (Value) + D (Diversity)**:
- **U**: Node càng ít được khám phá → càng cao (khuyến khích khám phá mới)
- **V**: Node có success rate cao từ parent → càng cao (khuyến khích khai thác nhánh tốt)
- **D**: Node khác biệt so với các node đã explore → càng cao (tránh bị trùng lặp)

### 14.4 Full Reset giữa các node

Trước mỗi node mới, go-browse gọi `full_reset_url` để reset server về trạng thái ban đầu:

```python
if hasattr(config, 'full_reset_url') and config.full_reset_url:
    perform_full_reset(config.full_reset_url)  # POST request reset server state
```

Điều này đảm bảo mỗi node bắt đầu với state sạch — không còn cart item, không còn session, không còn search params.

### 14.5 Agent navigate tự nhiên (không browser.goto())

Khi HSGE explore 1 node, nó gọi `browser.goto(url)` — tương đương gõ URL vào thanh địa chỉ, dễ gặp redirect vì state đã thay đổi.

Khi go-browse explore 1 node, agent **click link, fill form, submit** — đi theo đúng flow tự nhiên. Nó dùng **prefix** (trace đã lưu) để tái tạo đường đi từ root đến node đó.

### 14.6 So sánh trực tiếp

| Khía cạnh | HSGE (hiện tại) | Go-Browse |
|-----------|----------------|-----------|
| **Phát hiện URL** | Query DOM `<a href>` (tĩnh) | Callback `open_pages_urls` (động) |
| **Thời điểm phát hiện** | Sau khi task hoàn thành | **Trong lúc** thực thi task — sau mỗi step |
| **URL đã được visit?** | Chưa — chỉ là href trong DOM | **Đã được visit** — browser đang ở trang đó |
| **Queue** | FIFO (first-in-first-out) | **Scored** (UVD ranking) |
| **Reset state** | Không có | `full_reset_url` trước mỗi node |
| **Navigate đến URL mới** | `browser.goto(url)` (direct) | Agent click theo prefix (tự nhiên) |
| **State thay đổi** | ✅ **CÓ** — cart/session expire | ❌ **Không** — reset + prefix đảm bảo |
| **Graph** | 2 graph riêng (HG + OpGraph) | 1 graph thống nhất (Node-based) |
| **Skill discovery** | Cluster → abstract → verify | Trace → prefix → summarize |
| **Frontier selection** | FIFO queue | UVD scoring |

### 14.7 Áp dụng vào HSGE

#### a) Thay đổi cơ chế phát hiện URL (QUAN TRỌNG NHẤT)

Chuyển từ DOM query → callback-based `open_pages_urls`:

```python
# Trong Solver.solve() hoặc runtime loop:
# Sau mỗi step, kiểm tra URL mới từ browser
def _on_step_completed(self, browser, step, traj_steps):
    """Callback sau mỗi step — phát hiện URL mới NGAY LẬP TỨC."""
    try:
        open_urls = browser.env.unwrapped.page.evaluate(
            "() => window.location.href"
        )
        # Hoặc dùng browser.open_pages_urls nếu available
    except:
        return
    
    new_url = open_urls  # hoặc lấy từ obs['open_pages_urls']
    if new_url and new_url != self._current_url:
        # URL mới được phát hiện — state còn nguyên
        # Lưu prefix (trace từ node hiện tại đến URL mới)
        self._discovered_urls.append({
            "url": new_url,
            "prefix_steps": list(traj_steps),  # steps đã thực thi
            "source_url": self._current_url,
        })
        self._current_url = new_url
```

#### b) Thêm full_reset_url

```python
# runtime.py
class WebArenaExplorer:
    def __init__(self, ..., full_reset_url: str | None = None):
        self.full_reset_url = full_reset_url
    
    def _reset_env(self):
        """Reset server state trước mỗi node mới."""
        if self.full_reset_url:
            try:
                import requests
                requests.post(self.full_reset_url, timeout=10)
                print(f"  [reset] Full env reset: {self.full_reset_url}")
            except Exception as e:
                print(f"  [reset] Failed: {e}")
```

#### c) Thay FIFO queue bằng scored frontier

```python
# runtime.py
class WebArenaExplorer:
    def __init__(self, ..., frontier_alpha=1.0, frontier_beta=1.0, frontier_theta=1.0):
        self.frontier_scorer = FrontierScorer(alpha, beta, theta)
    
    def _score_frontier(self):
        """Score tất cả URLs trong frontier để chọn node tốt nhất."""
        scored = []
        for url, depth in self.frontier:
            node_info = self._get_node_info(url)
            score = self.frontier_scorer.compute(node_info)
            scored.append((score, url, depth))
        scored.sort(key=lambda x: -x[0])
        return scored  # Trả về danh sách đã sort — pop phần tử đầu tiên
```

---

## 15. Bản đồ cải tiến tổng thể (Cập nhật)

### Priority Matrix

| Priority | Mục | Impact | Effort |
|----------|-----|--------|--------|
| 🔴 P0 | Verification gate (contexts rỗng) | **CRITICAL**: cả pipeline vô hiệu | Thấp |
| 🔴 P0 | Tool-use cho skill hints | **CRITICAL**: skill hints không dùng được | Trung bình |
| 🔴 P0 | **Callback-based URL discovery (từ go-browse)** | **CRITICAL**: URL expire, redirect, checkout không đến được | **Cao** |
| 🟠 P1 | Curriculum từ planner (không phải composition) | Cao: tasks không khả thi | Trung bình |
| 🟠 P1 | Đồng bộ OperatorGraph vs HierarchicalGraph | Cao: 2 graph không nhất quán | Trung bình |
| 🟠 P1 | Discovery không tạo composition edges sai | Cao: skill chain sai ngữ nghĩa | Thấp |
| 🟠 P1 | **Scored frontier (UVD) thay vì FIFO queue** | Cao: chọn node tốt hơn | Trung bình |
| 🟡 P2 | Checkpoint lưu full state | Trung bình: resume không chính xác | Trung bình |
| 🟡 P2 | Transfer có execution thật | Trung bình: transfer chỉ là retrieval | Cao |
| 🟡 P2 | Segmentation dùng LLM + heuristic | Trung bình: URL boundary quá thô | Trung bình |
| 🟡 P2 | **Full reset env trước mỗi node** | Trung bình: state không sạch | Thấp |
| 🟢 P3 | Error handling toàn diện | Thấp: nhưng quan trọng cho reliability | Cao |
| 🟢 P3 | Monitoring metrics | Thấp: quality of life | Thấp |
| 🟢 P3 | Frontier filter context-aware | Thấp: hiện tại đã đủ tốt | Thấp |
| 🟢 P3 | Abstraction execution plan | Thấp: nice-to-have | Cao |

### Thứ tự thực hiện đề xuất (Cập nhật)

```
Phase 1 — Fix critical bugs (P0)
  ├── 1.1 Verification gate: thay lambda: [] bằng verify contexts thật
  ├── 1.2 Tool-use: chuyển skill hints từ text → function calling
  └── 1.3 Callback-based URL discovery (từ go-browse)

Phase 2 — Fix core logic (P1)
  ├── 2.1 Curriculum từ planner
  ├── 2.2 Đồng bộ OperatorGraph + HierarchicalGraph
  ├── 2.3 Discovery: bỏ composition edges từ co-occurrence
  └── 2.4 Scored frontier (UVD) thay vì FIFO queue

Phase 3 — Improve reliability (P2)
  ├── 3.1 Checkpoint full state
  ├── 3.2 Transfer execution thật
  ├── 3.3 Segmentation cải tiến
  └── 3.4 Full reset env trước mỗi node

Phase 4 — Polish (P3)
  ├── 4.1 Error handling
  ├── 4.2 Monitoring
  ├── 4.3 Frontier filter context-aware
  └── 4.4 Abstraction execution plan
```
