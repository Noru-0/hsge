import argparse
import json
import re
from typing import Any

import tiktoken
from beartype import beartype

from agent.prompts import *
from browser_env import Trajectory
from browser_env.actions import (
    Action,
    ActionParsingError,
    ActionTypes,
    create_id_based_action,
    create_none_action,
    create_playwright_action,
)
from browser_env.utils import Observation, StateInfo
from llms import (
    call_llm,
    generate_from_huggingface_completion,
    generate_from_openai_chat_completion,
    generate_from_openai_completion,
    lm_config,
)
from llms.tokenizers import Tokenizer

# Non-interactive element roles that should never be clicked/typed into
_NON_INTERACTIVE_ROLES = {
    "statictext", "heading", "rootwebarea", "paragraph",
    "layouttable", "layouttablerow", "layouttablecell",
    "generic", "main", "list", "alert", "listitem",
    "image", "none", "separator", "table", "group",
    "definition", "descriptionlist", "term",
}

# Regex to parse accessibility tree lines: [id] role 'name'
_PARSE_ELEMENT_RE = re.compile(
    r"\[(\d+)\]\s+(\w+)\s+('[^']*'|\"[^\"]*\")",
    re.IGNORECASE,
)


def _parse_observation_roles(obs: str) -> dict[str, str]:
    """Parse accessibility tree observation to map element_id → role."""
    roles: dict[str, str] = {}
    for m in _PARSE_ELEMENT_RE.finditer(obs):
        eid = m.group(1)
        role = m.group(2).lower()
        # Keep first occurrence (most specific)
        if eid not in roles:
            roles[eid] = role
    return roles


def _is_interactive(role: str) -> bool:
    """Check if an element role is interactive (clickable/typable)."""
    return role.lower() not in _NON_INTERACTIVE_ROLES


def _check_action_grounding(
    action: Action, obs: str
) -> tuple[bool, str]:
    """Validate that the action targets an interactive element.

    Returns (is_valid, error_message).
    """
    action_type = action.get("action_type", 0)
    element_id = action.get("element_id", "")

    # Only check actions that target specific elements
    if action_type not in (
        ActionTypes.CLICK,
        ActionTypes.TYPE,
        ActionTypes.HOVER,
    ):
        return True, ""

    if not element_id:
        return True, ""

    roles = _parse_observation_roles(obs)
    role = roles.get(element_id, "")

    if not role:
        return True, ""  # Can't determine role, allow

    if not _is_interactive(role):
        return False, (
            f"Action targets non-interactive element: "
            f"[{element_id}] is {role}. "
            f"Choose a clickable/typable element (link, button, textbox, "
            f"combobox, checkbox, radio, menuitem, option, tab, searchbox)."
        )

    return True, ""


class Agent:
    """Base class for the agent"""

    def __init__(self, *args: Any) -> None:
        pass

    def next_action(
        self, trajectory: Trajectory, intent: str, meta_data: Any
    ) -> Action:
        """Predict the next action given the observation"""
        raise NotImplementedError

    def reset(
        self,
        test_config_file: str,
    ) -> None:
        raise NotImplementedError


class TeacherForcingAgent(Agent):
    """Agent that follows a pre-defined action sequence"""

    def __init__(self) -> None:
        super().__init__()

    def set_action_set_tag(self, tag: str) -> None:
        self.action_set_tag = tag

    def set_actions(self, action_seq: str | list[str]) -> None:
        if isinstance(action_seq, str):
            action_strs = action_seq.strip().split("\n")
        else:
            action_strs = action_seq
        action_strs = [a.strip() for a in action_strs]

        actions = []
        for a_str in action_strs:
            try:
                if self.action_set_tag == "playwright":
                    cur_action = create_playwright_action(a_str)
                elif self.action_set_tag == "id_accessibility_tree":
                    cur_action = create_id_based_action(a_str)
                else:
                    raise ValueError(
                        f"Unknown action type {self.action_set_tag}"
                    )
            except ActionParsingError as e:
                cur_action = create_none_action()

            cur_action["raw_prediction"] = a_str
            actions.append(cur_action)

        self.actions: list[Action] = actions

    def next_action(
        self, trajectory: Trajectory, intent: str, meta_data: Any
    ) -> Action:
        """Predict the next action given the observation"""
        return self.actions.pop(0)

    def reset(
        self,
        test_config_file: str,
    ) -> None:
        with open(test_config_file) as f:
            ref_actions = json.load(f)["reference_action_sequence"]
            tag = ref_actions["action_set_tag"]
            action_seq = ref_actions["action_sequence"]
            self.set_action_set_tag(tag)
            self.set_actions(action_seq)


