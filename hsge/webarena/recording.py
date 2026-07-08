"""Episode persistence in the run-dir layout build_sft_dataset.py reads.

Shared by the phase-1 explorer (runtime.py) and the phase-2 collection loop
(collect.py). extra_meta lets phase 2 attach verification metadata
(task_id/verified/eval/answer) to episode_meta.json.
"""
from __future__ import annotations

import base64
import json
import os


def record_episode(out_dir: str, episode_index: int, goal: str, steps, obs_texts,
                   obs_screenshots, success: bool, difficulty: int, tag: str,
                   extra_meta: dict | None = None) -> str:
    ep_id = f"ep_{episode_index:04d}"
    ep = os.path.join(out_dir, "episodes", ep_id)
    os.makedirs(os.path.join(ep, "page_state"), exist_ok=True)
    meta = {"kind": "low_level_trajectory", "goal": goal,
            "outcome": {"success": bool(success), "reward": 1.0 if success else 0.0, "response": ""},
            "metadata": {"difficulty": difficulty, "tags": [tag]}, "step_count": len(steps)}
    if extra_meta:
        meta.update(extra_meta)
    json.dump(meta, open(os.path.join(ep, "episode_meta.json"), "w"), indent=2)
    with open(os.path.join(ep, "episode.jsonl"), "w") as f:
        for k, st in enumerate(steps):
            axp = f"page_state/step_{k:03d}_axtree.txt"
            open(os.path.join(ep, axp), "w").write(obs_texts[k] if k < len(obs_texts) else "")
            observation = {"axtree_txt": {"path": axp}}
            shot = obs_screenshots[k] if k < len(obs_screenshots) else None
            if shot:
                shotp = f"page_state/step_{k:03d}_screenshot.jpg"
                open(os.path.join(ep, shotp), "wb").write(base64.b64decode(shot))
                observation["screenshot"] = {"path": shotp}
            rec = {"record_type": "step", "index": k,
                   "action": json.dumps({"thought": st.obs_summary, "action": st.action}),
                   "parsed_action": st.action, "thought": st.obs_summary,
                   "observation": observation, "hints": st.hints,
                   "last_error": st.last_error, "url": st.url}
            f.write(json.dumps(rec) + "\n")
    return ep_id
