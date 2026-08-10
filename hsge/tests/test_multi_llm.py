"""Role-specific LLM configuration and WebArena runtime wiring."""

from types import SimpleNamespace

from hsge.llm import HashingEmbedder
from hsge.webarena.runtime import WebArenaExplorer
from run_webarena import AGENT_ROLES, _effective_llm_config, _resolve_agent_vision


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


def test_reasoning_effort_is_role_scoped_and_off_by_default():
    """GPT-5.x-only knob: a role that doesn't set it must not send it at all,
    since a non-reasoning model (gpt-4o, deepseek) 400s on the param."""
    cli = SimpleNamespace(provider=None, model=None, base_url=None)
    cfg = {"agents": {"solver": {"reasoning_effort": "none"},
                      "site_seeder": {"reasoning_effort": "low"}}}

    assert _effective_llm_config(cli, cfg, "solver")["reasoning_effort"] == "none"
    assert _effective_llm_config(cli, cfg, "site_seeder")["reasoning_effort"] == "low"
    assert _effective_llm_config(cli, cfg, "episode_judge")["reasoning_effort"] is None


def test_reasoning_effort_inherits_from_shared_block():
    cli = SimpleNamespace(provider=None, model=None, base_url=None)
    cfg = {"reasoning_effort": "medium",
           "agents": {"solver": {"reasoning_effort": "none"}}}

    assert _effective_llm_config(cli, cfg, "solver")["reasoning_effort"] == "none"
    assert _effective_llm_config(cli, cfg, "page_explorer")["reasoning_effort"] == "medium"


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


def test_runtime_wires_max_tasks_into_explorer(tmp_path):
    runtime = WebArenaExplorer(
        browser_factory=lambda url: None,
        llm=_RoleLLM("fallback"),
        embedder=HashingEmbedder(),
        out_dir=str(tmp_path),
        allow_pattern=r"https://example\.com/.*",
        max_tasks=6,
    )

    assert runtime.explorer.max_tasks == 6


def test_agent_vision_config_inherits_shared_values():
    cfg = {
        "vision": False, "som": True, "image_detail": "low",
        "agents": {
            "page_explorer": {"vision": True, "image_detail": "high"},
            "solver": {"vision": True, "som": False},
        },
    }

    vision = _resolve_agent_vision(cfg)

    assert vision["page_explorer"] == {"vision": True, "som": True, "image_detail": "high"}
    assert vision["solver"] == {"vision": True, "som": False, "image_detail": "low"}
    # a role with no override at all falls all the way back to the built-in defaults
    assert vision["trajectory_segmenter"] == {"vision": False, "som": True, "image_detail": "low"}


def test_runtime_wires_vision_into_explorer_and_solver(tmp_path):
    llms = {role: _RoleLLM(role) for role in AGENT_ROLES}
    agent_vision = {
        "page_explorer": {"vision": True, "som": True, "image_detail": "high"},
        "solver": {"vision": True, "som": False, "image_detail": "low"},
        **{role: {"vision": False, "som": True, "image_detail": "low"}
           for role in AGENT_ROLES if role not in ("page_explorer", "solver")},
    }

    runtime = WebArenaExplorer(
        browser_factory=lambda url: None,
        llm=_RoleLLM("fallback"),
        embedder=HashingEmbedder(),
        out_dir=str(tmp_path),
        allow_pattern=r"https://example\.com/.*",
        agent_llms=llms,
        agent_vision=agent_vision,
    )

    assert runtime.explorer.vision is True
    assert runtime.explorer.som is True
    assert runtime.explorer.image_detail == "high"
    assert runtime.solver.vision is True
    assert runtime.solver.som is False


def test_site_seeder_role_is_wired(tmp_path):
    assert "site_seeder" in AGENT_ROLES
    llms = {role: _RoleLLM(role) for role in AGENT_ROLES}
    runtime = WebArenaExplorer(
        browser_factory=lambda url: None,
        llm=_RoleLLM("fallback"),
        embedder=HashingEmbedder(),
        out_dir=str(tmp_path),
        allow_pattern=r"https://example\.com/.*",
        agent_llms=llms,
        use_site_seed=True,
    )
    assert runtime.seeder.llm is llms["site_seeder"]


def test_runtime_defaults_vision_off_when_not_configured(tmp_path):
    llms = {role: _RoleLLM(role) for role in AGENT_ROLES}

    runtime = WebArenaExplorer(
        browser_factory=lambda url: None,
        llm=_RoleLLM("fallback"),
        embedder=HashingEmbedder(),
        out_dir=str(tmp_path),
        allow_pattern=r"https://example\.com/.*",
        agent_llms=llms,
    )

    assert runtime.explorer.vision is False
    assert runtime.solver.vision is False
