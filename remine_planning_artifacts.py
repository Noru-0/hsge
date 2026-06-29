#!/usr/bin/env python3
"""Best-effort recovery of planning evidence from an older HSGE run.

The utility is deliberately conservative: a URL transition is useful provenance,
but it is not effect evidence without the corresponding post-action AXTree.
Recovered candidates remain non-planner-ready until fresh verification.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from hsge.webarena.action_validation import action_family
from hsge.webarena.predicates import build_predicate_extractor, predicates_from


def _read_json(path: Path, default=None):
    if not path.is_file():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _axtree(episode_dir: Path, observation: dict) -> str | None:
    relative = observation.get("axtree_txt", {}).get("path", "")
    path = episode_dir / relative
    return path.read_text(encoding="utf-8") if relative and path.is_file() else None


def _event_transitions(source: Path) -> dict[int, list[dict]]:
    transitions: dict[int, list[dict]] = defaultdict(list)
    for event in _read_jsonl(source / "events.jsonl"):
        episode_id = event.get("episode_id")
        if (
            isinstance(episode_id, int)
            and event.get("component") == "solver"
            and event.get("event") == "url_discovered"
        ):
            transitions[episode_id].append(event.get("data", {}))
    return transitions


def remine(source: Path, output: Path, plugins: list[str]) -> dict:
    if source.resolve() == output.resolve():
        raise ValueError("output directory must differ from the source run")
    output.mkdir(parents=True, exist_ok=True)
    extractor = build_predicate_extractor(plugins)
    event_transitions = _event_transitions(source)
    evidence: list[dict] = []
    counts = Counter()

    for episode_dir in sorted((source / "episodes").glob("ep_*")):
        meta = _read_json(episode_dir / "episode_meta.json", {}) or {}
        episode_id = int(episode_dir.name.rsplit("_", 1)[-1])
        tags = meta.get("metadata", {}).get("tags", [])
        if "LOCAL" not in tags or not meta.get("outcome", {}).get("success", False):
            continue
        counts["successful_local_episodes"] += 1
        steps = [
            row for row in _read_jsonl(episode_dir / "episode.jsonl")
            if row.get("record_type") == "step"
        ]
        final_state = meta.get("final_state", {}) or {}
        final_ax_path = episode_dir / final_state.get("axtree_txt", {}).get("path", "")
        final_ax = (
            final_ax_path.read_text(encoding="utf-8")
            if final_state.get("axtree_txt") and final_ax_path.is_file()
            else None
        )
        transitions = event_transitions.get(episode_id, [])

        for index, row in enumerate(steps):
            observation = row.get("observation", {})
            pre_url = observation.get("url", "")
            pre_ax = _axtree(episode_dir, observation)
            post_url = ""
            post_ax = None
            provenance = ""
            if index + 1 < len(steps):
                next_observation = steps[index + 1].get("observation", {})
                post_url = next_observation.get("url", "")
                post_ax = _axtree(episode_dir, next_observation)
                provenance = "next_step_observation"
            elif final_ax is not None:
                post_url = final_state.get("url", "")
                post_ax = final_ax
                provenance = "episode_final_state"
            else:
                matching = [t for t in transitions if t.get("source_url") == pre_url]
                post_url = matching[-1].get("target_url", "") if matching else ""
                provenance = "url_event_without_final_state"

            complete = pre_ax is not None and post_ax is not None and bool(post_url)
            pre = predicates_from(pre_url, pre_ax or "", extractor) if pre_ax is not None else set()
            post = predicates_from(post_url, post_ax or "", extractor) if complete else set()
            effects = post - pre if complete else set()
            counts["steps"] += 1
            counts["complete_transitions" if complete else "incomplete_transitions"] += 1
            if effects:
                counts["effectful_transitions"] += 1
            evidence.append({
                "episode_id": episode_id,
                "step_index": index,
                "goal": meta.get("goal", ""),
                "action": row.get("parsed_action", ""),
                "action_family": action_family(row.get("parsed_action", "")),
                "pre_url": pre_url,
                "post_url": post_url,
                "preconditions": sorted(pre),
                "effects": sorted(effects),
                "complete": complete,
                "incomplete_reason": "" if complete else "missing_final_state_evidence",
                "provenance": provenance,
                "predicate_schema_version": extractor.schema_version,
            })

    with (output / "planning_evidence.jsonl").open("w", encoding="utf-8") as handle:
        for row in evidence:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    grouped = defaultdict(list)
    for row in evidence:
        if row["complete"] and row["effects"]:
            grouped[(row["action_family"], tuple(row["effects"]))].append(row)
    candidates = [{
        "candidate_id": f"remined_{index:04d}",
        "action_family": key[0],
        "effects": list(key[1]),
        "support": len(rows),
        "episode_ids": sorted({row["episode_id"] for row in rows}),
        "planning_ready": False,
        "planning_rejection_reason": "remined_evidence_requires_fresh_verification",
        "predicate_schema_version": extractor.schema_version,
    } for index, (key, rows) in enumerate(sorted(grouped.items()), start=1)]
    (output / "operator_candidates.json").write_text(
        json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output / "graph.json").write_text(
        json.dumps({
            "low_level": {"n_states": 0, "states": [], "trajectory_edges": {}},
            "high_level": {
                "n_skills": 0,
                "n_operators": 0,
                "n_composition_edges": 0,
                "skills": {},
                "operators": {},
                "skill_to_skill": {},
            },
        }, indent=2),
        encoding="utf-8",
    )
    (output / "curriculum.json").write_text("[]\n", encoding="utf-8")
    (output / "curriculum_diagnostics.json").write_text(json.dumps({
        "status": "no_planner_ready_skills",
        "planner_ready_skills": 0,
        "reachable_goals": 0,
        "terminal_tasks": 0,
        "all_effects": [],
    }, indent=2), encoding="utf-8")
    report = {
        "source_run": str(source),
        "output": str(output),
        "predicate_schema_version": extractor.schema_version,
        "status": "best_effort_incomplete" if counts["incomplete_transitions"] else "evidence_recovered",
        "counts": dict(sorted(counts.items())),
        "planner_ready_operators": 0,
        "note": "Candidates require fresh effect verification and are not exported as operators.",
    }
    (output / "remine_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--predicate-plugins", nargs="*", default=["commerce"])
    args = parser.parse_args()
    report = remine(args.source_run, args.output, args.predicate_plugins)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
