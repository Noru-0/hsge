# 16 - Current Explore Flow and Data Flow

Tài liệu này tóm tắt ngắn gọn luồng explore hiện tại sau các thay đổi lớn trong
WebArena runtime. Các docs cũ vẫn hữu ích để hiểu ý tưởng HSGE gốc, nhưng file
này nên được đọc trước khi chạy hoặc sửa `run_webarena.py` và
`hsge/webarena/runtime.py`.

## Mục tiêu hiện tại

Runtime hiện tại không chỉ duyệt URL và lưu trajectory. Nó vận hành một vòng lặp
khép kín:

1. chọn frontier node có triển vọng;
2. tạo các task nhỏ, grounded trên page hiện tại;
3. dùng solver thực thi task và ghi episode training;
4. từ trajectory thành công, học skill, mine operator, cập nhật graph;
5. dùng skill/operator đã học để gợi ý task tiếp theo, compose goal dài hơn;
6. xuất đầy đủ artifact để resume, debug, train SFT, curriculum và transfer.

Các thay đổi vẫn giữ nguyên nguyên tắc domain-agnostic: không hardcode shopping
hay một site cụ thể vào core flow. Những phần liên quan checkout/order-flow đều
được xử lý bằng affordance/predicate/risk pattern tổng quát và có safety mode.

## Entry Point

Chạy chính:

```bash
PYTHONPATH=. python run_webarena.py --root-url "$WA_SHOPPING" --out outputs/wa_run --max-nodes 20
```

Các flag quan trọng:

- `--provider`, `--model`, `--explorer-model`, `--solver-model`: tách model rẻ
  cho proposer/lookahead và model mạnh hơn cho solver.
- `--resume`: khôi phục từ `checkpoint.json`, `skills.json`,
  `curriculum.json`, `transfer.json`.
- `--screenshot`: lưu screenshot từng step nếu backend/browser hỗ trợ.
- `--storage-state`: dùng session đã login sẵn.
- `--checkout-mode safe|full|discover-only` và `--place-order-allowed`: giới
  hạn hành vi có rủi ro trong transaction flow.
- `--dry-run`: kiểm tra wiring offline bằng fake browser và mock LLM.

## Explore Flow

### 1. Khởi tạo runtime

`run_webarena.py` tạo:

- `PageExplorer`: đề xuất task local từ AXTree hiện tại.
- `Solver`: action loop sinh từng action JSON và gọi browser.
- `SkillLibrary`: observe -> cluster -> abstract -> verify -> admit.
- `Discovery`: nhận trajectory thành công, segment và đưa vào library.
- `OperatorGraph` + `HierarchicalGraph`: lưu predicate operators và skill graph.
- `FrontierScorer` + `LookaheadPredictor`: chấm điểm frontier theo U/V.

`WebArenaExplorer` cũng mở các file log/output, cấu hình denylist mặc định cho
`/logout`, đọc credential hints từ `WA_ACCOUNT_*`, và chuẩn bị checkpoint state.

### 2. Chọn frontier node

Frontier không còn FIFO thuần. Trước mỗi vòng lặp:

1. `_fetch_axtree_for_frontier()` cố lấy AXTree cho các URL chưa visit.
2. `LookaheadPredictor` sinh candidate task + confidence cho mỗi URL.
3. `FrontierScorer` tính điểm:
   - `U`: uncertainty từ variance/mean của confidence lookahead;
   - `V`: value từ success rate của parent, có penalty khi đã chọn nhiều sibling.
4. `_select_frontier_node()` chọn trong top-score band nhỏ để tránh một nhánh
   stale độc chiếm explore.

Mỗi snapshot frontier được ghi vào `frontier.jsonl` với score breakdown.

### 3. Load node và recover state

Khi chọn URL, runtime tạo browser mới và ưu tiên recover bằng prefix trace:

- Trong lúc solver chạy, `_on_step_completed()` bắt các URL transition thật.
- Mỗi URL mới được lưu cùng `PrefixTrace`: source URL, target URL, action đã dẫn
  tới target, và các step replayable.
- Khi URL này được chọn từ frontier, `_navigate_via_prefix()` replay click/fill
  tự nhiên thay vì chỉ `goto()`, giúp giữ đúng session/state.

Nếu prefix stale hoặc load ra empty observation, runtime requeue có giới hạn rồi
mới release URL. Lỗi ở một node được cô lập, ghi log/checkpoint và vòng lặp tiếp
tục.

