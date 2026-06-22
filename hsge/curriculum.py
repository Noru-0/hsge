"""Curriculum generation by skill composition on the hierarchical graph.

Difficulty := length of the composed skill chain. We enumerate chains by walking
skill->skill successor edges, then emit Tasks ordered easy->hard. These feed both
task proposal (more grounded exploration targets) and curriculum-ordered
fine-tuning of the agent.
"""
from __future__ import annotations

from .graph import HierarchicalGraph
from .schema import SkillCard, Task


def _display_name(name: str) -> str:
    name = (name or "skill").strip()
    if "_" in name and name.lower() == name:
        return name.replace("_", " ")
    return name


def _chains(graph: HierarchicalGraph, max_len: int) -> list[list[str]]:
    chains: list[list[str]] = []
    # length-1 chains: every skill on its own
    for sid in graph.skills:
        chains.append([sid])
    # extend via DFS over composition successors
    frontier = [[sid] for sid in graph.skills]
    while frontier:
        path = frontier.pop()
        if len(path) >= max_len:
            continue
        for nxt in graph.successors(path[-1]):
            if nxt in path:
                continue
            new = path + [nxt]
            chains.append(new)
            frontier.append(new)
    return chains


def _instruction(graph: HierarchicalGraph, chain: list[str]) -> str:
    names = [_display_name(graph.skills[s].name) for s in chain]
    if len(names) == 1:
        return f"Complete the '{names[0]}' task."
    return " Then ".join([f"Do '{n}'." for n in names]).strip()


def generate_curriculum(
    graph: HierarchicalGraph,
    max_len: int = 3,
    site: str = "",
) -> list[Task]:
    chains = _chains(graph, max_len)
    # dedupe
    seen, uniq = set(), []
    for c in chains:
        key = tuple(c)
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    tasks = [
        Task(instruction=_instruction(graph, c), skill_chain=c,
             difficulty=len(c), site=site)
        for c in uniq
    ]
    tasks.sort(key=lambda t: t.difficulty)        # easy -> hard
    return tasks


# ---- Alias for backward compatibility ---------------------------------------
def generate_curriculum_from_operators(opgraph, max_len=3, site=""):
    """Alias giữ tương thích với runtime cũ."""
    return []
