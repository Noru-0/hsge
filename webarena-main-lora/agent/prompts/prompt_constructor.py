import ast
import json
import os
import re
from pathlib import Path
from typing import Any, TypedDict

from browser_env import Action, ActionParsingError, Trajectory
from browser_env.env_config import URL_MAPPINGS
from browser_env.utils import StateInfo
from llms import lm_config
from llms.tokenizers import Tokenizer
from llms.utils import APIInput


class Instruction(TypedDict):
    """Instruction for constructing prompt"""

    intro: str
    examples: list[tuple[str, str]]
    template: str
    meta_data: dict[str, Any]


class PromptConstructor(object):
    def __init__(
        self,
        instruction_path: str | Path,
        lm_config: lm_config.LMConfig,
        tokenizer: Tokenizer,
    ):
        self.instruction_path = Path(instruction_path)
        self.obs_modality = "text"
        self.lm_config = lm_config
        instruction = json.load(open(self.instruction_path))
        instruction["examples"] = [tuple(e) for e in instruction["examples"]]
        self.instruction: Instruction = instruction
        self.tokenizer = tokenizer

    def get_lm_api_input(
        self, intro: str, examples: list[tuple[str, str]], current: str
    ) -> APIInput:

        """Return the require format for an API"""
        message: list[dict[str, str]] | str
        if "openai" in self.lm_config.provider:
            if self.lm_config.mode == "chat":
                message = [{"role": "system", "content": intro}]
                for (x, y) in examples:
                    message.append(
                        {
                            "role": "system",
                            "name": "example_user",
                            "content": x,
                        }
                    )
                    message.append(
                        {
                            "role": "system",
                            "name": "example_assistant",
                            "content": y,
                        }
                    )
                message.append({"role": "user", "content": current})
                return message
            elif self.lm_config.mode == "completion":
                message = f"{intro}\n\n"
                message += "Here are a few examples:\n"
                for example in examples:
                    message += f"Observation\n:{example[0]}\n\n"
                    message += f"Action: {example[1]}\n\n"
                message += "Now make prediction given the observation\n\n"
                message += f"Observation\n:{current}\n\n"
                message += "Action:"
                return message
            else:
                raise ValueError(
                    f"OpenAI models do not support mode {self.lm_config.mode}"
                )
        elif "huggingface" in self.lm_config.provider:
            # https://huggingface.co/blog/llama2#how-to-prompt-llama-2
            # https://github.com/facebookresearch/llama/blob/main/llama/generation.py#L320
            if "Llama-2" in self.lm_config.model:
                if self.lm_config.mode == "chat":
                    B_INST, E_INST = "[INST]", "[/INST]"
                    B_SYS, E_SYS = "<<SYS>>\n", "\n<</SYS>>\n\n"
                    BOS, EOS = "<s>", "</s>"
                    # adding the system message to be the starting of the first example
                    examples = [
                        (
                            B_SYS + intro + E_SYS + examples[0][0],
                            examples[0][1],
                        )
                    ] + examples[1:]
                    message = "".join(
                        [
                            f"{BOS}{B_INST} {x.strip()} {E_INST} {y.strip()} {EOS}"
                            for (x, y) in examples
                        ]
                    )
                    # add the current observation
                    message += f"{BOS}{B_INST} {current.strip()} {E_INST} {self.instruction['meta_data'].get('force_prefix', '')}"

                    return message
                else:
                    raise ValueError("Only chat mode is supported for Llama-2")
            else:
                raise ValueError(
                    f"Huggingface models do not support model_tag {self.lm_config.gen_config['model_tag']}"
                )
        else:
            raise NotImplementedError(
                f"Provider {self.lm_config.provider} not implemented"
            )

    def construct(
        self,
        trajectory: Trajectory,
        intent: str,
        meta_data: dict[str, Any] = {},
    ) -> APIInput:
        raise NotImplementedError

    def map_url_to_real(self, url: str) -> str:
        """Map the urls to their real world counterparts"""
        for i, j in URL_MAPPINGS.items():
            if i in url:
                url = url.replace(i, j)
        return url

    def map_url_to_local(self, url: str) -> str:
        """Map the urls to their local counterparts"""
        for i, j in URL_MAPPINGS.items():
            if j in url:
                url = url.replace(j, i)
            # https
            if j.replace("http", "https") in url:
                url = url.replace(j.replace("http", "https"), i)
        return url

    def _extract_action(self, response: str) -> str:
        raise NotImplementedError

    def extract_action(self, response: str) -> str:
        response = self._extract_action(response)
        response = self.map_url_to_local(response)
        return response


