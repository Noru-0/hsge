"""Core data structures for HSGE.

Everything that flows through the pipeline is one of these. Keeping the schema
in one place makes the LLM-induced artifacts (skill cards) inspectable, which is
what you want for the qualitative figures and the verification audit trail.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .predicate_ontology import FactPattern, TypedActionModel


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class Step:
    """One primitive (action, observation) pair in a trajectory."""
    action: str                 # e.g. "click [submit]", "type [username] 'alice'"
    url: str                    # URL after the action
    obs_summary: str = ""       # short NL summary of the resulting observation
    dom_signature: str = ""     # cheap structural fingerprint of the page
    misc: dict | None = None    # optional metadata (e.g. {"skill": "add_to_cart"})

    def action_kind(self) -> str:
        """Verb only, used to build a site-agnostic action signature."""
        action = (self.action or "").strip().lower()
        if "(" in action:
            return action.split("(", 1)[0].strip()
        return action.split(" ", 1)[0]


@dataclass
class SubTrajectory:
    """A contiguous, semantically coherent slice of a full trajectory.

    This is the unit that gets clustered and abstracted into a skill.
    """
    steps: list[Step]
    subgoal: str                       # NL description, e.g. "log in with credentials"
    source_site: str                   # domain it was collected from
    source_task: str = ""              # the task that produced the parent trajectory
    success: bool = True               # only successes are eligible for discovery
    sub_id: str = field(default_factory=lambda: _new_id("st"))
    planning_preconditions: set[str] = field(default_factory=set)
    planning_effects: set[str] = field(default_factory=set)
    predicate_schema_version: str = ""
    source_kind: str = "local"
    source_episode_id: int | None = None
    source_task_id: str = ""
    typed_action_model: TypedActionModel | None = None

    def action_signature(self) -> str:
        """Site-agnostic signature: the sequence of action verbs.

        'login on site A' and 'login on site B' should map to the same signature
        even though selectors/values differ. This is what makes clustering and
        transfer possible.
        """
        return " > ".join(s.action_kind() for s in self.steps)

    def text_for_embedding(self) -> str:
        parts = [f"GOAL: {self.subgoal}", f"ACTIONS: {self.action_signature()}"]
        if self.planning_effects:
            effects_sorted = ", ".join(sorted(self.planning_effects))
            parts.append(f"EFFECTS: {effects_sorted}")
        return " | ".join(parts)


@dataclass
class ParamSlot:
    """A site-specific value that was 'lifted' out of concrete trajectories."""
    name: str                  # e.g. "username", "submit_button_selector"
    slot_type: str             # "value" | "selector" | "url"
    description: str = ""
    example: str = ""


@dataclass
class SkillStats:
    n_members: int = 0          # sub-trajectories in the cluster
    n_verify_attempts: int = 0
    n_verify_success: int = 0
    sites_seen: set[str] = field(default_factory=set)
    bootstrap_verified: bool = False

    @property
    def success_rate(self) -> float:
        if self.n_verify_attempts == 0:
            return 0.0
        return self.n_verify_success / self.n_verify_attempts


@dataclass
class SkillCard:
    """An option <I, pi, beta> in human/LLM-readable form.

    - precondition  ~ I (initiation set predicate, as NL the grounder can check)
    - action_template + slots ~ pi (parameterized policy)
    - success_predicate ~ beta (termination/success test)

    Phase 4 additions:
    - execution_plan: structured list of ExecutionStep for robust execution
    - alternative_templates: fallback templates for different page layouts
    """
    name: str
    description: str
    slots: list[ParamSlot]
    action_template: list[str]     # templated actions, e.g. "type {username_selector} {username}"
    precondition: str
    success_predicate: str
    cluster_id: str
    member_ids: list[str] = field(default_factory=list)
    stats: SkillStats = field(default_factory=SkillStats)
    verified: bool = False
    skill_id: str = field(default_factory=lambda: _new_id("skill"))
    planning_preconditions: set[str] = field(default_factory=set)
    planning_effects: set[str] = field(default_factory=set)
    terminal: bool = False
    planning_ready: bool = False
    planning_rejection_reason: str = ""
    typed_planning_ready: bool = False
    typed_planning_rejection_reason: str = ""
    predicate_schema_version: str = ""
    # Phase 4: structured execution plan
    execution_plan: list[dict] = field(default_factory=list)
    alternative_templates: list[list[str]] = field(default_factory=list)
    typed_action_model: TypedActionModel | None = None

    @property
    def has_verified_effects(self) -> bool:
        return bool(
            self.planning_effects
            or (
                self.typed_action_model
                and (
                    self.typed_action_model.add_effects
                    or self.typed_action_model.delete_effects
                )
            )
        )

    def effect_summary(self) -> dict[str, Any]:
        model = self.typed_action_model
        return {
            "legacy_add": sorted(self.planning_effects),
            "typed_add": [
                pattern.to_dict() for pattern in sorted(model.add_effects)
            ] if model else [],
            "typed_delete": [
                pattern.to_dict() for pattern in sorted(model.delete_effects)
            ] if model else [],
        }

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stats"]["sites_seen"] = sorted(self.stats.sites_seen)
        d["planning_preconditions"] = sorted(self.planning_preconditions)
        d["planning_effects"] = sorted(self.planning_effects)
        d["typed_action_model"] = (
            self.typed_action_model.to_dict() if self.typed_action_model else None
        )
        d["has_verified_effects"] = self.has_verified_effects
        d["effect_summary"] = self.effect_summary()
        return d

    def pretty(self) -> str:
        slots = ", ".join(f"{s.name}:{s.slot_type}" for s in self.slots) or "(none)"
        lines = [
            f"[{self.skill_id}] {self.name}  (verified={self.verified}, "
            f"success={self.stats.success_rate:.2f}, sites={len(self.stats.sites_seen)})",
            f"  desc       : {self.description}",
            f"  precond    : {self.precondition}",
            f"  slots      : {slots}",
            f"  template   :",
        ]
        lines += [f"      - {a}" for a in self.action_template]
        lines.append(f"  success_if : {self.success_predicate}")
        if self.execution_plan:
            lines.append(f"  execution_plan ({len(self.execution_plan)} steps):")
            for i, step in enumerate(self.execution_plan):
                lines.append(f"      {i}. [{step.get('action_type','?')}] "
                             f"{step.get('target_desc','')}")
        if self.alternative_templates:
            lines.append(f"  alternatives: {len(self.alternative_templates)} variant(s)")
        return "\n".join(lines)


@dataclass
class Task:
    """A proposed task, possibly a composition of skills (for the curriculum)."""
    instruction: str
    skill_chain: list[str]          # skill_ids composed, in order
    difficulty: int                 # = len(skill_chain) by default
    site: str = ""
    task_id: str = field(default_factory=lambda: _new_id("task"))
    goal_predicate: str = ""
    terminal: bool = False
    task_origin: str = "curriculum"
    predicate_schema_version: str = ""
    typed_goal_pattern: FactPattern | None = None
    planner_source: str = "legacy"
