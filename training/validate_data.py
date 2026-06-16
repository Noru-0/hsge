#!/usr/bin/env python3
"""Validate training data before launching SFT."""
import json, sys, re

def validate(filepath: str):
    print(f"Validating: {filepath}")
    data = [json.loads(l) for l in open(filepath)]
    n = len(data)
    print(f"  Total examples: {n}")

    issues = []
    std_actions = {'click', 'fill', 'select_option', 'goto', 'send_msg_to_user', 'go_back'}

    for i, ex in enumerate(data):
        msgs = ex.get("messages")
        if not msgs or len(msgs) != 3:
            issues.append(f"[{i}] Expected 3 messages, got {len(msgs) if msgs else 0}")
            continue
        roles = [m["role"] for m in msgs]
        if roles != ["system", "user", "assistant"]:
            issues.append(f"[{i}] Wrong role order: {roles}")

        # Check assistant action format
        act_str = msgs[2]["content"]
        try:
            act = json.loads(act_str)
            action = act.get("action", "")
            fn_match = re.match(r'(\w+)\(', action)
            if fn_match:
                fn = fn_match.group(1)
                if fn not in std_actions:
                    issues.append(f"[{i}] Non-standard action '{fn}' (not critical)")
            else:
                issues.append(f"[{i}] Action has no function call: {action[:80]}")
        except json.JSONDecodeError:
            issues.append(f"[{i}] Assistant content is not valid JSON")

    # Difficulty distribution
    by_diff = {}
    for ex in data:
        d = ex.get("difficulty", 0)
        by_diff[d] = by_diff.get(d, 0) + 1
    print(f"  Difficulty distribution: {dict(sorted(by_diff.items()))}")

    # AXTree coverage
    no_tree = sum(1 for e in data if not e.get("axtree_loaded", True))
    print(f"  Without AXTree text: {no_tree}/{n}")

    # Content stats
    lengths = [sum(len(m["content"]) for m in ex["messages"]) for ex in data]
    print(f"  Content length: min={min(lengths)}, max={max(lengths)}, avg={sum(lengths)//n}")
    print(f"  Estimated tokens: min~{min(lengths)//3}, max~{max(lengths)//3}, avg~{sum(lengths)//3//n}")

    if issues:
        print(f"\n  Issues found ({len(issues)}):")
        for iss in issues[:15]:
            print(f"    - {iss}")
        if len(issues) > 15:
            print(f"    ... and {len(issues)-15} more")
    else:
        print("\n  ✅ All examples valid!")

    print("\nReady for training.")

if __name__ == "__main__":
    validate(sys.argv[1] if len(sys.argv) > 1 else "/root/data/train.jsonl")
