# Flow chạy HSGE Explore hiện tại

> Phạm vi: `run_webarena.py` và pipeline WebArena trong `hsge/webarena/`.
>
> Trạng thái tài liệu: đối chiếu trực tiếp với code ngày **2026-07-01**.
> Tài liệu này mô tả hành vi đang được implement, bao gồm cả các giới hạn hiện tại;
> không mô tả kiến trúc lý tưởng hoặc flow của các bản cũ.

## 1. Mục tiêu của flow explore

Một run explore đồng thời thực hiện bốn việc:

1. Duyệt các trạng thái web mới bằng frontier URL có chấm điểm.
2. Tạo và giải các task cục bộ trên từng page để thu trajectory.
3. Học `SkillCard` từ các trajectory thành công, sau đó verification trước khi admit.
4. Biến skill có effect đã verify thành planning operator để sinh curriculum và task dài hơn.

Điểm quan trọng của implementation hiện tại:

- URL graph dùng để điều phối exploration và lưu provenance.
- Skill graph dùng predicate precondition/effect để planning.
- URL adjacency **không** tự tạo skill-composition edge.
- Operator chỉ được sinh từ `SkillCard` đã verify và `planning_ready`.
- Learned skill hiện **không được đưa lại vào prompt của `PageExplorer` hoặc `Solver`**.

## 2. Toàn cảnh end-to-end

```text
config.yaml / CLI / .env
          │
          ▼
run_webarena.py
  resolve provider, model, browser, embedder
          │
          ▼
WebArenaExplorer.__init__
  ├─ PageExplorer
  ├─ Solver
  ├─ FrontierScorer + LookaheadPredictor
  ├─ SkillLibrary + Discovery
  ├─ HierarchicalGraph + OperatorGraph
  └─ logs / metrics / checkpoint
          │
          ▼
while frontier còn URL và nodes_processed < max_nodes
  │
  ├─ lấy AXTree/lookahead cho frontier chưa biết
  ├─ score URL bằng S = αU + βV
  ├─ chọn một URL trong top score band
  └─ process_node(URL)
       ├─ mở node bằng prefix replay hoặc direct navigation
       ├─ PageExplorer đề xuất local tasks
       ├─ Solver giải từng task, có reset + retry
       ├─ ghi episode cho cả success và failure
       ├─ trajectory thành công → Discovery → SkillLibrary
       ├─ sinh và chạy tối đa N Curriculum Task từ state của node
       ├─ Curriculum success → Discovery
       ├─ nếu có plan → thử composed GOAL task
       ├─ thêm URL mới vào frontier
       └─ ghi node summary + frontier snapshot
          │
          ▼
checkpoint sau mỗi node
          │
          ▼
final export: skills, graph, curriculum, metrics, episodes
```

## 3. Các component chính

| Component | Vai trò hiện tại |
| --- | --- |
| `run_webarena.py` | Load `.env`/YAML/CLI, resolve model, tạo browser factory và khởi chạy runtime. |
| `WebArenaBrowser` | Wrapper quanh `browsergym/openended`; mở URL, trả AXTree/BID/screenshot, thực thi canonical action. |
| `PageExplorer` | Nhìn page hiện tại và đề xuất task cục bộ có tag `[INFO]`, `[NAV]`, `[MOD]`. |
| `Solver` | Vòng lặp observe → LLM action → validate → browser action → success judge. |
| `FrontierScorer` | Xếp hạng URL bằng uncertainty `U` và value `V`. |
| `LookaheadPredictor` | Dùng model rẻ để dự đoán các task có thể làm ở URL chưa explore. |
| `Discovery` | Nhận trajectory thành công, segment và đẩy các segment vào `SkillLibrary`. |
| `SkillLibrary` | Cluster online → abstract → verify → deduplicate/admit. |
| `HierarchicalGraph` | Giữ low-level URL graph và high-level planner-ready skill graph. |
| `OperatorGraph` | Biểu diễn skill dưới dạng preconditions/effects và planning bằng forward BFS. |
| `curriculum.py` | Sinh task ngắn nhất cho từng effect có thể reach từ root predicates. |

## 4. Khởi động run

### 4.1 Thứ tự lấy configuration

`run_webarena.py` thực hiện theo thứ tự:

1. Load `.env` nhưng không override biến môi trường đã tồn tại.
2. Tìm `--config`; mặc định là `config.yaml` nếu file tồn tại.
3. Flatten YAML sections thành defaults cho `argparse`.
4. Parse CLI; giá trị CLI override YAML.
5. Validate range, enum và kiểu dữ liệu.