### 4. Detect domain ở root

Ở depth 0, `PageExplorer.detect_domain()` đọc AXTree để ghi `domain.json`:

- `domain_type`
- `common_tasks`
- `common_actions`

Thông tin này chỉ làm reference cho proposer. Task vẫn phải grounded trên page
hiện tại, không copy nguyên các pattern generic.

### 5. Propose và lọc local tasks

`PageExplorer.propose()` kết hợp:

- seed tasks deterministic theo affordance visible;
- LLM proposals;
- skill hints từ library đã admit;
- domain context từ root.

Task proposal được lọc để loại:

- login/signup task;
- action-chain quá dài;
- task quá phức tạp;
- quote không xuất hiện trên page;
- task đòi affordance hoặc risky control không visible.

Runtime tiếp tục rank task bằng coverage: ưu tiên family còn thiếu skill hoặc còn
ít successful examples, tránh lặp task đã thành công hoặc fail quá nhiều.

### 6. Solve task và ghi episode

Với mỗi task local:

1. browser được reset lại về node state;
2. runtime thêm safety hint, account hint, skill hints và tool definitions từ
   skill library;
3. `Solver.solve()` sinh từng action trong action space WebArena/HSGE;
4. action được validate/repair theo AXTree hiện tại;
5. kết quả được terminal-check bằng `reached()`.

Mỗi task, kể cả fail, được ghi thành một episode dưới `outputs/.../episodes/`.
Successful episode sau đó đi tiếp vào discovery/operator mining.

### 7. Skill discovery

Với trajectory thành công:

1. `Discovery.on_trajectory()` thêm URL transitions vào low-level graph.
2. `segment_trajectory()` tách trajectory thành sub-trajectories.
3. `SkillLibrary.observe()` embed từng subtraj và đưa vào `OnlineClusterer`.
4. Khi cluster đủ maturity, `abstract_cluster()` tạo `SkillCard`.
5. `verify_skill()` replay skill trên held-out contexts từ các episode đã có.
6. Skill pass verification được admit, ghi ngay vào `skills.json`.

Nếu abstraction/verification fail, cluster không bị đánh dấu chết vĩnh viễn; nó
có thể retry khi có thêm member/context mới. `skill_diagnostics.json` lưu các
sự kiện như segment created, cluster matured, rejection reason, admitted skill.

### 8. Operator mining và composed goals

Song song với skill discovery, `_mine_operator()` lấy predicate delta:

```text
start predicates = predicates_from(start_url, start_axtree)
end predicates   = predicates_from(final_url, final_axtree)
effect           = end - start
```

Từ đó tạo `Operator(name, preconditions, effects)`. `_sync_to_hierarchical_graph()`
biến operator thành skill node ảo trong `HierarchicalGraph` và tạo composition
edge khi effect của operator A thỏa precondition của operator B.

Nếu có `--terminal-goal`, hoặc auto terminal goal phát hiện transaction predicate
phù hợp, `plan()` BFS trên `OperatorGraph` để tạo composed goal task dài hơn.
Goal task cũng được solve, record và verify như local task.

### 9. Mở rộng frontier

Frontier ưu tiên URL phát hiện trong lúc solver thực sự navigate, vì chúng có
prefix trace đã biết reachable. Nếu không có callback-discovered URL, runtime
fallback sang `browser.links()`.

Fallback link list được đưa qua `filter_frontier()`:

- extract URL templates bằng position-based variable detection;
- score template cluster bằng heuristic domain-agnostic;
- sample đa dạng theo depth trong budget.

Mỗi child mới được set parent trong scorer và có lookahead candidates để lần
chọn sau có U/V score.

## Data Flow

```text
root_url
  -> frontier [(url, depth)]
  -> lookahead candidates + U/V score
  -> selected node
  -> AXTree/browser observation
  -> PageExplorer tasks
  -> Solver steps
  -> episode artifacts
  -> successful trajectory
       -> Discovery -> segmentation -> clustering -> abstraction -> verification -> skills.json
       -> predicate delta -> OperatorGraph -> HierarchicalGraph -> graph.json
  -> discovered URLs / DOM links
  -> filtered frontier
  -> checkpoint.json
```

Training data path:

```text
outputs/wa_run/episodes/
  -> build_sft_dataset.py
  -> train.jsonl
```