class PromptAgent(Agent):
    """prompt-based agent that emits action given the history"""

    @beartype
    def __init__(
        self,
        action_set_tag: str,
        lm_config: lm_config.LMConfig,
        prompt_constructor: PromptConstructor,
    ) -> None:
        super().__init__()
        self.lm_config = lm_config
        self.prompt_constructor = prompt_constructor
        self.action_set_tag = action_set_tag

    def set_action_set_tag(self, tag: str) -> None:
        self.action_set_tag = tag

    @beartype
    def next_action(
        self, trajectory: Trajectory, intent: str, meta_data: dict[str, Any]
    ) -> Action:
        prompt = self.prompt_constructor.construct(
            trajectory, intent, meta_data
        )
        lm_config = self.lm_config
        n = 0
        while True:
            response = call_llm(lm_config, prompt)
            force_prefix = self.prompt_constructor.instruction[
                "meta_data"
            ].get("force_prefix", "")
            response = f"{force_prefix}{response}"
            n += 1
            try:
                parsed_response = self.prompt_constructor.extract_action(
                    response
                )
                if self.action_set_tag == "id_accessibility_tree":
                    action = create_id_based_action(parsed_response)
                elif self.action_set_tag == "playwright":
                    action = create_playwright_action(parsed_response)
                else:
                    raise ValueError(
                        f"Unknown action type {self.action_set_tag}"
                    )
                action["raw_prediction"] = response

                # Validate grounding: check if action targets interactive element
                state_info: StateInfo = trajectory[-1]
                obs = state_info.get("observation", {})
                obs_text = obs.get("text", "") if isinstance(obs, dict) else ""
                if obs_text:
                    is_valid, err_msg = _check_action_grounding(action, obs_text)
                    if not is_valid:
                        if n >= lm_config.gen_config["max_retry"]:
                            action["raw_prediction"] = (
                                f"{response}\n[GROUNDING ERROR: {err_msg}]"
                            )
                            break
                        # Add error feedback and retry
                        prompt = self.prompt_constructor.construct(
                            trajectory, intent, meta_data
                        )
                        # Inject grounding feedback into the prompt
                        if isinstance(prompt, list):
                            prompt.append({
                                "role": "user",
                                "content": (
                                    f"ERROR: {err_msg}\n"
                                    f"Please choose a different, valid interactive element "
                                    f"and return a corrected JSON action."
                                ),
                            })
                        continue

                break
            except ActionParsingError as e:
                if n >= lm_config.gen_config["max_retry"]:
                    action = create_none_action()
                    action["raw_prediction"] = response
                    break

        return action

    def reset(self, test_config_file: str) -> None:
        pass


def construct_agent(args: argparse.Namespace) -> Agent:
    llm_config = lm_config.construct_llm_config(args)

    agent: Agent
    if args.agent_type == "teacher_forcing":
        agent = TeacherForcingAgent()
    elif args.agent_type == "prompt":
        with open(args.instruction_path) as f:
            constructor_type = json.load(f)["meta_data"]["prompt_constructor"]
        tokenizer = Tokenizer(args.provider, args.model)
        prompt_constructor = eval(constructor_type)(
            args.instruction_path, lm_config=llm_config, tokenizer=tokenizer
        )
        agent = PromptAgent(
            action_set_tag=args.action_set_tag,
            lm_config=llm_config,
            prompt_constructor=prompt_constructor,
        )
    else:
        raise NotImplementedError(
            f"agent type {args.agent_type} not implemented"
        )
    return agent
