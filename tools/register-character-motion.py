"""Register an exact generated motion candidate for the workbench action selector."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.animated_input_index import inspect_registration
from autospine_workbench.automation.character_motion_catalog import register


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--character', required=True)
    parser.add_argument('--motion-candidate', required=True)
    args = parser.parse_args(); state = args.state_root.resolve()
    projects = ProjectStore(args.workspace.resolve(), state)
    manager = SimpleNamespace(root=state/'jobs/character-web-v1', application=SimpleNamespace(store=AnimatedStore(state)))
    sources = inspect_registration(projects, args.project)['source_addresses']
    choice = register(manager, args.project, args.character, args.motion_candidate, sources)
    print(json.dumps(dict(choice_id=choice, authority='none')))
