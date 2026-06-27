"""End-to-end HSGE demo on mock sites (no network/keys needed).

Pipeline exercised:
  1. Online skill discovery from streamed trajectories (3 training sites)
  2. Online clustering -> abstraction -> verification-gated admission
  3. Hierarchical graph construction (states + skills + composition edges)
  4. Cross-domain transfer to a held-out site (wiki)
  5. Curriculum generation by skill composition

Replace MockLLM / HashingEmbedder / WebEnv with real backends for the paper.
"""
from __future__ import annotations

from hsge import (
    Discovery, HierarchicalGraph, HashingEmbedder, MockLLM, SkillLibrary,
    Step, demo_sites, generate_curriculum, transfer_to_site,
)

SITES = demo_sites()
TRAIN = ["shop", "forum", "gitlab"]
HELDOUT = "wiki"

# Per-site element ids (mirror env._site) so we can synthesize realistic actions.
IDS = {
    "shop":   dict(user="email", pwd="pwd", submit="signin", box="q", go="search_btn"),
    "forum":  dict(user="username", pwd="password", submit="login_btn", box="searchbox", go="go_btn"),
    "gitlab": dict(user="login_field", pwd="pass_field", submit="submit", box="search_input", go="find"),
}


def make_trajectory(site: str) -> list[Step]:
    """A login flow (3 steps on /login) followed by a search flow (2 steps on /home).

    Step.url is the page where the action is taken, so URL boundaries cleanly
    separate the two sub-goals during segmentation.
    """
    e = IDS[site]
    login_url, home_url = f"/{site}/login", f"/{site}/home"
    return [
        Step(f"type [{e['user']}] alice", login_url, "entered username"),
        Step(f"type [{e['pwd']}] hunter2", login_url, "entered password"),
        Step(f"click [{e['submit']}]", login_url, "submitted login"),
        Step(f"type [{e['box']}] shoes", home_url, "typed query"),
        Step(f"click [{e['go']}]", home_url, "ran search"),
    ]


def verify_contexts():
    """Held-out execution contexts for the verification gate: login-start and
    home-start envs across all training sites."""
    ctx = []
    for s in TRAIN:
        ctx.append(SITES[s]["login"])
        ctx.append(SITES[s]["home"])
    return ctx


def main() -> None:
    llm = MockLLM()
    embedder = HashingEmbedder(dim=256)
    library = SkillLibrary(
        llm=llm, embedder=embedder, verify_contexts_fn=verify_contexts,
        sim_threshold=0.6, maturity=3, verify_k=2,
    )
    graph = HierarchicalGraph()
    discovery = Discovery(library, graph)

    print("=" * 70)
    print("1) ONLINE SKILL DISCOVERY  (streaming trajectories from 3 sites)")
    print("=" * 70)
    for site in TRAIN:
        steps = make_trajectory(site)
        admitted = discovery.on_trajectory(
            steps, site=site, task=f"log in and search on {site}",
            subgoal_hints=["log in with credentials", "search the catalog"],
        )
        n_clusters = len(library.clusterer)
        print(f"  fed {site:7s} -> clusters={n_clusters}  "
              f"admitted_this_step={[a for a in admitted]}")

    print(f"\n  Library now holds {len(library.all_skills())} verified skill(s).")

    print("\n" + "=" * 70)
    print("2) DISCOVERED SKILL CARDS")
    print("=" * 70)
    for card in library.all_skills():
        print(card.pretty())
        print()

    print("=" * 70)
    print("3) HIERARCHICAL GRAPH")
    print("=" * 70)
    print(f"  low-level states (URLs)      : {len(graph.states)}")
    print(f"  low-level trajectory edges   : {sum(len(v) for v in graph.trajectory_edges.values())}")
    print(f"  high-level skill nodes       : {len(graph.skills)}")
    print(f"  skill->skill composition edges:")
    for a, bs in graph.skill_to_skill.items():
        na = graph.skills[a].name
        for b in bs:
            print(f"      {na}  -->  {graph.skills[b].name}")

    print("\n" + "=" * 70)
    print(f"4) CROSS-DOMAIN TRANSFER  ->  held-out site '{HELDOUT}'")
    print("=" * 70)
    for ctx_key, query in [("login", "log in with credentials"),
                           ("home", "search the catalog")]:
        target = SITES[HELDOUT][ctx_key]
        res = transfer_to_site(library, target, query=query, top_k=5)
        print(f"  query={query!r:34s} attempted={res.attempted} "
              f"succeeded={res.succeeded} rate={res.transfer_rate:.2f} "
              f"transferred={res.transferred_skill_ids}")

    print("\n" + "=" * 70)
    print("5) CURRICULUM  (easy -> hard, by skill composition)")
    print("=" * 70)
    for task in generate_curriculum(graph, max_len=3):
        chain = " + ".join(graph.skills[s].name for s in task.skill_chain)
        print(f"  [difficulty {task.difficulty}] {chain}")
        print(f"      instruction: {task.instruction}")


if __name__ == "__main__":
    main()