Model được resolve theo priority:

```text
--explorer-model / --solver-model
    > EXPLORER_MODEL / SOLVER_MODEL
    > provider preset
```

Nếu dùng `--model`, giá trị này override cả explorer và solver model sau khi resolve.

### 4.2 Real run và dry run

Real run tạo:

- `OpenAILLM` tương thích OpenAI API cho explorer và solver;
- `STEmbedder`, fallback sang `HashingEmbedder` nếu thiếu `sentence-transformers`;
- `WebArenaBrowser` với headless, screenshot, timeout và storage state từ config.

Dry run dùng `_DryLLM` và `_FakeBrowser`, không mở browser/network thật.

### 4.3 Khởi tạo runtime

`WebArenaExplorer.__init__` tạo toàn bộ state sống của run:

- `PageExplorer` và `Solver` dùng hai LLM có thể khác nhau;
- `HierarchicalGraph`, trong đó `operator_graph` là planning graph chuẩn;
- `SkillLibrary` với similarity threshold, maturity, verification `k`;
- `Discovery` nối successful trajectory vào skill pipeline;
- `LookaheadPredictor` và `FrontierScorer`;
- frontier/retry/task/coverage counters;
- `run.log`, `events.jsonl`, `frontier.jsonl` và output directories.

Predicate plugins hiện được khởi tạo từ các plugin khai báo rõ. Trong implementation
hiện tại, token `auto` bị loại trước khi gọi builder; muốn có commerce predicates cần
cấu hình chứa `commerce`, ví dụ:

```yaml
predicates:
  plugins: [auto, commerce]
```

Chỉ `[auto]` hiện tương đương core predicates, chưa tự nhận diện commerce domain.

## 5. State của frontier

Runtime duy trì ba tập chính:

```text
frontier = [(normalized_url, depth), ...]  # ứng viên chưa xử lý
queued   = {normalized_url, ...}           # đã giữ chỗ, chống enqueue trùng
visited  = {normalized_url, ...}           # node hoàn tất thành công
```

URL identity được normalize bằng `_normalize_trace_url`:

- lowercase scheme/host;
- bỏ fragment;
- chuẩn hóa path/trailing slash;
- sort query parameters;
- bỏ tracking params như `utm_*`, `gclid`, `_ga`;
- giữ semantic query như search term, sort, page, mode.

Vì vậy `/search?q=shoe` và `/search?q=phone` vẫn là hai node khác nhau.

Frontier capacity mặc định:

```text
clamp(max_nodes × 4, min=20, max=120)
```

hoặc dùng `frontier.max_size` nếu được cấu hình.

## 6. Xếp hạng và chọn node

### 6.1 Lookahead

Trước mỗi lần chọn node, `_fetch_axtree_for_frontier()` cố lấy AXTree cho URL chưa
có cache/lookahead bằng một browser tạm. `LookaheadPredictor` sinh các candidate:

```json
{"task": "...", "type": "navigation", "confidence": 0.8}
```

Nếu model/API không khả dụng, predictor trả các candidate trung tính có confidence `0.5`.

### 6.2 Công thức score hiện tại

Runtime đang dùng:

```text
S(URL) = α × U(URL) + β × V(URL)
```

Trong đó:

```text
U = variance(confidences) / (mean(confidences) + ε)
V = parent_success_rate × 1 / log(parent_selected_children + 2)
```

- URL chưa có lookahead nhận `U = 1.0`.
- Parent chưa có trajectory dùng prior success rate `0.5`.
- `Diversity D` vẫn có helper trong `scoring.py`, nhưng `compute()` hiện đặt `theta=0`
  và không cộng `D` vào score.

### 6.3 Loose top-band selection

Runtime không luôn lấy URL có score cao nhất. Nó:

1. Lấy tối đa `frontier_select_pool` URL đầu.
2. Giữ các URL có score ít nhất `best_score × frontier_score_band`.
3. Trong pool này ưu tiên:
   - ít prefix retry hơn;
   - ít lần được chọn hơn;
   - depth thấp hơn;
   - score cao hơn;
   - URL lexical order để deterministic tie-break.

Mục tiêu là tránh một nhánh stale liên tục độc chiếm frontier.

## 7. Load một node và khôi phục state

### 7.1 Browser context

