"""Verification gate — the quality story that separates this from offline
workflow induction (AWM). A freshly abstracted skill is a *hypothesis*; it is
admitted to the library only if it can be grounded and executed successfully in
>= k distinct contexts.

Grounding (binding slots to a concrete page) is delegated to the LLM; execution
and the success check go through the env. We also update per-skill stats so the
library can prune decayers later.
"""
from __future__ import annotations

import json
import re

from .env import PageState, WebEnv
from .llm import LLM
from .schema import SkillCard
from .webarena.action_validation import axtree_elements, parse_hsge_action, validate_hsge_action
from .webarena.predicates import PredicateExtractor, predicates_from

_SYS = ("You GROUND a parameterized skill onto a concrete page: bind each "
        "selector/value slot to an element present in the page. Return JSON.")


def ground_and_execute(llm: LLM, skill: SkillCard, env: WebEnv,
                       predicate_extractor: PredicateExtractor | None = None) -> bool:
    """Try to run `skill` from the env's current page. Returns success bool.

    Nếu env có browser_factory, dùng browser thật để verify.
    Nếu không, dùng mock WebEnv.
    """
    setattr(skill, "_last_planning_effects_verified", False)
    browser_factory = getattr(env, 'browser_factory', None)
    if browser_factory:
        return _ground_and_execute_browser(
            llm, skill, env, browser_factory, predicate_extractor
        )

    # Fallback: mock WebEnv — dùng affordances để ground + execute trên mock
    page = env.reset()
    payload = {
        "slots": [{"name": s.name, "slot_type": s.slot_type} for s in skill.slots],
        "affordances": list(page.affordances),
    }
    g = llm.complete_json(_SYS, f"<payload>{json.dumps(payload)}</payload>")
    if not g.get("groundable", False):
        fallback = _deterministic_bindings(skill, affordances=list(page.affordances))
        if not fallback:
            _append_verify_failure(skill, "mock_not_groundable")
            return False
        bindings = fallback
    else:
        bindings = g.get("bindings", {})

    for tmpl in skill.action_template:
        action = tmpl
        for name, val in bindings.items():
            action = action.replace("{" + name + "}", repr(str(val)))
        if "{" in action:
            _append_verify_failure(skill, "mock_unbound_slot")
            return False
        try:
            parsed = parse_hsge_action(action)
        except ValueError as exc:
            _append_verify_failure(skill, f"mock_parse_failed:{exc}")
            return False
        if parsed.name in {"goto", "send_msg_to_user"}:
            _append_verify_failure(skill, f"mock_forbidden_action:{parsed.name}")
            return False
        env.step(action)
    return env.check(skill.success_predicate)


def _ground_and_execute_browser(llm: LLM, skill: SkillCard, env: WebEnv,
                                browser_factory, predicate_extractor=None) -> bool:
    """Verify skill bằng browser thật: mở start_url, thực thi skill actions, kiểm tra kết quả."""
    browser = None
    try:
        start_url = env.pages.get(env.start, PageState("", [], {})).url if hasattr(env, 'pages') else ""
        if not start_url:
            start_url = getattr(env, 'start', "")
        
        browser = browser_factory(start_url)
        obs = browser.reset()
        if not obs.get("url"):
            return False
        before_predicates = predicates_from(
            obs.get("url", ""), obs.get("axtree", ""), predicate_extractor
        )

        has_slots = bool(skill.slots) or ("{" in str(skill.action_template))
        if not has_slots:
            return False

        # Ground: LLM bind slots vào axtree của context
        axtree = obs.get("axtree", "")[:4000]
        payload = {
            "slots": [{"name": s.name, "slot_type": s.slot_type} for s in skill.slots],
            "page_url": obs.get("url", ""),
            "axtree_snippet": axtree,
            "affordances": _extract_affordances(axtree),
            "verification_target": {
                "role": getattr(env, "verification_target_role", ""),
                "name": getattr(env, "verification_target_name", ""),
                "fingerprint": getattr(env, "verification_target_fingerprint", ""),
            },
        }
        g = llm.complete_json(
            "You GROUND a parameterized skill onto a concrete page. "
            "Given the skill's slots and the current page's accessibility tree, "
            "bind each selector/value slot to an element present in the page. "
            "Return JSON with 'groundable' (bool) and 'bindings' (dict).",
            f"Skill: {skill.name}\nDescription: {skill.description}\n"
            f"Action template: {skill.action_template}\n"
            f"<payload>{json.dumps(payload)}</payload>"
        )
        preferred = _verification_target_bindings(skill, env, obs.get("axtree", ""))
        if not g.get("groundable", False):
            bindings = preferred or _deterministic_bindings(
                skill, axtree=obs.get("axtree", "")
            )
            if not bindings:
                _append_verify_failure(skill, "browser_not_groundable")
                return False
        else:
            bindings = g.get("bindings", {})
            # The held-out transition supplies semantic target evidence.  It is
            # more reliable than an unconstrained generic LLM binding.
            bindings.update(preferred)

        # Execute: render template với bindings và thực thi trên browser thật
        # Chỉ execute nếu template có chứa placeholder (có thể ground được)
        templates = skill.action_template
        if isinstance(templates, str):
            templates = [templates]
        has_placeholder = any("{" in t for t in templates)
        if not has_placeholder:
            _append_verify_failure(skill, "browser_no_placeholder")
            return False

        for tmpl in templates:
            action = tmpl
            for name, val in bindings.items():
                action = action.replace("{" + name + "}", repr(str(val)))
            if "{" in action:
                _append_verify_failure(skill, "browser_unbound_slot")
                return False
            validation = validate_hsge_action(action, obs.get("axtree", ""), allow_goto=False)
            if not validation.ok:
                fallback = _deterministic_bindings(skill, axtree=obs.get("axtree", ""))
                if fallback and fallback != bindings:
                    bindings.update(fallback)
                    action = tmpl
                    for name, val in bindings.items():
                        action = action.replace("{" + name + "}", repr(str(val)))
                    validation = validate_hsge_action(action, obs.get("axtree", ""), allow_goto=False)
                if not validation.ok:
                    _append_verify_failure(skill, f"browser_validation_failed:{validation.reason}")
                    return False
            obs = browser.act(action)
            if not obs.get("url"):
                _append_verify_failure(skill, "browser_action_returned_no_url")
                return False

        if skill.planning_effects:
            observed = predicates_from(
                obs.get("url", ""), obs.get("axtree", ""), predicate_extractor
            )
            observed_delta = observed - before_predicates
            missing = skill.planning_effects - observed_delta
            if missing:
                _append_verify_failure(
                    skill,
                    "browser_missing_planning_effects:" + ",".join(sorted(missing)),
                )
                return False
            setattr(skill, "_last_planning_effects_verified", True)
        return True
    except Exception as exc:
        _append_verify_failure(skill, f"browser_exception:{type(exc).__name__}")
        return False
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass


