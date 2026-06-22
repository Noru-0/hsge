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

from .env import PageState, WebEnv
from .llm import LLM
from .schema import SkillCard
from .webarena.action_validation import parse_hsge_action, validate_hsge_action

_SYS = ("You GROUND a parameterized skill onto a concrete page: bind each "
        "selector/value slot to an element present in the page. Return JSON.")


def ground_and_execute(llm: LLM, skill: SkillCard, env: WebEnv) -> bool:
    """Try to run `skill` from the env's current page. Returns success bool.

    Nếu env có browser_factory, dùng browser thật để verify.
    Nếu không, dùng mock WebEnv.
    """
    browser_factory = getattr(env, 'browser_factory', None)
    if browser_factory:
        return _ground_and_execute_browser(llm, skill, env, browser_factory)

    # Fallback: mock WebEnv — dùng affordances để ground + execute trên mock
    page = env.reset()
    payload = {
        "slots": [{"name": s.name, "slot_type": s.slot_type} for s in skill.slots],
        "affordances": list(page.affordances),
    }
    g = llm.complete_json(_SYS, f"<payload>{json.dumps(payload)}</payload>")
    if not g.get("groundable", False):
        return False
    bindings = g.get("bindings", {})

    for tmpl in skill.action_template:
        action = tmpl
        for name, val in bindings.items():
            action = action.replace("{" + name + "}", repr(str(val)))
        if "{" in action:
            return False
        try:
            parsed = parse_hsge_action(action)
        except ValueError:
            return False
        if parsed.name in {"goto", "send_msg_to_user"}:
            return False
        env.step(action)
    return env.check(skill.success_predicate)


def _ground_and_execute_browser(llm: LLM, skill: SkillCard, env: WebEnv, browser_factory) -> bool:
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
        if not g.get("groundable", False):
            return False
        bindings = g.get("bindings", {})

        # Execute: render template với bindings và thực thi trên browser thật
        # Chỉ execute nếu template có chứa placeholder (có thể ground được)
        templates = skill.action_template
        if isinstance(templates, str):
            templates = [templates]
        has_placeholder = any("{" in t for t in templates)
        if not has_placeholder:
            return False

        for tmpl in templates:
            action = tmpl
            for name, val in bindings.items():
                action = action.replace("{" + name + "}", repr(str(val)))
            if "{" in action:
                return False
            validation = validate_hsge_action(action, obs.get("axtree", ""), allow_goto=False)
            if not validation.ok:
                return False
            obs = browser.act(action)
            if not obs.get("url"):
                return False

        return True
    except Exception:
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


def verify_skill(
    llm: LLM,
    skill: SkillCard,
    contexts: list[WebEnv],
    k: int = 2,
) -> bool:
    """Admit iff the skill succeeds in >= k distinct contexts. Mutates skill.stats.

    If no verification contexts are available, reject the candidate until the
    run has collected enough successful contexts to audit it.
    """
    if k <= 0:
        skill.verified = True
        return True

    if not contexts:
        print(f"  [verify] \"{skill.name}\": no contexts available → rejected")
        skill.verified = False
        return False

    successes = 0
    tried_contexts: set[str] = set()
    for env in contexts:
        site = getattr(env, "site", "") or repr(env)
        start = getattr(env, "start", "")
        page_url = ""
        try:
            page_url = env.pages[start].url
        except Exception:
            page_url = str(start)
        context_key = f"{site}:{page_url}"
        if context_key in tried_contexts:
            continue
        tried_contexts.add(context_key)
        skill.stats.n_verify_attempts += 1
        try:
            ok = ground_and_execute(llm, skill, env)
        except Exception:
            ok = False
        if ok:
            successes += 1
            skill.stats.n_verify_success += 1
        if successes >= k:
            break

    required = k
    skill.verified = successes >= required
    print(f"  [verify] \"{skill.name}\": {successes}/{k} successes → "
          f"{'ADMITTED' if skill.verified else 'REJECTED'}")
    return skill.verified
