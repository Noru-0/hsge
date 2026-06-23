# Training Data and Evaluation Issues

This note summarizes the current problems found in the training data and in the
WebArena evaluation setup. The main point is simple: the model is not only weak
because of model quality. A large part of the failure comes from action-space
mismatch, noisy demonstrations, weak element grounding, and missing small-task
coverage.

## 1. Training Data Issues

### Invalid Actions in Training Data

The training data contains actions that are not valid for the current WebArena
execution path:

- `go_back()`
- `functions.GatherProductInfo`
- `multi_tool_use.parallel`
- Natural-language actions such as:
  - `"Select ... for comparison"`
  - `"Filter results by price..."`

These examples teach the model that it can output tool calls or plain English
commands that the evaluator cannot execute. During evaluation, this becomes a
direct action parsing or action mapping problem.

### Hallucinated BIDs

There are 6 actions that refer to element IDs that do not exist, or use text
instead of numeric BIDs:

```text
fill('comment_field_id', '...')          # BID is text, not a number
click('Tweezers For Succulents Duo')     # product name used instead of BID
fill('Energy Drink')                     # text used instead of BID
click('[1396] list')                     # invalid BID format
click('Blue')                            # text used instead of BID
```

These are hallucinated BIDs. The agent is guessing an element identifier instead
of grounding the action in the current accessibility tree.

### Weak Thought-to-Action Grounding

About 38.7% of thoughts do not mention the action type that is taken next.

Example pattern:

```text
Thought: I need to add the item to the cart.
Action: click('1501')
```

The thought explains the high-level goal, but it does not say that the next step
is a click, nor does it connect the target element to the action. This makes the
reasoning less grounded and gives the model fewer examples of how to choose a
specific executable action.

About 15.1% of thoughts contain a numeric BID. That is not necessarily bad, but
it means most examples still do not explicitly connect the reasoning to the
screen element being used.

### Missing Action Coverage

The current data is missing or under-represents important browser actions:

- `scroll`
- `hover`
- explicit search submission
- reading visible information and answering with `send_msg_to_user`

This shows up in several task types:

- Tasks that require scrolling often fail because the agent cannot move through
  the page properly.
- Tasks that require hover menus cannot be solved reliably.
- Tasks that require reading reviews often reach the review section, then keep
  clicking around instead of reading the text and answering.
- The agent does not yet reliably know how to search for a product using the
  search bar.

These issues likely share the same root cause: the action space is too small,
and the proposed tasks are too high-level. Because of that, the dataset has too
few small, isolated tasks for basic browser skills such as searching, scrolling,
hovering, reading reviews, and extracting information.

## 2. Evaluation Issues

### Action Mismatch with WebArena

The actions in the training data do not match the WebArena benchmark action
format directly. They need a clean mapping layer before evaluation.

If the mapping is loose or incomplete, the model may output an action that looks
reasonable in the training format but becomes invalid or semantically wrong in
WebArena.

### Login Tasks Are Currently Broken

Several WebArena benchmark tasks require login. WebArena provides a script to
prepare cookies automatically for those tasks, but the current setup still fails.

Current reproduced behavior:

1. The login script runs successfully.
2. The session appears to be logged in.
3. After clicking the "My Account" page, the site logs out again.

This means login-required tasks are not reliable evaluation targets yet. They
should either be fixed first or separated from the main evaluation score.

### Scroll-Dependent Tasks Fail

Many WebArena tasks require scrolling. Since the current action space and
training data do not properly cover scroll behavior, these tasks fail even when
the model has otherwise reached the right page.

This is especially visible in product detail and review tasks, where important
information may be below the fold.

### Information Extraction Tasks Fail

Some tasks require the agent to read information from the page and return an
answer.

Example:

```text
Who complained about this product in the reviews?
```

The agent can sometimes reach the correct review area, but then it continues to
click randomly instead of reading the visible text and answering. This suggests
the current training data over-teaches navigation/clicking and under-teaches
read-and-answer behavior.

## 3. Training Coverage vs WebArena Test Coverage

The current training set covers some shopping workflows, but it misses many
WebArena task types. The table below compares the available training examples
against task types present in the WebArena benchmark.

| Task Type | Training | WebArena | Status |
|---|---:|---:|---|
| View Product Details | OK 21 | ? | Covered in training, unclear WebArena count |
| Search + Add to Cart/Wishlist | OK 18 | OK | Covered |
| Browse + Add to Cart/Wishlist | OK 9 | OK | Covered |
| Compare Products | OK 8 | OK | Covered |
| Read Reviews | OK 5 | OK | Covered but likely too shallow |
| Remove from Wish List | OK 3 | ? | Covered in training, unclear WebArena count |
| Cart Management | OK 2 | ? | Covered in training, unclear WebArena count |
| Filter/Sort | OK 2 | OK | Covered but low volume |
| Checkout/Purchase | OK 1 | OK 7 | Missing volume |
| Subscribe | OK 1 | ? | Covered in training, unclear WebArena count |
| Order History Query | Missing 0 | OK 5 | Missing |
| Order Status Tracking | Missing 0 | OK 5 | Missing |
| Account/Address Update | Missing 0 | OK 11 | Missing |
| Review Analysis (sentiment) | Missing 0 | OK 6 | Missing |
| Refund/Reorder | Missing 0 | OK 10 | Missing |
| Market Survey/Analytics | Missing 0 | OK 15 | Missing |
| Price Range Analysis | Missing 0 | OK 5 | Missing |
| Product Rating | Missing 0 | OK 7 | Missing |
| Contact/Draft Message | Missing 0 | OK 5 | Missing |
| Complex Purchase (budget) | Missing 0 | OK 5 | Missing |

The biggest gap is not only the number of samples. It is the missing task
families. Several WebArena task types have zero corresponding examples in the
training data, so the model has no chance to learn those behaviors from SFT.

## 4. Likely Root Causes

The failures seem to come from a few connected causes:

- The action space is smaller than what WebArena tasks require.
- Training examples include invalid actions and hallucinated element IDs.
- Thoughts often describe the goal but not the concrete next action.
- The dataset has too many high-level tasks and too few small skill-focused
  tasks.
- Read-and-answer tasks are under-represented compared with click/navigation
  tasks.
- Evaluation still has infrastructure issues, especially login persistence.