def _extract_affordances(axtree: str) -> list[str]:
    """Return visible numeric BIDs from an accessibility tree snippet."""
    import re

    return re.findall(r"^\s*\[(\d+)\]", axtree or "", flags=re.MULTILINE)


def _append_verify_failure(skill: SkillCard, reason: str) -> None:
    failures = getattr(skill, "_verify_failures", None)
    if failures is None:
        failures = []
        setattr(skill, "_verify_failures", failures)
    failures.append(reason)


def _deterministic_bindings(
    skill: SkillCard,
    *,
    axtree: str = "",
    affordances: list[str] | None = None,
) -> dict[str, str] | None:
    """Ground obvious canonical slots without asking the LLM.

    This is intentionally generic: it looks for affordance families such as
    inputs, links, menus, feedback indicators, and state-changing controls.
    Domain words may appear in labels, but the policy is expressed as UI roles
    and reusable action families.
    """
    if not skill.slots:
        return {}
    bindings: dict[str, str] = {}
    used: set[str] = set()
    for slot in skill.slots:
        if slot.slot_type == "value":
            bindings[slot.name] = _value_for_slot(skill, slot.name)
            continue
        if slot.slot_type != "selector":
            continue
        bid = _select_bid_for_slot(skill, slot.name, axtree=axtree, affordances=affordances, used=used)
        if not bid:
            return None
        bindings[slot.name] = bid
        used.add(bid)
    return bindings


def _verification_target_bindings(
    skill: SkillCard, env: WebEnv, axtree: str
) -> dict[str, str]:
    """Bind a selector to the semantic target retained by the context builder."""
    expected_role = str(getattr(env, "verification_target_role", "") or "").lower()
    expected_name = str(getattr(env, "verification_target_name", "") or "")
    expected_fingerprint = str(
        getattr(env, "verification_target_fingerprint", "") or ""
    )
    if not (expected_role or expected_name or expected_fingerprint):
        return {}

    def normalized(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))

    expected_text = normalized(expected_name)
    if not expected_text and "|" in expected_fingerprint:
        expected_text = normalized(expected_fingerprint.split("|", 1)[1])
    ranked: list[tuple[int, str]] = []
    for bid, (role, line) in axtree_elements(axtree).items():
        line_text = normalized(line)
        score = 0
        if expected_role and role == expected_role:
            score += 5
        if expected_text and expected_text in line_text:
            score += 10
        elif expected_text:
            tokens = set(expected_text.split())
            score += len(tokens & set(line_text.split()))
        if score:
            ranked.append((score, bid))
    if not ranked:
        return {}
    ranked.sort(reverse=True)

    selector_slots = [slot.name for slot in skill.slots if slot.slot_type == "selector"]
    if not selector_slots:
        return {}
    target_slot = next(
        (
            name for name in selector_slots
            if re.search(r"control|target|item|record|submit|button|link", name, re.I)
        ),
        selector_slots[-1],
    )
    return {target_slot: ranked[0][1]}


def _value_for_slot(skill: SkillCard, slot_name: str) -> str:
    text = f"{skill.name} {slot_name}".lower()
    if re.search(r"search|query|find", text):
        return "test"
    if re.search(r"email", text):
        return "test@example.com"
    if re.search(r"phone", text):
        return "5555555555"
    if re.search(r"zip|postal", text):
        return "10001"
    return "auto_value"


