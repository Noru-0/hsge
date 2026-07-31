"""SiteSeeder turns a landing page into a {description, capabilities[]} profile.
Run: PYTHONPATH=. python -m pytest hsge/tests/test_site_seeder.py -q
"""
from hsge.webarena.agents import SEEDER_SYS, SiteSeeder


class _StubLLM:
    def __init__(self, out):
        self._out = out
        self.calls = []

    def complete_json(self, system, prompt, image_b64=None, image_detail="low"):
        self.calls.append((system, prompt))
        return self._out


def test_seeder_prompt_prefix_and_no_mock_tokens():
    # dry-run _DryLLM routes on this prefix; MockLLM routes on SEGMENT/ABSTRACT/GROUND
    assert SEEDER_SYS.startswith("SUMMARIZE")
    for tok in ("SEGMENT", "ABSTRACT", "GROUND"):
        assert tok not in SEEDER_SYS


def test_derive_parses_description_and_capabilities():
    llm = _StubLLM({
        "description": "A demo shopping site for electronics.",
        "capabilities": [
            {"name": "checkout", "goal": "Buy the cheapest in-stock mouse and confirm the order."},
            {"name": "search", "goal": "Find all laptops under $500 and open the first."},
        ],
    })
    seed = SiteSeeder(llm).derive({"url": "http://shop/", "axtree": "Home ..."})
    assert seed["description"].startswith("A demo shopping")
    assert [c["name"] for c in seed["capabilities"]] == ["checkout", "search"]
    # the page axtree and url reach the model
    assert "http://shop/" in llm.calls[0][1]


def test_derive_drops_auth_capabilities_and_entries_without_goal():
    llm = _StubLLM({
        "description": "d",
        "capabilities": [
            {"name": "login", "goal": "Log in to your account."},   # auth -> dropped
            {"name": "broken"},                                       # no goal -> dropped
            {"name": "cart", "goal": "Add three books to the cart."},
        ],
    })
    seed = SiteSeeder(llm).derive({"url": "http://x/", "axtree": ""})
    assert [c["name"] for c in seed["capabilities"]] == ["cart"]


def test_derive_returns_empty_on_garbage():
    seed = SiteSeeder(_StubLLM({"nonsense": 1})).derive({"url": "http://x/", "axtree": ""})
    assert seed == {"description": "", "capabilities": []}
