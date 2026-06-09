"""Tests for the core online clustering and the discovery pipeline.

Run:  python -m pytest tests/ -q     (or)     python tests/test_clustering.py
"""
import numpy as np

from hsge import (
    Discovery, HashingEmbedder, HierarchicalGraph, MockLLM, OnlineClusterer,
    SkillLibrary, Step, demo_sites,
)


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_similar_vectors_share_cluster():
    c = OnlineClusterer(sim_threshold=0.6)
    a = _unit([1, 0, 0])
    b = _unit([0.95, 0.05, 0])      # very close to a
    assert c.partial_fit(a, "a") == c.partial_fit(b, "b")
    assert len(c) == 1


def test_dissimilar_vectors_spawn_clusters():
    c = OnlineClusterer(sim_threshold=0.6)
    c.partial_fit(_unit([1, 0, 0]), "a")
    c.partial_fit(_unit([0, 1, 0]), "b")   # orthogonal -> new cluster
    assert len(c) == 2


def test_clusterer_grows_online():
    c = OnlineClusterer(sim_threshold=0.8)
    rng = np.random.default_rng(0)
    for i in range(20):
        c.partial_fit(_unit(rng.normal(size=8)), f"x{i}")
    # nonparametric: cluster count is data-driven, strictly between 1 and 20
    assert 1 < len(c) <= 20


def test_pipeline_admits_two_verified_skills():
    IDS = {
        "shop": dict(user="email", pwd="pwd", submit="signin", box="q", go="search_btn"),
        "forum": dict(user="username", pwd="password", submit="login_btn", box="searchbox", go="go_btn"),
        "gitlab": dict(user="login_field", pwd="pass_field", submit="submit", box="search_input", go="find"),
    }
    sites = demo_sites()
    train = ["shop", "forum", "gitlab"]

    def traj(s):
        e = IDS[s]; lu = f"/{s}/login"; hu = f"/{s}/home"
        return [Step(f"type [{e['user']}] a", lu), Step(f"type [{e['pwd']}] b", lu),
                Step(f"click [{e['submit']}]", lu), Step(f"type [{e['box']}] q", hu),
                Step(f"click [{e['go']}]", hu)]

    def vctx():
        out = []
        for s in train:
            out += [sites[s]["login"], sites[s]["home"]]
        return out

    lib = SkillLibrary(MockLLM(), HashingEmbedder(), vctx, maturity=3, verify_k=2)
    g = HierarchicalGraph()
    d = Discovery(lib, g)
    for s in train:
        d.on_trajectory(traj(s), s, "task", ["log in with credentials", "search the catalog"])

    assert len(lib.all_skills()) == 2
    assert all(c.verified for c in lib.all_skills())
    # composition edge login -> search exists
    assert any(g.skills[a].name.startswith("Log In") for a in g.skill_to_skill)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
