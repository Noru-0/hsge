"""Role-specific LLM configuration and WebArena runtime wiring."""

from types import SimpleNamespace

from hsge.llm import HashingEmbedder
from hsge.webarena.runtime import WebArenaExplorer
from run_webarena import AGENT_ROLES, _effective_llm_config


class _RoleLLM:
    def __init__(self, name):
        self.name = name

    def complete_json(self, system, prompt):
        return {}


def test_role_config_inherits_shared_values(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://env.invalid/v1")
    cli = SimpleNamespace(provider=None, model=None, base_url=None)
    cfg = {
        "provider": "deepseek",
        "model": "shared-model",
        "temperature": 0.2,
        "agents": {"solver": {"model": "solver-model", "temperature": 0.0}},
    }

    solver = _effective_llm_config(cli, cfg, "solver")
    explorer = _effective_llm_config(cli, cfg, "page_explorer")

    assert solver["model"] == "solver-model"
    assert solver["temperature"] == 0.0
    assert solver["base_url"] == "https://env.invalid/v1"
    assert explorer["model"] == "shared-model"
    assert explorer["temperature"] == 0.2


def test_global_cli_model_overrides_every_role():
    cli = SimpleNamespace(provider=None, model="cli-model", base_url=None)
    cfg = {"agents": {role: {"model": f"{role}-model"} for role in AGENT_ROLES}}

    assert all(
        _effective_llm_config(cli, cfg, role)["model"] == "cli-model"
        for role in AGENT_ROLES
    )


def test_runtime_routes_each_helper_to_its_model(tmp_path):
    fallback = _RoleLLM("fallback")
    llms = {role: _RoleLLM(role) for role in AGENT_ROLES}

    runtime = WebArenaExplorer(
        browser_factory=lambda url: None,
        llm=fallback,
        embedder=HashingEmbedder(),
        out_dir=str(tmp_path),
        allow_pattern=r"https://example\.com/.*",
        agent_llms=llms,
    )

    assert runtime.explorer.llm is llms["page_explorer"]
    assert runtime.solver.llm is llms["solver"]
    assert runtime.discovery.segmentation_llm is llms["trajectory_segmenter"]
    assert runtime.library.abstraction_llm is llms["skill_abstractor"]
    assert runtime.library.verification_llm is llms["skill_verifier"]
    assert runtime.operator_llm is llms["operator_inducer"]
