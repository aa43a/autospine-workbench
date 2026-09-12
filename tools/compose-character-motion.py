"""Merge exact character and motion candidate bundles; no adoption or release authority."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.motion_composition import compose


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--character', required=True)
    parser.add_argument('--motion-candidate', required=True)
    args = parser.parse_args()
    store = AnimatedStore(args.state_root)
    result = compose(store.read(args.character), store.read(args.motion_candidate), args.character, args.motion_candidate)
    digest = store.publish(result)
    if store.read(digest) != result: raise ValueError('character_motion_composition_replay')
    print(json.dumps(dict(bundle_sha256=digest, status='needs_review')))
