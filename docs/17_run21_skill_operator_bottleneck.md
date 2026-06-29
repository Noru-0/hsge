# Run 21: Skill → Operator → Curriculum Bottleneck

## Status

Run 21 confirms that the operator and curriculum infrastructure is active, but
the learned graph is still too sparse for long-horizon composition. At the
22-node checkpoint the run had produced:

- 128 episodes, including 72 successful tasks;
- 4 execution-verified skills;
- 1 planner-ready operator (`submit_search_query`);
- 0 composition edges;
- 2 reachable curriculum goals, both one-step search effects;
- 0 terminal tasks.

The planner is not the component losing the purchase chain. It correctly plans
over the operator graph it receives. The bottleneck is the conversion of
successful, effectful trajectories into specialized planner-ready skills.

## Concrete evidence

Several successful Add to Cart episodes contain the expected exact predicate
delta. For example:

```text
before click: item_selected
after click:  item_selected + cart_nonempty + on_cart
effect:       cart_nonempty + on_cart
```

Despite this evidence, the admitted `activate_named_control` skill has empty
planning effects. Therefore it remains execution-only and never creates an
`add_to_cart` operator.

## Where the effect is lost

### 1. Heterogeneous actions share one cluster

The current embedding and abstraction pipeline frequently groups actions with
the same primitive signature (`click`) and generic subgoal label. Category
navigation, product opening, option selection, Add to Cart, wishlist actions,
and pagination can therefore become members of the same
`activate_named_control` cluster.

### 2. Support aggregation removes minority effects

`_planning_evidence()` retains predicates supported by at least two thirds of a
cluster. A cluster containing many unrelated clicks will not retain
`cart_nonempty`, even when every actual Add to Cart member establishes it.

```text
heterogeneous click members
    → cart_nonempty appears in a minority
    → fails the 2/3 support threshold
    → planning_effects = {}
```

The support rule is reasonable for a coherent cluster; the failure is that the
cluster is not effect-coherent.

### 3. Persistent session state saturates boolean predicates

The shopping session preserves cart state across episodes. After the first cart
addition, later episodes may begin with `cart_nonempty` already true:

```text
pre  = {..., cart_nonempty}
post = {..., cart_nonempty}
post - pre = {}
```

Because abstraction also excludes effects that are common preconditions, a
persistent cart makes `cart_nonempty` increasingly likely to disappear from the
learned effect set. A monotonic boolean cannot distinguish `cart count 1 → 2` or
`item absent → item present`.

### 4. Segmentation does not always isolate the causal action

An Add to Cart task may include opening a product, selecting an option, changing
quantity, clicking Add to Cart, and reporting completion. Broad segments mix
setup actions with the causal action. Action-level segments help, but their
generic labels can still send all clicks into the same cluster.

### 5. Admitted effectless skills are not revised

An execution-only skill may be admitted before enough effect evidence exists.
Later observations continue to update clusters, but an already abstracted skill
is not automatically re-abstracted. A new candidate with the same generic name
may also be rejected as a duplicate instead of revising or splitting the
existing skill. Consequently, new cart evidence cannot upgrade the old skill.

### 6. Some predicates describe incidental UI rather than the main state

Mini-cart content can cause `on_cart` to appear on product or search pages.
Collection and detail predicates can also coexist on dense storefront pages.
These noisy predicates create overly broad operator preconditions and make
effect/precondition composition brittle.

## Downstream consequence

The intended chain requires one producer for every intermediate predicate:

```text
search          → results_shown
open_product    → item_selected
add_to_cart     → cart_nonempty
checkout        → on_checkout
enter_payment   → payment_entered
place_order     → order_confirmed
```

Run 21 currently provides only the first producer. With no operator producing
`item_selected` or `cart_nonempty`, the graph cannot derive composition edges.
The curriculum planner therefore emits only the reachable one-step search goals.

## Recommended repair order

1. Cluster by semantic target intent and observed effect in addition to action
   signature. Add to Cart, wishlist, navigation, and pagination must not share a
   generic click cluster.
2. Prefer action-level causal segments when a single action introduces a
   canonical effect.
3. Split a mature cluster when its members have incompatible effect signatures,
   instead of allowing the support threshold to erase all effects.
4. Re-abstract or revise an execution-only skill when new evidence changes its
   supported effects; duplicate detection must compare planning semantics, not
   name alone.
5. Separate page-location predicates from global widget state: `on_cart` should
   require main cart-page evidence, while mini-cart evidence may establish only
   `cart_nonempty`.
6. Add non-saturating commerce evidence such as `cart_count_increased` or an
   observed item-added confirmation, or reset cart state in verification
   contexts.
7. Minimize operator preconditions to predicates that are necessary and stable,
   rather than retaining every common page cue.

## Acceptance criteria for the next run

- At least two independently verified `add_to_cart` contexts produce the same
  canonical cart effect.
- `open_product` and `add_to_cart` are distinct planner-ready skills.
- The graph contains `open_product → add_to_cart` through
  `item_selected` matching.
- A reachable cart goal yields a curriculum task with difficulty greater than
  one.
- Adding more unrelated click trajectories cannot remove an already verified
  cart effect.
- Mini-cart content alone never establishes `on_cart`.

`order_confirmed` is not expected while `checkout.mode=safe` and
`place_order_allowed=false`; intermediate cart and checkout chains are still
expected and are the appropriate validation target for safe runs.
