"""Environment interface + a scripted mock.

The real backend is WebArena via BrowserGym (what flat-graph exploration uses). The mock here
exposes the same tiny surface so verification/transfer can actually *execute*
skills and get a success signal without standing up Docker sites.

Success model: a skill succeeds if executing it lands the agent on one of the
env's designated `goal_pages`. This is page-reaching, predicate-agnostic, and
deterministic -- good enough to exercise the full pipeline.

Real adapter sketch:

    import gymnasium, browsergym.webarena   # noqa
    class WebArenaEnv(WebEnv):
        def __init__(self, task): self.env = gymnasium.make("browsergym/" + task)
        ...
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class PageState:
    url: str
    affordances: list[str]                       # element ids exposed by the page
    goto: dict[str, str] = field(default_factory=dict)   # affordance -> next page key


class WebEnv:
    def __init__(self, site: str, pages: dict[str, PageState], start: str,
                 goal_pages: set[str]):
        self.site = site
        self.pages = pages
        self.start = start
        self.goal_pages = goal_pages            # set of page KEYS that count as success
        self.cur = start

    def reset(self) -> PageState:
        self.cur = self.start
        return self.pages[self.cur]

    def state(self) -> PageState:
        return self.pages[self.cur]

    def step(self, action: str) -> PageState:
        """Execute 'click [signin]' / 'type [user] alice'. Only clicks navigate."""
        page = self.pages[self.cur]
        verb = action.split(" ", 1)[0].lower()
        target = None
        canonical = re.match(r"\s*([a-z_]+)\((.*)\)\s*$", action)
        if canonical:
            verb = canonical.group(1).lower()
            first = canonical.group(2).split(",", 1)[0].strip()
            target = first.strip("'\"")
        else:
            m = re.search(r"\[([^\]]+)\]", action)
            target = m.group(1) if m else None
        if verb == "click" and target and target in page.affordances and target in page.goto:
            self.cur = page.goto[target]
        return self.pages[self.cur]

    def check(self, predicate: str = "") -> bool:
        """Success iff we reached a goal page (predicate kept for interface parity)."""
        return self.cur in self.goal_pages


def _site(site: str) -> dict[str, WebEnv]:
    """Build the page graph for one site and return login-start and home-start envs.

    login --(submit)--> home --(search)--> results
    Element ids differ per site so transfer is non-trivial.
    """
    ids = {
        "shop":   dict(user="email", pwd="pwd", submit="signin",
                       box="q", go="search_btn"),
        "forum":  dict(user="username", pwd="password", submit="login_btn",
                       box="searchbox", go="go_btn"),
        "gitlab": dict(user="login_field", pwd="pass_field", submit="submit",
                       box="search_input", go="find"),
        "wiki":   dict(user="u_name", pwd="u_pass", submit="log_in",
                       box="lookup", go="search"),
    }[site]

    pages = {
        "login": PageState(f"/{site}/login",
                           affordances=[ids["user"], ids["pwd"], ids["submit"]],
                           goto={ids["submit"]: "home"}),
        "home": PageState(f"/{site}/home",
                          affordances=[ids["box"], ids["go"], "logout"],
                          goto={ids["go"]: "results", "logout": "login"}),
        "results": PageState(f"/{site}/results", affordances=["item", "next"], goto={}),
    }
    login_env = WebEnv(site, pages, start="login", goal_pages={"home"})
    home_env = WebEnv(site, pages, start="home", goal_pages={"results"})
    return {"login": login_env, "home": home_env}


def demo_sites() -> dict[str, dict[str, WebEnv]]:
    """shop/forum/gitlab are training sites; wiki is the held-out transfer site."""
    return {s: _site(s) for s in ("shop", "forum", "gitlab", "wiki")}