`build_sft_dataset.py` đọc các episode thành công, dựng lại prompt theo solver
action space, thêm AXTree + recent action history, và xuất mỗi step thành một
SFT chat example. Có thể xuất format `hsge_json`, `webarena_id`, hoặc
`webarena_json`.

## Output Artifacts

Một run hiện tại có thể tạo:

- `run.log`: log chính, gồm node, task outcome, skill/graph/curriculum updates.
- `events.jsonl`: append-only structured events với correlation theo `run_id`,
  `node_id`, `task_id`, `episode_id`; gồm URL funnel, frontier decisions,
  solver outcomes, skill admission và planner decisions.
- `metrics_latest.json`: snapshot counters sau mỗi checkpoint.
- `frontier.jsonl`: snapshot frontier sau từng node, gồm score, U, V, parent SR.
- `checkpoint.json`: frontier, visited, queued, discovered prefix traces,
  operator graph, hierarchical graph edges, clusterer state, scorer state.
- `domain.json`: domain summary ở root.
- `coverage.json`: coverage theo task family/action family và success/fail.
- `metrics.json`: tổng hợp nodes, tasks, skills, operators, errors.
- `skills.json`: skill đã verify/admit, ghi ngay khi admit.
- `skill_diagnostics.json`: trace chi tiết của discovery/verification.
- `graph.json`: low-level URL graph + high-level skills/operators/composition.
- `curriculum.json`: shortest planner chain tới từng reachable goal predicate,
  sắp easy-to-hard; terminal goal giữ nguyên full long-horizon chain.
- `transfer.json`: kết quả retrieve/adapt skill nếu gọi transfer eval.
- `nodes/node_N/node_info.json`: metadata từng node, gồm children, tasks,
  score breakdown, lookahead, prefix trace.
- `nodes/node_N/summary.json`: compact frontier delta, task outcomes, Solver URL
  funnel, skill/operator delta và planner status.
- `episodes/ep_XXXX/episode_meta.json`: goal, success, difficulty, tags.
- `episodes/ep_XXXX/episode.jsonl`: từng step với thought, parsed action,
  observation path và optional `last_action`.
- `episodes/ep_XXXX/page_state/*.txt`: AXTree từng step.
- `episodes/ep_XXXX/screenshots/*.png`: screenshot từng step nếu bật.

## Module Map Hiện Tại

- `run_webarena.py`: CLI, provider/model resolution, dry-run, browser factory.
- `hsge/webarena/runtime.py`: vòng lặp explore, checkpoint/resume, record,
  skill hints, operator mining, graph/curriculum/export.
- `hsge/webarena/agents.py`: `PageExplorer`, `Solver`, action-space prompt,
  task filtering, deterministic seed tasks.
- `hsge/webarena/scoring.py`: lookahead và U/V frontier scoring.
- `hsge/webarena/frontier_filter.py`: template clustering và fallback link filter.
- `hsge/webarena/action_validation.py`: parse/validate/repair action và task/action
  family helpers.
- `hsge/webarena/predicates.py`: predicate extraction và terminal condition check.
- `hsge/library.py`: skill lifecycle, retryable abstraction/verification, retrieval.
- `hsge/discovery.py`: online hook từ trajectory sang segmentation/library/graph.
- `hsge/operators.py`: precondition/effect operators và BFS planning.
- `build_sft_dataset.py`: chuyển episode artifacts thành SFT JSONL.

## Những cải tiến chính so với flow cũ

- Tách rõ explorer model, solver model và lookahead model.
- Frontier chọn bằng score U/V thay vì FIFO đơn giản.
- URL mới có prefix trace replay, giúp recover các state không thể tái tạo bằng
  direct `goto()`.
- Task proposal có seed deterministic, domain context, skill hints, filtering và
  coverage-aware ranking.
- Solver có action validation, richer action docs, account hint, skill tools và
  screenshot support.
- Skill discovery có diagnostics, duplicate check, retry khi abstraction/verify
  fail, và admit callback ghi `skills.json` tức thì.
- Operator mining dùng predicate delta để tạo graph composition thật, thay vì
  cạnh đồng xuất hiện trong trajectory.
- Resume lưu gần như toàn bộ state: frontier, scorer, prefix traces, operator
  graph, hierarchical graph và clusterer.
- Output phục vụ cả debug và training: node info, coverage, metrics, graph,
  curriculum, transfer, episode AXTree/screenshot.