Mỗi node tạo một `WebArenaBrowser`. BrowserGym thực tế bắt đầu ở `about:blank`, rồi
wrapper tự `page.goto(start_url)` với navigation timeout cấu hình.

`storage_state` được gắn vào Playwright context để giữ cookies/login.

Runtime **không gọi full server reset trong `_process_node()`**, vì reset server có thể
làm session cookie trong storage state mất hiệu lực. Điều này đồng nghĩa cart/wishlist và
các server-side mutation có thể tồn tại xuyên task/node nếu site không được reset ngoài run.

### 7.2 Prefix trace

Khi Solver đi từ URL A sang URL B, callback lưu một `PrefixTrace` gồm:

- source URL và target URL;
- toàn bộ actions đã đi tới B;
- BID cũ;
- target role/name/fingerprint;
- stateful hint;
- schema version.

Khi B được chọn làm node, runtime ưu tiên:

```text
goto(source_url) → replay natural actions → xác nhận arrived_url == target_url
```

Với mỗi action, prefix replay:

1. Dùng BID cũ nếu role/name vẫn đúng.
2. Nếu BID đổi, tìm đúng một element có cùng role + accessible name.
3. Nếu có nhiều match: `ambiguous_target`.
4. Nếu không có match: `target_not_found`.
5. Validate action trước khi execute.

### 7.3 Prefix failure

- Prefix stateless thất bại: có thể fallback direct goto.
- Prefix được xem là stateful mà thất bại: không direct-goto vì sẽ tạo sai state;
  node được requeue có giới hạn.
- Khi prefix stateful fail trong reset giữa các task, các task còn lại của node được
  short-circuit để tránh lặp cùng một lỗi.
- Hết retry limit: runtime bỏ stale reservation để URL có thể được khám phá lại bằng
  một prefix mới.

Redirect tới một URL đã visited cũng làm node bị skip.

## 8. PageExplorer tạo local tasks

`PageExplorer.propose(obs)` dùng tối đa 6000 ký tự đầu của AXTree và screenshot nếu
model hỗ trợ vision.

Với profile `training_quality`, task list gồm hai nguồn:

1. Deterministic seed tasks từ visible affordances.
2. Task do LLM đề xuất.

Seed tasks có thể bao gồm:

- search;
- feedback/review count;
- hover/menu;
- filter/sort;
- state-changing control;
- cart/checkout flow;
- address/payment/profile/history/communication;
- numeric lookup.

LLM task phải qua các filter:

- không phải login/register task;
- có hoặc được suy ra tag `[INFO]`, `[NAV]`, `[MOD]`;
- không phải multi-action chain quá dài;
- quoted entity phải xuất hiện trên page;
- page phải có affordance tương ứng;
- risky control phải thực sự visible.

Sau đó runtime tiếp tục rank task để bù coverage:

- ưu tiên skill family còn thiếu;
- ưu tiên family ít successful data;
- hạ task/family đã thất bại nhiều;
- bỏ task đã success hoặc vượt retry/saturation counters.

Learned SkillCard hiện không được truyền vào `PageExplorer.propose()`.

## 9. Reset và retry từng task

Trước mỗi task, `_reset_browser_to_node()` cố tái tạo đúng node state:

1. Nếu node có prefix: replay prefix.
2. Nếu stateless replay fail: `browser.reset()` rồi direct goto actual URL.
3. Nếu stateful replay fail: task bị skip và các task còn lại có thể short-circuit.
4. Nếu không có prefix: reset browser; nếu URL sai thì goto actual URL.

Mỗi task có tối đa `task_retry_limit` attempts trong code hiện tại. Giá trị `3` nghĩa
là tối đa ba lần solve, không phải ba retry cộng thêm lần đầu.

Context hints đưa vào Solver gồm:

- account credentials từ `WA_ACCOUNT_*` nếu có;
- checkout safety hint dựa trên `checkout_mode`;
- cấm final order/payment nếu `place_order_allowed=false`.

## 10. Solver action loop

Với mỗi local/composed task, `Solver.solve()` chạy tối đa `max_steps`:

```text
current AXTree + goal + last 5 actions
              │
              ▼
        LLM JSON {thought, action}
              │
              ▼
validate canonical action + visible BID
              │
              ▼
record Step(pre-state + target metadata)
              │
              ▼
browser.act(action)
              │
              ├─ update post URL/predicates
              ├─ callback URL discovery
              ├─ loop/scroll saturation checks
              └─ terminal predicate check nếu có
```

