"""Build a current character candidate from an explicit sleeve job or saved ordinary route."""
import argparse
import json
from pathlib import Path

from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_application import AnimatedApplication
from autospine_workbench.automation.sleeve_web_jobs import SleeveWebJobs
from autospine_workbench.automation.character_composition import build_character


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project'); parser.add_argument('--sleeve-job')
    parser.add_argument('--workspace', type=Path, default=Path('..'))
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    args = parser.parse_args()
    store = ProjectStore(args.workspace.resolve(), args.state_root.resolve())
    sleeves = SleeveWebJobs(store)
    try:
        result = build_character(AnimatedApplication(store), sleeves, args.project, args.sleeve_job)
        print(json.dumps(result, ensure_ascii=False))
    finally:
        sleeves.close()


if __name__ == '__main__':
    main()
