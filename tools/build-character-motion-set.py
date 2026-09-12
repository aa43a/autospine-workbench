"""Group same-source motion candidates for one workbench action selection."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.motion_set import combine


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--character', required=True)
    parser.add_argument('--motion-candidate', action='append', required=True)
    args = parser.parse_args(); store = AnimatedStore(args.state_root)
    files = combine(store.read(args.character), args.character,
                    [(d, store.read(d)) for d in args.motion_candidate])
    print(json.dumps(dict(bundle_sha256=store.publish(files),
                         animations=json.loads(files['character-manifest.json'])['animations'])))
