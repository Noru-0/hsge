"""Cross-domain skill transfer — the headline contribution.

When exploration reaches a *new* site, instead of cold-starting we retrieve
candidate skills from the library, attempt to ground each onto the new site's
DOM, execute, and verify. Abstract structure transfers; grounding re-binds.

The reported quantity is the transfer success rate (fraction of retrieved skills
that ground+verify on the held-out site) and the set of skills that newly cover
the site. In the paper this becomes: exploration cost-to-coverage with vs
without a seeded library.
"""
from __future__ import annotations

from dataclasses import dataclass

from .env import WebEnv
from .library import SkillLibrary
from .verification import ground_and_execute


@dataclass
class TransferResult:
    site: str
    attempted: int
    succeeded: int
    transferred_skill_ids: list[str]

    @property
    def transfer_rate(self) -> float:
        return self.succeeded / self.attempted if self.attempted else 0.0


def transfer_to_site(
    library: SkillLibrary,
    target_env: WebEnv,
    query: str,
    top_k: int = 5,
) -> TransferResult:
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
