"""HSGE: Hierarchical Graph Exploration with Skill Abstraction.

A research scaffold extending flat-graph exploration  with online skill
discovery, verification-gated admission, a hierarchical (state + skill) graph,
cross-domain skill transfer, and curriculum generation.

Swap the mock backends (MockLLM, HashingEmbedder, WebEnv) for Claude/OpenAI,
sentence-transformers, and WebArena-via-BrowserGym respectively.
"""
from .schema import Step, SubTrajectory, SkillCard, ParamSlot, Task
from .llm import LLM, MockLLM, Embedder, HashingEmbedder
from .clustering import OnlineClusterer, Cluster
from .library import SkillLibrary
from .graph import HierarchicalGraph
from .discovery import Discovery
from .transfer import transfer_to_site, TransferResult
from .curriculum import generate_curriculum
from .env import WebEnv, PageState, demo_sites

__all__ = [
    "Step", "SubTrajectory", "SkillCard", "ParamSlot", "Task",
    "LLM", "MockLLM", "Embedder", "HashingEmbedder",
    "OnlineClusterer", "Cluster", "SkillLibrary", "HierarchicalGraph",
    "Discovery", "transfer_to_site", "TransferResult", "generate_curriculum",
    "WebEnv", "PageState", "demo_sites",
]
