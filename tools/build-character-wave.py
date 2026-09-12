"""Publish whole-character wave diagnostics; failed geometry cannot enter the motion catalog."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.builtin_wave_candidate import generate


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--character', required=True)
    parser.add_argument('--repair', action='store_true')
    parser.add_argument('--drape-helper', action='append', default=[], help='Existing wrist cloth helper to stabilize')
    args = parser.parse_args()
    store = AnimatedStore(args.state_root)
    result = generate(store.read(args.character), args.character, repair=args.repair, drape_helpers=args.drape_helper)
    digest = store.publish(result)
    report = json.loads(result['motion-review.json'])
    print(json.dumps(dict(bundle_sha256=digest, geometry_passed=report['geometry_passed'],
                         failing_slots=report['failing_slots'])))