def _select_bid_for_slot(
    skill: SkillCard,
    slot_name: str,
    *,
    axtree: str = "",
    affordances: list[str] | None = None,
    used: set[str] | None = None,
) -> str:
    used = used or set()
    if axtree:
        elements = [
            (bid, role, line)
            for bid, (role, line) in axtree_elements(axtree).items()
            if bid not in used
        ]
        ranked = sorted(elements, key=lambda e: _selector_score(skill.name, slot_name, e[1], e[2]), reverse=True)
        for bid, role, line in ranked:
            if _selector_score(skill.name, slot_name, role, line) > 0:
                return bid
        return ""
    for bid in affordances or []:
        if bid not in used:
            return str(bid)
    return ""


def _selector_score(skill_name: str, slot_name: str, role: str, line: str) -> int:
    text = f"{skill_name} {slot_name} {line}".lower()
    role = (role or "").lower()
    score = 0
    if role in {"button", "link", "checkbox", "radio", "menuitem", "option", "tab", "combobox", "textbox", "searchbox"}:
        score += 1
    if re.search(r"search|query|find", f"{skill_name} {slot_name}", re.I):
        if role in {"textbox", "searchbox", "combobox"}:
            score += 8
        if re.search(r"search|query|find|go|submit", text):
            score += 3
    elif skill_name in {"open_visible_item", "open_visible_detail", "read_visible_detail"}:
        if role == "link":
            score += 7
        if role == "button":
            score += 3
        if re.search(r"detail|view|open|more|item|record|article|issue|image", text):
            score += 3
    elif skill_name in {"activate_state_change_control", "save_visible_item"}:
        if role in {"button", "link", "checkbox", "radio", "option"}:
            score += 6
        if re.search(r"add|save|apply|submit|continue|next|confirm|select|choose|checkout|compare|remove|delete", text):
            score += 4
    elif skill_name == "inspect_feedback_indicator":
        if role in {"link", "button", "tab"}:
            score += 5
        if re.search(r"feedback|review|rating|comment|discussion|star", text):
            score += 5
    elif skill_name == "inspect_menu_options":
        if role in {"menuitem", "button", "link", "tab"}:
            score += 5
        if re.search(r"menu|haspopup|expand|category|options", text):
            score += 4
    elif skill_name == "inspect_filter_sort":
        if role in {"button", "link", "combobox", "option"}:
            score += 5
        if re.search(r"filter|sort|facet|refine", text):
            score += 5
    elif skill_name in {"fill_visible_field", "submit_search_query"}:
        if role in {"textbox", "searchbox", "combobox"}:
            score += 7
    elif skill_name == "activate_named_control":
        if role in {"button", "link", "checkbox", "radio", "menuitem", "option", "tab"}:
            score += 4
    return score


def verify_skill(
    llm: LLM,
    skill: SkillCard,
    contexts: list[WebEnv],
    k: int = 2,
    predicate_extractor: PredicateExtractor | None = None,
) -> bool:
    """Admit iff the skill succeeds in >= k distinct contexts. Mutates skill.stats.

    If no verification contexts are available, reject the candidate until the
    run has collected enough successful contexts to audit it.
    """
    if k <= 0:
        skill.verified = True
        setattr(skill, "_planning_verify_successes", 0)
        return True

    if not contexts:
        print(f"  [verify] \"{skill.name}\": no contexts available → rejected")
        skill.verified = False
        return False

    successes = 0
    planning_successes = 0
    setattr(skill, "_verify_failures", [])
    tried_contexts: set[str] = set()
    for env in contexts:
        site = getattr(env, "site", "") or repr(env)
        start = getattr(env, "start", "")
        page_url = ""
        try:
            page_url = env.pages[start].url
        except Exception:
            page_url = str(start)
        context_key = str(
            getattr(env, "verification_context_id", "")
            or f"{site}:{page_url}"
        )
        if context_key in tried_contexts:
            continue
        tried_contexts.add(context_key)
        skill.stats.n_verify_attempts += 1
        try:
            ok = ground_and_execute(llm, skill, env, predicate_extractor)
        except Exception as exc:
            _append_verify_failure(skill, f"verify_exception:{type(exc).__name__}")
            ok = False
        if ok:
            successes += 1
            skill.stats.n_verify_success += 1
            if getattr(skill, "_last_planning_effects_verified", False):
                planning_successes += 1
        if successes >= k and (
            not skill.planning_effects or planning_successes >= k
        ):
            break

    required = k
    skill.verified = successes >= required
    setattr(skill, "_planning_verify_successes", planning_successes)
    print(f"  [verify] \"{skill.name}\": {successes}/{k} successes → "
          f"{'ADMITTED' if skill.verified else 'REJECTED'}")
    if not skill.verified:
        reasons = getattr(skill, "_verify_failures", [])
        if reasons:
            top = ", ".join(f"{r}×{reasons.count(r)}" for r in dict.fromkeys(reasons[:5]))
            print(f"  [verify] \"{skill.name}\" failure reasons: {top}")
    return skill.verified