### 10.1 Action validation

Action phải thuộc canonical HSGE/BrowserGym space và target BID phải tồn tại trong
AXTree hiện tại. `goto()` chỉ được cho phép nếu URL đã hiện diện trong goal/page context;
cross-origin hoặc URL tự bịa bị chặn.

Ba invalid actions liên tiếp kết thúc solve attempt.

### 10.2 Planning metadata trên từng Step

Trước khi execute, Solver lưu:

```json
{
  "schema_version": "core-v2+commerce-v2",
  "pre_url": "...",
  "pre_predicates": ["..."],
  "target_bid": "123",
  "target_role": "button",
  "target_name": "'Add to Cart'",
  "target_fingerprint": "button|'add to cart'"
}
```

Sau action, Solver bổ sung `post_url` và `post_predicates`. Đây là evidence chính cho
segmentation, skill effects, prefix semantic regrounding và verification contexts.

### 10.3 Action error và loop protection

- Navigation timeout sau click có thể được xem là action đã execute; Solver tiếp tục
  với observation mới thay vì luôn fail ngay.
- Non-navigation action error kết thúc attempt.
- Cùng action/URL transition lặp ba lần hoặc chu kỳ lặp bị phát hiện sẽ dừng.
- Bốn scroll liên tiếp không đổi observation signature sẽ dừng do saturation.

### 10.4 Success judge

Có hai chế độ:

**Goal có symbolic predicate**

- Thành công ngay khi `reached(goal_predicate, URL, AXTree)` trả true.

**Local natural-language goal**

- Agent phải kết thúc bằng `send_msg_to_user(...)`.
- Answer phải có evidence trong observed pages/actions.
- Hover/menu cần có hover action và menu-like evidence.
- State-changing tasks dùng một LLM judge vì Magento thường update bằng AJAX.
- Information/navigation tasks yêu cầu token đáng kể trong answer xuất hiện trên page.

LLM state-change judge hiện đánh giá “reasonable actions + compatible final state”, nên
đây là một nguồn false positive cần theo dõi khi đọc episodes.

## 11. Ghi episode

Mọi task không bị skip/error đều tạo một episode, kể cả task thất bại.

```text
episodes/ep_NNNN/
├─ episode_meta.json
├─ episode.jsonl
├─ page_state/
│  ├─ step_000_axtree.txt
│  ├─ step_001_axtree.txt
│  └─ final_axtree.txt
└─ screenshots/                 # nếu screenshot=true
```

`episode_meta.json` chứa:

- goal;
- success/reward;
- tag `LOCAL`, `CURRICULUM` hoặc `GOAL`;
- `task_origin` và curriculum provenance (`curriculum_task_id`, chain, revision) nếu có;
- difficulty;
- final URL, predicates và predicate schema.

`episode.jsonl` chứa từng action, repaired thought, pre-action URL/AXTree, screenshot path,
last action và `misc.planning` pre/post evidence.

Coverage counters được cập nhật theo task family và action family.

## 12. URL discovery và frontier expansion

### 12.1 Callback-discovered URL

Sau mỗi Solver action làm URL đổi, `_on_step_completed()` kiểm tra:

- actual URL transition;
- unique trong node;
- same origin;
- chưa visited/queued/discovered;
- không match denylist;
- match allow regex.

URL hợp lệ được lưu cùng `PrefixTrace` và đánh dấu `frontier_eligible`.

### 12.2 DOM fallback

Cuối node, runtime ưu tiên callback-discovered URLs. Chỉ khi không có URL mới từ
callback và depth chưa đạt `max_depth`, runtime lấy same-origin `<a href>` từ DOM.

DOM candidates được:

- normalize/deduplicate;
- check allow/deny/visited/queued;
- gom theo structural URL template;
- score template bằng độ sâu, placeholder, keyword và cluster size;
- diversity-sample theo frontier capacity.

Mỗi child được enqueue ở `depth + 1`, gắn parent URL và lookahead candidates.

## 13. Discovery: trajectory thành SkillCard

Successful **LOCAL** trajectory và successful **CURRICULUM** trajectory (khi feedback bật)
được đưa ngay vào `Discovery.on_trajectory()`. Composed `GOAL` episode hiện được ghi nhưng
không được feed lại vào discovery trong cùng flow.

### 13.1 Low-level graph

Mỗi URL transition giữa các consecutive steps được thêm vào:

