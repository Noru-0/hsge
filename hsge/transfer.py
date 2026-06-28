"""Cross-domain skill transfer — the headline contribution.

When exploration reaches a *new* site, instead of cold-starting we retrieve
candidate skills from the library, attempt to ground each onto the new site's
DOM, execute, and verify. Abstract structure transfers; grounding re-binds.

The reported quantity is the transfer success rate (fraction of retrieved skills
that ground+verify on the held-out site) and the set of skills that newly cover
the site. In the paper this becomes: exploration cost-to-coverage with vs
without a seeded library.

Phase 3 improvement: adds real browser-based transfer with LLM-based
adaptation when grounding fails on the target site.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from .env import WebEnv
from .library import SkillLibrary
from .llm import LLM
from .schema import SkillCard, ParamSlot
from .verification import ground_and_execute

logger = logging.getLogger(__name__)


@dataclass
class TransferResult:
    site: str
    attempted: int
    succeeded: int
    transferred_skill_ids: list[str]
    adapted_skill_ids: list[str] = field(default_factory=list)

    @property
    def transfer_rate(self) -> float:
        return self.succeeded / self.attempted if self.attempted else 0.0


def transfer_to_site(
    library: SkillLibrary,
    target_env: WebEnv,
    query: str,
    top_k: int = 5,
) -> TransferResult:
    """Transfer skills to a target environment via retrieval + grounding.

    Uses the mock WebEnv for grounding (deterministic page graphs).
    For real browser-based transfer with adaptation, use transfer_and_adapt().
    """
    candidates = library.retrieve(query, top_k=top_k)
    transferred = []
    for card in candidates:
        card.stats.n_verify_attempts += 1
        ok = ground_and_execute(library.llm, card, target_env)
        if ok:
            card.stats.n_verify_success += 1
            card.stats.sites_seen.add(target_env.site)
            transferred.append(card.skill_id)
    return TransferResult(
        site=target_env.site,
        attempted=len(candidates),
        succeeded=len(transferred),
        transferred_skill_ids=transferred,
    )


def transfer_and_adapt(
    library: SkillLibrary,
    llm: LLM,
    browser_factory,
    target_url: str,
    query: str,
    top_k: int = 5,
    max_steps: int = 10,
) -> TransferResult:
    """Transfer skills to a new site with actual browser execution and adaptation.

    Steps:
      1. Retrieve top-k skills from the library.
      2. For each skill, open a browser on the target URL and try to
         ground-and-execute.
      3. If grounding fails, ask the LLM to adapt the skill's action template
         to the target page's DOM.
      4. If adaptation succeeds, save the adapted variant and report it.

    Returns a TransferResult with counts of directly transferred and adapted skills.
    """
    candidates = library.retrieve(query, top_k=top_k)
    transferred: list[str] = []
    adapted_skills: list[str] = []

    for card in candidates:
        card.stats.n_verify_attempts += 1
        try:
            browser = browser_factory(target_url)
            obs = browser.reset()
            if not obs.get("url"):
                browser.close()
                continue

            # Try direct grounding first
            ok = _try_ground_and_execute_on_browser(llm, card, browser, max_steps)

            if ok:
                card.stats.n_verify_success += 1
                card.stats.sites_seen.add(target_url)
                transferred.append(card.skill_id)
                logger.info(f"  [transfer] {card.name} → DIRECT TRANSFER to {target_url}")
            else:
                # Adaptation: ask LLM to adjust the skill for this page
                adapted = _adapt_skill_to_page(llm, card, obs)
                if adapted is not None:
                    adapted_ok = _try_ground_and_execute_on_browser(
                        llm, adapted, browser, max_steps
                    )
                    if adapted_ok:
                        # Store adapted skill in library
                        adapted.stats.n_verify_success += 1
                        adapted.stats.sites_seen.add(target_url)
                        adapted_skills.append(adapted.skill_id)
                        # Optionally register adapted skill back into library
                        _register_adapted_skill(library, card, adapted, target_url)
                        logger.info(f"  [transfer] {card.name} → ADAPTED for {target_url}")
                    else:
                        logger.info(f"  [transfer] {card.name} → ADAPTATION FAILED on {target_url}")
                else:
                    logger.info(f"  [transfer] {card.name} → GROUNDING+ADAPTATION FAILED on {target_url}")

            browser.close()
        except Exception as e:
            logger.warning(f"  [transfer] Error transferring {card.name}: {e}")
            continue

    return TransferResult(
        site=target_url,
        attempted=len(candidates),
        succeeded=len(transferred),
        transferred_skill_ids=transferred,
        adapted_skill_ids=adapted_skills,
    )


def _try_ground_and_execute_on_browser(
    llm: LLM,
    card: SkillCard,
    browser,
    max_steps: int = 10,
) -> bool:
    """Try to ground and execute a skill on a real browser page.

    Uses the LLM to bind slots to the current page's affordances,
    then executes the action template step by step.
    """
    obs = browser.observation()
    axtree = obs.get("axtree", "")

    # Ask LLM to ground the skill (bind slots to page elements)
    payload = {
        "skill": card.name,
        "description": card.description,
        "slots": [{"name": s.name, "slot_type": s.slot_type, "description": s.description}
                  for s in card.slots],
        "action_template": card.action_template,
        "page_url": obs.get("url", ""),
        "page_axtree_snippet": axtree[:4000],
    }

    ground_sys = (
        "You GROUND a parameterized skill onto a concrete page. "
        "Bind each selector/value slot to an element present in the page. "
        "Return JSON with 'groundable' (bool) and 'bindings' (dict of slot_name -> value)."
    )
    g = llm.complete_json(ground_sys, f"<payload>{json.dumps(payload)}</payload>")

    if not g.get("groundable", False):
        return False

    bindings = g.get("bindings", {})

    # Render and execute the template
    templates = card.action_template
    if isinstance(templates, str):
        templates = [templates]

    for tmpl in templates:
        action = tmpl
        for name, val in bindings.items():
            action = action.replace("{" + name + "}", str(val))
        if "{" in action:
            return False  # unbound slot
        try:
            obs = browser.act(action)
        except Exception:
            return False

    # Check success via predicate (if available)
    if card.success_predicate:
        try:
            from .webarena.predicates import reached
            url = obs.get("url", "")
            axtree = obs.get("axtree", "")
            return reached(card.success_predicate, url, axtree)
        except ImportError:
            # predicates module not available (e.g. in test env)
            pass

    return True


_ADAPT_SYS = (
    "You ADAPT a skill's action template to work on a different page. "
    "The original skill worked on one site but needs different selectors/values "
    "for this new page. Return JSON with the adapted action_template."
)


def _adapt_skill_to_page(llm: LLM, card: SkillCard, obs: dict) -> SkillCard | None:
    """Ask LLM to adapt a skill to the current page's DOM.

    Returns a new SkillCard with adapted action_template, or None if adaptation
    is not possible.
    """
    prompt = {
        "skill_name": card.name,
        "description": card.description,
        "original_template": card.action_template,
        "slots": [{"name": s.name, "slot_type": s.slot_type} for s in card.slots],
        "new_page_url": obs.get("url", ""),
        "new_page_axtree_snippet": obs.get("axtree", "")[:4000],
        "instruction": (
            "Adapt the action_template to work on this new page. "
            "Replace selectors with ones that exist in the new page's accessibility tree. "
            "Keep the same logical steps but use correct element IDs for this page."
        ),
    }
    out = llm.complete_json(_ADAPT_SYS, json.dumps(prompt))
    if not out or "action_template" not in out:
        return None

    adapted_template = out["action_template"]
    if isinstance(adapted_template, str):
        adapted_template = [adapted_template]

    adapted = SkillCard(
        name=f"{card.name}_adapted",
        description=f"{card.description} (adapted)",
        slots=card.slots,
        action_template=adapted_template,
        precondition=card.precondition,
        success_predicate=card.success_predicate,
        cluster_id=card.cluster_id,
        member_ids=card.member_ids,
        planning_preconditions=set(card.planning_preconditions),
        planning_effects=set(card.planning_effects),
        terminal=card.terminal,
    )
    return adapted


def _register_adapted_skill(
    library: SkillLibrary,
    original: SkillCard,
    adapted: SkillCard,
    target_site: str,
) -> None:
    """Register an adapted skill variant back into the library."""
    from .schema import SkillStats
    adapted.stats = SkillStats(
        n_members=1,
        n_verify_attempts=1,
        n_verify_success=1,
        sites_seen={target_site},
    )
    adapted.verified = True
    # Use a synthetic cluster id derived from the original
    synthetic_cid = hash(adapted.name) % (2 ** 31)
    library.skills[synthetic_cid] = adapted
    if library._on_admit:
        library._on_admit(adapted)
