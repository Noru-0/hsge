import glob
import importlib
import importlib.util
import json
import os


# use the current directory as the root
def run() -> None:
    """Convert all python files in agent/prompts to json files in agent/prompts/jsons

    Python files are easiser to edit
    """
    for p_file in glob.glob(f"agent/prompts/raw/*.py"):
        base_name = os.path.basename(p_file).replace(".py", "")
        if base_name.startswith("_"):          # skip __init__.py etc.
            continue
        spec = importlib.util.spec_from_file_location(base_name, p_file)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load prompt file {p_file}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        prompt = module.prompt
        # save the prompt as a json file
        os.makedirs("agent/prompts/jsons", exist_ok=True)
        with open(f"agent/prompts/jsons/{base_name}.json", "w+") as f:
            json.dump(prompt, f, indent=2)
    print(f"Done convert python files to json")


if __name__ == "__main__":
    run()