```text
graph.states
graph.trajectory_edges[url_before] -> url_after
```

### 13.2 Segmentation

`segment_trajectory()` kết hợp:

1. URL-boundary spans: split khi consecutive step URL đổi.
2. LLM đặt subgoal cho seeded spans.
3. Action-level segments:
   - fill/type có thể ghép với click/press kế tiếp;
   - mỗi click tạo một causal candidate;
   - cart/wishlist/transaction click có thể kéo theo preceding fill/select;
   - hover tạo `inspect menu options` segment.
4. Drop segment chứa `send_msg_to_user` hoặc `goto`.
5. Dedupe theo exact action sequence + subgoal.

Planning evidence của mỗi segment:

```text
planning_preconditions = pre_predicates của step đầu
planning_effects       = post_predicates step cuối - pre_predicates step đầu
```

### 13.3 Online clustering

Mỗi `SubTrajectory` được embed từ:

```text
GOAL + action signature + observed effects
```

Online clusterer gán vào centroid có cosine similarity đạt threshold; nếu không thì tạo
cluster mới. Không có fixed number of clusters.

Khi cluster đạt `skill_maturity`, library thử split behavior trước abstraction. Các family
đang nhận diện gồm:

- `state_change`;
- `save_item`;
- `open_detail`;
- `open_collection`;
- `inspect_feedback`;
- `search`;
- `inspect_menu`;
- generic action signature.

Split chỉ xảy ra khi ít nhất hai family đều có từ hai members trở lên. Minority outlier đơn
lẻ hiện chưa đủ kích hoạt split.

### 13.4 Abstraction

LLM nhận dominant subgoal, modal action verbs và representative examples rồi phải tạo
SkillCard domain-neutral gồm:

- canonical snake_case name;
- description;
- typed slots;
- canonical action template;
- precondition/success predicate;
- execution plan và optional alternatives.

Card được validate để chặn:

- domain-specific/overfit literals;
- noncanonical name;
- natural-language action template;
- value slot bị dùng làm click target;
- invalid slot/action combination.

Nếu LLM output hỏng hoặc quá overfit, deterministic fallback có thể tạo bootstrap card.

Planning evidence được aggregate:

- generic predicate cần support tối thiểu `ceil(2N/3)`;
- commerce milestone hiện chỉ cần một member;
- predicate đã là common precondition không được giữ lại làm effect.

Tên skill sau đó được align với strong evidence, ví dụ cart effects ép về
`activate_state_change_control`.

### 13.5 Duplicate check

Trước verification, candidate được so với skills đã admit:

- cùng name + overlapping non-empty effects → duplicate;
- cùng name nhưng non-overlapping non-empty effects → được giữ như vai trò khác;
- nếu một trong hai effectless → hiện được xem là duplicate.

Nhánh effectless này là limitation đáng chú ý: một generic effectless skill có thể chặn
candidate effectful cùng tên xuất hiện sau.

## 14. Verification gate

### 14.1 Xây verification contexts

Real-browser contexts được tạo từ successful episode transitions, không còn dedupe chỉ theo
episode start URL.

Với candidate có effects, context chỉ hợp lệ nếu:

```text
candidate.planning_effects ⊆ transition.post_predicates - transition.pre_predicates
```

Mỗi context giữ:

- pre-action URL;
- post-action URL;
- transition effects;
- action kind;
- target role/name/fingerprint;
- unique transition identity.

Tối đa 10 contexts được lấy. `effective_k` là:

```text
configured_verify_k = 0: bypass verification gate
bootstrap card có context: 1
card thường: min(configured_verify_k, max(1, number_of_contexts))
```

Nếu không có context và `k > 0`, candidate bị reject.

### 14.2 Ground và execute

Verifier mở browser tại context pre-URL, rồi:

1. LLM bind selector/value slots vào AXTree.
2. Semantic target từ recorded transition được ưu tiên để override generic binding.
3. Nếu LLM grounding fail, deterministic selector scoring được dùng.
4. Render và validate từng action template.
5. Execute trong browser thật.
6. Extract predicates sau execution.
7. Với effectful skill, yêu cầu toàn bộ effects xuất hiện trong observed post-minus-pre delta.

Skill được admit khi đạt ít nhất `effective_k` successes ở các unique context IDs.

### 14.3 Hai tier sau admission

