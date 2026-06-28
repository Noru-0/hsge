"""Run a flat baseline and HSGE on IDENTICAL input, diff the artifacts.

    python compare.py
"""
from __future__ import annotations

from hsge import (
    Discovery, HierarchicalGraph, HashingEmbedder, MockLLM, SkillLibrary,
    Step, demo_sites, generate_curriculum, transfer_to_site,
)
from hsge.flat_baseline import FlatExploreBaseline

SITES = demo_sites()
TRAIN = ["shop", "forum", "gitlab"]
HELDOUT = "wiki"
IDS = {
    "shop":   dict(user="email", pwd="pwd", submit="signin", box="q", go="search_btn"),
    "forum":  dict(user="username", pwd="password", submit="login_btn", box="searchbox", go="go_btn"),
    "gitlab": dict(user="login_field", pwd="pass_field", submit="submit", box="search_input", go="find"),
}
SUBGOALS = ["log in with credentials", "search the catalog"]


def make_trajectory(site: str) -> list[Step]:
    e = IDS[site]; lu, hu = f"/{site}/login", f"/{site}/home"
    return [
        Step(f"type [{e['user']}] alice", lu, "entered username"),
        Step(f"type [{e['pwd']}] hunter2", lu, "entered password"),
        Step(f"click [{e['submit']}]", lu, "submitted login"),
        Step(f"type [{e['box']}] shoes", hu, "typed query"),
        Step(f"click [{e['go']}]", hu, "ran search"),
    ]


def verify_contexts():
    ctx = []
    for s in TRAIN:
        ctx += [SITES[s]["login"], SITES[s]["home"]]
    return ctx


def run_flat_baseline():
    gb = FlatExploreBaseline()
    for site in TRAIN:
        gb.collect(make_trajectory(site), site, f"log in and search on {site}")
    new_site = gb.cover_new_site(SITES[HELDOUT]["login"], SUBGOALS)
    return gb, new_site


def run_hsge():
    lib = SkillLibrary(MockLLM(), HashingEmbedder(), verify_contexts,
                       sim_threshold=0.6, maturity=3, verify_k=2)
    graph = HierarchicalGraph()
    disc = Discovery(lib, graph)
    for site in TRAIN:
        disc.on_trajectory(make_trajectory(site), site,
                           f"log in and search on {site}", subgoal_hints=SUBGOALS)
    # cross-domain transfer to held-out site
    transfers, reused = [], 0
    for key, q in [("login", SUBGOALS[0]), ("home", SUBGOALS[1])]:
        r = transfer_to_site(lib, SITES[HELDOUT][key], query=q, top_k=5)
        transfers.append(r)
        reused += r.succeeded
    curric = generate_curriculum(graph)
    return lib, graph, transfers, reused, curric


def row(label, a, b):
    print(f"  {label:<34}| {str(a):<26}| {b}")


def main():
    gb, gb_new = run_flat_baseline()
    lib, graph, transfers, reused, curric = run_hsge()

    n_traj = len(gb.dataset)
    n_states = len(gb.graph.states)
    n_edges = gb.graph.n_edges
    n_skills = len(lib.all_skills())
    n_comp = sum(len(v) for v in graph.skill_to_skill.values())
    hard_tasks = [t for t in curric if t.difficulty >= 2]

    print("INPUT (identical for both):")
    print(f"  3 training sites x 1 trajectory (login+search, 5 steps each) = {n_traj} trajectories")
    print(f"  then arrival at 1 held-out site: '{HELDOUT}'\n")

    print("=" * 92)
    print(f"  {'ARTIFACT':<34}| {'Flat baseline':<26}| HSGE (hierarchical)")
    print("=" * 92)
    row("low-level URL nodes", n_states, len(graph.states))
    row("low-level trajectory edges", n_edges, sum(len(v) for v in graph.trajectory_edges.values()))
    row("raw trajectories stored", n_traj, f"{n_traj} (same, retained)")
    row("abstracted reusable skills", 0, n_skills)
    row("verification gate", "none", f"yes (>=2 ctx); rates {[f'{c.stats.success_rate:.2f}' for c in lib.all_skills()]}")
    row("high-level skill nodes", 0, n_skills)
    row("skill->skill composition edges", 0, n_comp)
    row("curriculum: single-skill tasks", "per-page only", len([t for t in curric if t.difficulty == 1]))
    row("curriculum: composed (hard) tasks", 0, len(hard_tasks))
    print("=" * 92)

    print("\nHANDLING THE NEW SITE 'wiki' (never seen during discovery):")
    print("-" * 92)
    print(f"  Flat baseline : {gb_new['transfer']}; "
          f"must run {gb_new['new_exploration_episodes']} fresh exploration episodes; "
          f"reused units = {gb_new['reused_units']}")
    tlist = []
    for r in transfers:
        tlist.append(f"{r.succeeded}/{r.attempted}")
    print(f"  HSGE : transfers existing skills; "
          f"new exploration episodes = 0; "
          f"skills re-grounded+verified on wiki = {reused} "
          f"(per-subgoal {tlist})")
    print("-" * 92)

    print("\nWHAT HSGE ADDS ON TOP OF THE SAME FLAT GRAPH:")
    for c in lib.all_skills():
        sites = ", ".join(sorted(c.stats.sites_seen))
        print(f"  - skill '{c.name}': {len(c.slots)} param slots, "
              f"verified on [{sites}]")
    print(f"  - composition: " + "  ".join(
        f"({graph.skills[a].name} -> {graph.skills[b].name})"
        for a, bs in graph.skill_to_skill.items() for b in bs))
    print(f"  - hardest curriculum task: '{hard_tasks[0].instruction.strip()}'"
          if hard_tasks else "  - (no composed tasks)")

    print("\nNOTE: node/edge counts are identical because HSGE inherits the")
    print("the flat exploration graph and layers skills/hierarchy/transfer/curriculum on top.")
    print("The 'new exploration episodes' figure is illustrative of the mock; on")
    print("WebArena it must be measured with full LLM/exploration cost accounting.")


if __name__ == "__main__":
    main()
