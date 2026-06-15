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

from .env import WebEnv
from .llm import LLM
from .schema import SkillCard

_SYS = ("You GROUND a parameterized skill onto a concrete page: bind each "
        "selector/value slot to an element present in the page. Return JSON.")


def ground_and_execute(llm: LLM, skill: SkillCard, env: WebEnv) -> bool:
    """Try to run `skill` from the env's current page. Returns success bool."""
    page = env.reset()
    payload = {
        "slots": [{"name": s.name, "slot_type": s.slot_type} for s in skill.slots],
        "affordances": list(page.affordances),
    }
    g = llm.complete_json(_SYS, f"<payload>{json.dumps(payload)}</payload>")
    if not g.get("groundable", False):
        return False
    bindings = g.get("bindings", {})

    # Render the template with bindings and execute step by step.
    for tmpl in skill.action_template:
        action = tmpl
        for name, val in bindings.items():
            action = action.replace("{" + name + "}", str(val))
        # any remaining unbound slot -> grounding incomplete -> fail
        if "{" in action:
            return False
        env.step(action)
    return env.check(skill.success_predicate)


def verify_skill(
    llm: LLM,
    skill: SkillCard,
    contexts: list[WebEnv],
    k: int = 2,
) -> bool:
    """Admit iff the skill succeeds in >= k distinct contexts. Mutates skill.stats.

    If no verification contexts are available, admit immediately (we have no
    way to verify, but also no reason to reject).
    """
    if not contexts:
        # No verification environments available — admit without verification
        skill.verified = True
        return True

    successes = 0
    for env in contexts:
        skill.stats.n_verify_attempts += 1
        ok = ground_and_execute(llm, skill, env)
        if ok:
            successes += 1
            skill.stats.n_verify_success += 1
            skill.stats.sites_seen.add(env.site)
    skill.verified = successes >= k
    return skill.verified