```text
verified nhưng planning_ready=false
    → execution-only SkillCard
    → thường do effects rỗng; cũng có thể do effects chưa planning-verify đủ k
    → có trong SkillLibrary/skills.json
    → không có Operator

verified + effects non-empty + effects verify đủ k
    → planner-ready SkillCard
    → thêm vào HierarchicalGraph + OperatorGraph
```

Execution-only skill hiện vẫn được tính vào family diversity metrics.

### 14.4 Limitation của effectless verification

Với effectless card, context builder hiện không lọc action kind/effect và browser verifier
không đánh giá natural-language `success_predicate`; action execute không lỗi có thể đủ để
được admit. Vì vậy `verified=true` của effectless skill nên được hiểu là “groundable/executable”,
không phải “đã chứng minh semantic outcome”.

## 15. Admission callback, graph và operator

Khi library admit một card, runtime:

1. Emit `skill.admitted` event.
2. Nếu `planning_ready`, derive `Operator.from_skill(card)` với cùng `skill_id`.
3. Ghi `skills.json` ngay để không mất dữ liệu nếu run bị interrupt.
4. Refresh skill-family metrics.
5. Với planner-ready card, ghi lại graph và curriculum.

`Discovery` cũng nối skill với boundary URLs của segment khi tìm được member tương ứng:

```text
state URL → skill → effect URL
```

High-level composition edge được derive thuần symbolic:

```text
A → B iff A.effects ∩ B.preconditions != ∅
```

URL co-occurrence không tạo composition edge.

## 16. Curriculum execution và composed GOAL task

Sau local exploration, runtime reset về node, lấy predicates mới nhất và sinh curriculum
khả thi từ chính state đó. Scheduler chọn tối đa `curriculum.max_tasks_per_node` task theo
số lần đã attempt, difficulty, goal và chain. Mỗi task được concrete hóa theo AXTree hiện tại,
reset riêng, chạy bằng Solver với symbolic goal predicate và ghi tag `CURRICULUM`.

Curriculum episode thành công được feed lại vào Discovery nếu
`curriculum.feed_success_to_discovery=true`. Mỗi attempt được audit trong
`curriculum_executions.jsonl` và có stable `curriculum_task_id`.

Sau Curriculum Tasks, runtime lập lại Goal plan để operator vừa được admit có thể được dùng ngay.

`plan()` chạy forward BFS trên predicate state:

1. Operator applicable khi toàn bộ preconditions nằm trong current state.
2. Apply bằng cách union effects.
3. Bỏ operator không thêm predicate mới.
4. Trả shortest skill-id chain đầu tiên đạt goal.

Sau local exploration của một node, runtime gọi `_goal_task()`:

- Nếu `terminal_goal` được cấu hình, dùng goal đó.
- Nếu không và `auto_terminal_goals=true`, chỉ thử auto goal khi thấy transactional state/operator.
- Candidate auto goals theo thứ tự: confirmation cue → checkout path → progress control.
- Nếu không có plan, không chạy GOAL episode.
- Nếu có plan, LLM composer tạo một concrete instruction nhưng phải giữ nguyên skill order.
- Solver thực thi instruction độc lập; skill chain không được biến thành tool calls cho Solver.
- Mỗi goal có tối đa `max_goal_attempts` full attempts.
- Curriculum runner và Goal runner đều được gọi ở mỗi node; Solver chỉ chạy khi có plan reachable.

## 17. Curriculum generation

Curriculum lấy root predicates đã ghi ở depth 0 làm initial state. Với mỗi effect trong
OperatorGraph:

1. Planner tìm shortest chain từ initial predicates.
2. Goal đã có sẵn ở root bị bỏ.
3. Goal unreachable bị bỏ.
4. Difficulty bằng số skill trong chain.
5. Terminal flag chỉ true nếu effect thuộc terminal goal predicates.

Do đó curriculum phản ánh đúng operator graph hiện có. Nếu graph chỉ có hai atomic operator
không nối được nhau, curriculum cũng chỉ có difficulty-1 tasks.

## 18. Kết thúc một node

Sau tasks và optional GOAL phase, runtime:

1. Cập nhật node success rate cho FrontierScorer.
2. Expand frontier từ callback URLs hoặc DOM fallback.
3. Ghi một record vào `frontier.jsonl` với full frontier score breakdown.
4. Ghi:
   - `nodes/node_N/summary.json`;
   - `nodes/node_N/node_info.json`.
