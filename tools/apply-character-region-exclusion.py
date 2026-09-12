"""Apply a supplied exact human region decision to a new, reversible candidate."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.region_exclusion import apply


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--decision', type=Path, required=True)
    args = parser.parse_args()
    decision = json.loads(args.decision.read_bytes())
    store = AnimatedStore(args.state_root)
    files = store.read(decision['source_bundle_sha256'])
    result = apply(files, decision)
    digest = store.publish(result)
    if store.read(digest) != result:
        raise ValueError('character_region_exclusion_replay')
    print(json.dumps(dict(bundle_sha256=digest, status='needs_review', production_authorized=False)))


if __name__ == '__main__':
    main()
