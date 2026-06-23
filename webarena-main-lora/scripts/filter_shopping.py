#!/usr/bin/env python3
"""Filter WebArena test config to Shopping domain only."""
import json
import sys
import os

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else "config_files/test.raw.json"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "config_files/test_shopping.json"

    with open(input_file) as f:
        all_tasks = json.load(f)

    shopping_tasks = [
        t for t in all_tasks
        if any(s in ("shopping", "shopping_admin") for s in t.get("sites", []))
    ]

    with open(output_file, "w") as f:
        json.dump(shopping_tasks, f, indent=2)

    print(f"Total tasks: {len(all_tasks)}")
    print(f"Shopping tasks: {len(shopping_tasks)}")
    print(f"Saved to: {output_file}")

    # Show task_id range
    if shopping_tasks:
        ids = [t["task_id"] for t in shopping_tasks]
        print(f"Task IDs: {min(ids)} - {max(ids)}")
        print(f"Sites: {set(s for t in shopping_tasks for s in t['sites'])}")


if __name__ == "__main__":
    main()