5. Đóng browser.
6. Trả actual processed URL.
7. Main loop commit requested/actual URL vào `visited`, release `queued`.
8. Tăng `nodes_processed`.
9. Save checkpoint.

Node load/process error được isolate; run tiếp tục với frontier còn lại hoặc bounded recovery.

## 19. Checkpoint và resume

Checkpoint version hiện tại là `5`. Sau mỗi processed node hoặc recovery, runtime lưu:

- frontier, visited, queued;
- episode counter và nodes processed;
- pending prefix traces;
- frontier scorer state;
- URL attempts/success rates;
- selection/retry counters;
- root curriculum predicates;
- curriculum task attempt/success counters;
- hierarchical URL-skill edges;
- online cluster centroids/member IDs.

Verified SkillCards không nằm trực tiếp trong checkpoint; chúng được restore từ `skills.json`.
Planner-ready operators được derive lại từ restored cards.

`--resume` mở logs ở append mode, load checkpoint và skills/curriculum/transfer artifacts.
Implementation hiện đánh dấu full state restored và bỏ episode replay. Vì vậy resume quality phụ
thuộc vào clusterer/hierarchical state deserialize thành công; warning trong console cần được xem
như một tín hiệu checkpoint restore không đầy đủ.

`KeyboardInterrupt` được bắt ở node boundary handler:

- đóng active browser;
- đưa selected URL trở lại frontier;
- save checkpoint;
- export graph/curriculum/metrics;
- kết thúc với event `run.interrupted`.

## 20. Output artifacts và thời điểm cập nhật

```text
outputs/<run>/
├─ run.log
├─ events.jsonl
├─ metrics_latest.json
├─ metrics.json
├─ coverage.json
├─ checkpoint.json
├─ frontier.jsonl
├─ skills.json
├─ skill_diagnostics.json
├─ graph.json
├─ curriculum.json
├─ curriculum_diagnostics.json
├─ curriculum_executions.jsonl
├─ transfer.json                      # nếu chạy transfer eval
├─ nodes/node_N/
│  ├─ summary.json
│  └─ node_info.json
└─ episodes/ep_NNNN/
   ├─ episode_meta.json
   ├─ episode.jsonl
   ├─ page_state/*.txt
   └─ screenshots/*.png
```

| Artifact | Khi nào cập nhật |
| --- | --- |
| `events.jsonl` | Liên tục theo event level. |
| `run.log` | Liên tục cho human-readable milestones/errors. |
| `episode_*`, `coverage.json` | Sau mỗi recorded task. |
| `skill_diagnostics.json` | Sau mỗi discovery diagnostic event. |
| `skills.json` | Ngay khi admit skill và cuối run. |
| `graph.json`, `curriculum*.json` | Run start, planner-ready admission, checkpoint, periodic/final export. |
| `metrics_latest.json` | Run start, admission và checkpoint snapshots. |
| `metrics.json` | Chỉ khi run kết thúc/interrupted qua finalization path. |
| `checkpoint.json` | Sau mỗi node hoặc recovery/interrupt. |

Trong khi run đang chạy, `metrics_latest.json` có thể mới hơn hoặc cũ hơn một số append-only
logs. `skills_discovered` chỉ được set lại từ library size ở finalization, nên có thể tạm bằng 0
dù `skills_verified > 0` trong live snapshot.

## 21. Safety boundaries

### URL/browser safety

- Same-origin URL only.
- Allow regex bắt buộc cho frontier admission.
- `/logout` luôn bị deny mặc định.
- User-configured denylist được áp dụng thêm.
- `goto` bị giới hạn vào URL có evidence trong context.

### Transaction safety

| Mode | Hành vi |
| --- | --- |
| `discover-only` | Chỉ inspect/report flow; không submit hoặc mutate transaction form. |
| `safe` | Có thể đi qua cart/checkout nhưng chặn final Place Order/Pay Now nếu không cho phép. |
| `full` | Cho explore sâu hơn, nhưng final order vẫn phụ thuộc `place_order_allowed`. |

PageExplorer seed/filter và Solver context hints đều nhận safety configuration, nhưng WebArena là
stateful; các action như cart/wishlist/compare vẫn có thể mutate shared site.

## 22. Known limitations của flow hiện tại

Các điểm sau là hành vi thực tế cần nhớ khi đọc log hoặc thiết kế run tiếp theo:

1. **Effectless verification yếu.** Action chạy được có thể đủ để admit execution-only card.
2. **Effectless duplicate có thể chặn effectful candidate cùng tên.** Duplicate policy hiện xem
   một bên effectless là duplicate.
