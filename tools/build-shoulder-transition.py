"""Build an isolated shoulder trial; failing geometry remains blocked."""
import argparse
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.shoulder_transition import generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--character', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    store = AnimatedStore(args.state_root)
    files, report = generate(store.read(args.character), args.character)
    report['artifact_sha256'] = store.publish(files)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