class DirectPromptConstructor(PromptConstructor):
    """The agent will direct predict the action"""

    def __init__(
        self,
        instruction_path: str | Path,
        lm_config: lm_config.LMConfig,
        tokenizer: Tokenizer,
    ):
        super().__init__(instruction_path, lm_config, tokenizer)

    def construct(
        self,
        trajectory: Trajectory,
        intent: str,
        meta_data: dict[str, Any] = {},
    ) -> APIInput:
        """Construct prompt given the trajectory"""
        intro = self.instruction["intro"]
        examples = self.instruction["examples"]
        template = self.instruction["template"]
        keywords = self.instruction["meta_data"]["keywords"]
        state_info: StateInfo = trajectory[-1]  # type: ignore[assignment]

        obs = state_info["observation"][self.obs_modality]
        max_obs_length = self.lm_config.gen_config["max_obs_length"]
        if max_obs_length:
            obs = self.tokenizer.decode(self.tokenizer.encode(obs)[:max_obs_length])  # type: ignore[arg-type]

        page = state_info["info"]["page"]
        url = page.url
        previous_action_str = meta_data["action_history"][-1]

        # input x
        current = template.format(
            objective=intent,
            url=self.map_url_to_real(url),
            observation=obs,
            previous_action=previous_action_str,
        )

        # make sure all keywords are replaced
        assert all([f"{{k}}" not in current for k in keywords])
        prompt = self.get_lm_api_input(intro, examples, current)
        return prompt

    def _extract_action(self, response: str) -> str:
        action_splitter = self.instruction["meta_data"]["action_splitter"]
        pattern = rf"{action_splitter}((.|\n)*?){action_splitter}"
        match = re.search(pattern, response)
        if match:
            return match.group(1).strip()
        else:
            raise ActionParsingError(
                f"Cannot parse action from response {response}"
            )


class CoTPromptConstructor(PromptConstructor):
    """The agent will perform step-by-step reasoning before the answer"""

    def __init__(
        self,
        instruction_path: str | Path,
        lm_config: lm_config.LMConfig,
        tokenizer: Tokenizer,
    ):
        super().__init__(instruction_path, lm_config, tokenizer)
        self.answer_phrase = self.instruction["meta_data"]["answer_phrase"]

    def construct(
        self,
        trajectory: Trajectory,
        intent: str,
        meta_data: dict[str, Any] = {},
    ) -> APIInput:
        intro = self.instruction["intro"]
        examples = self.instruction["examples"]
        template = self.instruction["template"]
        keywords = self.instruction["meta_data"]["keywords"]
        state_info: StateInfo = trajectory[-1]  # type: ignore[assignment]

        obs = state_info["observation"][self.obs_modality]
        max_obs_length = self.lm_config.gen_config["max_obs_length"]
        if max_obs_length:
            obs = self.tokenizer.decode(self.tokenizer.encode(obs)[:max_obs_length])  # type: ignore[arg-type]

        page = state_info["info"]["page"]
        url = page.url
        previous_action_str = meta_data["action_history"][-1]
        current = template.format(
            objective=intent,
            url=self.map_url_to_real(url),
            observation=obs,
            previous_action=previous_action_str,
        )

        assert all([f"{{k}}" not in current for k in keywords])

        prompt = self.get_lm_api_input(intro, examples, current)
        return prompt

    def _extract_action(self, response: str) -> str:
        # find the first occurence of action
        action_splitter = self.instruction["meta_data"]["action_splitter"]
        pattern = rf"{action_splitter}((.|\n)*?){action_splitter}"
        match = re.search(pattern, response)
        if match:
            return match.group(1).strip()
        else:
            raise ActionParsingError(
                f'Cannot find the answer phrase "{self.answer_phrase}" in "{response}"'
            )