3. **Cluster drift sau admission.** Planning-ready cluster không tự re-abstract khi action
   signature/behavior mới tiếp tục nhập vào.
4. **Maturity đếm segments, không đếm unique episodes.** Nhiều segment từ một episode có thể
   làm cluster đạt maturity sớm.
5. **Commerce milestone support bằng 1.** Một rare effect trong mixed cluster có thể ảnh hưởng
   abstraction trước khi đủ independent evidence.
6. **Persistent site state.** Cart/wishlist đã true làm boolean delta bão hòa và khó verify lại.
7. **Predicate noise.** Dense Magento page có thể đồng thời bị gắn collection/detail/cart-like
   predicates, tạo preconditions quá rộng.
8. **Skill reuse chưa nằm trong action policy.** Skill chain định hướng instruction của
   Curriculum/Goal task nhưng Solver vẫn giải từ đầu bằng primitive actions.
9. **Diversity metrics tính cả execution-only skills.** `skill_diversity_met=true` không đồng
   nghĩa planner-ready graph có đủ family.
10. **No independent operator mining.** Successful trajectory không trực tiếp tạo operator;
    nếu SkillCard không qua planning verification thì graph không nhận effect đó.

## 23. Ví dụ một transition Add to Cart

```text
PageExplorer:
  [MOD] Add the visible item to the cart

Solver pre-state:
  URL = /item.html
  predicates = {item_selected, view:detail, ...}
  target = button|'add to cart'

Solver action:
  click('1328')

Solver post-state:
  predicates = {item_selected, view:detail, cart_nonempty, on_cart, ...}

Recorded Step effect:
  {cart_nonempty, on_cart}

Discovery:
  action-level segment = "add item to cart"
  signature = click
  behavior family = state_change

Cluster maturity:
  ≥ configured maturity

Abstraction:
  name = activate_state_change_control
  template = click({selector_slot})
  effects = {cart_nonempty, on_cart}

Verification contexts:
  only transitions whose observed delta includes both effects

If verify ≥ k:
  SkillCard planner_ready=true
  → Operator(preconditions → cart_nonempty/on_cart)
  → graph/curriculum có thể plan tới cart
```

Nếu cart đã non-empty trước action, delta có thể rỗng và transition đó không còn là evidence tốt
cho boolean effect. Đây là lý do reset strategy hoặc non-saturating predicate vẫn quan trọng.

## 24. Cách đọc code theo flow

Đọc theo thứ tự sau để bám đúng runtime:

1. `run_webarena.py::main`
2. `hsge/webarena/runtime.py::WebArenaExplorer.__init__`
3. `hsge/webarena/runtime.py::run`
4. `hsge/webarena/runtime.py::_process_node`
5. `hsge/webarena/agents.py::PageExplorer.propose`
6. `hsge/webarena/agents.py::Solver.solve`
7. `hsge/webarena/runtime.py::_on_step_completed`
8. `hsge/discovery.py::Discovery.on_trajectory`
9. `hsge/segmentation.py::segment_trajectory`
10. `hsge/library.py::SkillLibrary.observe/_try_admit`
11. `hsge/abstraction.py::abstract_cluster`
12. `hsge/webarena/verification_context.py::_build_browser_contexts`
13. `hsge/verification.py::verify_skill/ground_and_execute`
14. `hsge/graph.py`, `hsge/operators.py`, `hsge/curriculum.py`

## 25. Checklist khi đánh giá một run

Không chỉ nhìn `skills_verified`. Nên kiểm tra theo thứ tự:

1. Run đã `completed`, `interrupted`, hay vẫn đang active?
2. Bao nhiêu node/episode và bao nhiêu successful LOCAL trajectories?
3. `segments_created` và `clusters_matured` có đến từ unique episodes không?
4. Skill name/description/template có khớp planning effects không?
5. Verification contexts có đúng action/target family không?
6. Bao nhiêu card là execution-only và bao nhiêu planner-ready?
7. Duplicate events có chặn candidate effectful không?
8. Operator preconditions có tối thiểu và ổn định không?
9. Graph có composition edges hay chỉ atomic operators?
10. Curriculum có difficulty > 1 và terminal/reachable goal hợp lý không?
11. Prefix retry/direct-goto có làm mất stateful semantics không?
12. Metrics snapshot có cùng timestamp với logs/artifacts đang so sánh không?