# ---------------------------------------------------------------------------
# HSGE Prompt Constructor — bridges HSGE-trained models to WebArena benchmark
# ---------------------------------------------------------------------------
class HSGEPromptConstructor(DirectPromptConstructor):
    """
    Prompt constructor for models SFT-trained on HSGE format.

    The model outputs HSGE-style JSON:
        {"thought": "...", "action": "click('1234')"}

    This constructor:
      1. Uses HSGE system prompt + template (matching training distribution)
      2. Parses the JSON output
      3. Maps HSGE actions to WebArena benchmark actions
    """

    # Mapping from HSGE action functions to WebArena action names
    HSGE_TO_WA_ACTION = {
        "click": "click",
        "fill": "type",
        "type": "type",
        "goto": "goto",
        "send_msg_to_user": "stop",
        "press": "press",
        "scroll": "scroll",
        "hover": "hover",
    }

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize smart quotes and special Unicode characters."""
        return (
            text.replace("\u2019", "'")   # right single quote
                .replace("\u2018", "'")   # left single quote
                .replace("\u201c", '"')   # left double quote
                .replace("\u201d", '"')   # right double quote
                .replace("\u2013", "-")   # en dash
                .replace("\u2014", "-")   # em dash
        )

    # Credential placeholder patterns → benchmark credentials.
    # Prefer env-provided values; keep WebArena shopping defaults only as fallback.
    _DEFAULT_EMAIL = os.environ.get("WA_ACCOUNT_SHOPPING_USERNAME", "emma.lopez@gmail.com")
    _DEFAULT_PASSWORD = os.environ.get("WA_ACCOUNT_SHOPPING_PASSWORD", "Password.123")
    _CREDENTIAL_PLACEHOLDERS = [
        (re.compile(r"^my_email$", re.IGNORECASE), _DEFAULT_EMAIL),
        (re.compile(r"^my_password$", re.IGNORECASE), _DEFAULT_PASSWORD),
        (re.compile(r"^user_email$", re.IGNORECASE), _DEFAULT_EMAIL),
        (re.compile(r"^user_password$", re.IGNORECASE), _DEFAULT_PASSWORD),
        (re.compile(r"^myemail@example\.com$", re.IGNORECASE), _DEFAULT_EMAIL),
        (re.compile(r"^myvalidemail@example\.com$", re.IGNORECASE), _DEFAULT_EMAIL),
        (re.compile(r"^MyBestSecretPassword123$"), _DEFAULT_PASSWORD),
        (re.compile(r"^email$", re.IGNORECASE), _DEFAULT_EMAIL),
        (re.compile(r"^password$", re.IGNORECASE), _DEFAULT_PASSWORD),
        (re.compile(r"^user@example\.com$", re.IGNORECASE), _DEFAULT_EMAIL),
    ]

    @classmethod
    def _inject_credential(cls, text: str) -> str:
        """Replace credential placeholders with configured benchmark credentials."""
        for pattern, replacement in cls._CREDENTIAL_PLACEHOLDERS:
            if pattern.match(text.strip()):
                return replacement
        return text

    def construct(
        self,
        trajectory: Trajectory,
        intent: str,
        meta_data: dict[str, Any] = {},
    ) -> APIInput:
        """Construct HSGE prompt with the same last-five action context as SFT."""
        intro = self.instruction["intro"]
        examples = self.instruction["examples"]
        template = self.instruction["template"]
        keywords = self.instruction["meta_data"]["keywords"]
        state_info: StateInfo = trajectory[-1]  # type: ignore[assignment]

        obs = state_info["observation"][self.obs_modality]
        max_obs_length = self.lm_config.gen_config["max_obs_length"]
        if max_obs_length:
            obs = self.tokenizer.decode(self.tokenizer.encode(obs)[:max_obs_length])  # type: ignore[arg-type]

        page = state_info["info"]["page"]
        url = page.url
        history = meta_data.get("action_history", [])
        recent_actions = history[-5:] if history else []
        previous_action_str = "\n".join(f"- {h}" for h in recent_actions) or "(none)"

        current = template.format(
            objective=intent,
            url=self.map_url_to_real(url),
            observation=obs,
            previous_action=previous_action_str,
        )

        assert all([f"{{k}}" not in current for k in keywords])
        return self.get_lm_api_input(intro, examples, current)

    @staticmethod
    def _parse_hsge_json(response: str) -> dict:
        """Extract JSON object from HSGE model response (robust to markdown fences)."""
        # Strip code fences
        txt = re.sub(r"^```(?:json)?\s*|```\s*$", "", response.strip(), flags=re.MULTILINE)
        # Try direct parse
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            pass
        # Try to find first JSON object
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        action_match = re.search(
            r"(click|fill|type|press|scroll|hover|goto|send_msg_to_user)\([^)]*\)",
            txt,
            re.DOTALL,
        )
        if action_match:
            return {"thought": "", "action": action_match.group(0)}
        raise ActionParsingError(f"Cannot parse HSGE JSON from response: {response[:200]}")

    @classmethod
    def _hsge_to_webarena(cls, action: str) -> str:
        """Convert HSGE action string to WebArena action string.

        HSGE format → WebArena format:
          click('bid')              → click [bid]
          fill('bid','text')        → type [bid] [text] [0]   (no Enter!)
          type('bid','text','0_or_1') → type [bid] [text] [flag]
          press('Enter')            → press [Enter]
          scroll('down'|'up')       → scroll [down]
          hover('bid')              → hover [bid]
          goto('url')               → goto [url]
          send_msg_to_user('x')     → stop [x]
        """
        action = cls._normalize_text(action.strip())
        try:
            expr = ast.parse(action, mode="eval").body
        except SyntaxError as exc:
            raise ActionParsingError(f"Cannot parse HSGE action: {action[:100]}") from exc
        if not isinstance(expr, ast.Call) or not isinstance(expr.func, ast.Name):
            raise ActionParsingError(f"Cannot parse HSGE action: {action[:100]}")
        fn = expr.func.id
        if expr.keywords:
            raise ActionParsingError("HSGE actions do not support keyword arguments")
        args = []
        for arg in expr.args:
            if not isinstance(arg, ast.Constant) or not isinstance(arg.value, (str, int, float)):
                raise ActionParsingError("HSGE action arguments must be literals")
            args.append(cls._normalize_text(str(arg.value)))

        wa_fn = cls.HSGE_TO_WA_ACTION.get(fn)
        if wa_fn is None:
            raise ActionParsingError(f"Unknown HSGE action function: {fn}")

        if fn == "click":
            if not args:
                raise ActionParsingError("click() missing bid argument")
            if not args[0].isdigit():
                raise ActionParsingError(f"click() bid must be numeric, got {args[0]!r}")
            return f"click [{args[0]}]"

        elif fn == "fill":
            if len(args) < 2:
                raise ActionParsingError("fill() needs bid and text")
            if not args[0].isdigit():
                raise ActionParsingError(f"fill() bid must be numeric, got {args[0]!r}")
            # Replace credential placeholders with real credentials
            text = cls._inject_credential(args[1])
            # [0] = do NOT press Enter after typing (unlike type)
            return f"type [{args[0]}] [{text}] [0]"

        elif fn == "type":
            if len(args) < 2:
                raise ActionParsingError("type() needs bid and text")
            if not args[0].isdigit():
                raise ActionParsingError(f"type() bid must be numeric, got {args[0]!r}")
            # Replace credential placeholders with real credentials
            text = cls._inject_credential(args[1])
            enter = args[2] if len(args) >= 3 else "1"
            if enter not in ("0", "1"):
                raise ActionParsingError(f"type() enter flag must be 0 or 1, got: {enter}")
            return f"type [{args[0]}] [{text}] [{enter}]"

        elif fn == "press":
            if not args:
                raise ActionParsingError("press() missing key argument")
            return f"press [{args[0]}]"

        elif fn == "scroll":
            direction = args[0] if args else "down"
            if direction not in ("up", "down"):
                direction = "down"
            return f"scroll [{direction}]"

        elif fn == "hover":
            if not args:
                raise ActionParsingError("hover() missing bid argument")
            if not args[0].isdigit():
                raise ActionParsingError(f"hover() bid must be numeric, got {args[0]!r}")
            return f"hover [{args[0]}]"

        elif fn == "goto":
            if not args:
                raise ActionParsingError("goto() missing url argument")
            return f"goto [{args[0]}]"

        elif fn == "send_msg_to_user":
            msg = args[0] if args else "done"
            return f"stop [{msg}]"

        return action  # fallback

    def _extract_action(self, response: str) -> str:
        """Parse HSGE JSON output and convert to WebArena action string."""
        parsed = self._parse_hsge_json(response)
        hsge_action = parsed.get("action", "").strip()
        if not hsge_action:
            raise ActionParsingError(f"No 'action' field in HSGE response: {response[:200]}")
        return self._hsge_to_webarena(hsge_action)
