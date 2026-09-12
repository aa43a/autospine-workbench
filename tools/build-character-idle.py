"""Publish an exact-source whole-character idle candidate for workbench registration."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.builtin_idle_candidate import generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--character', required=True)
    args = parser.parse_args()
    store = AnimatedStore(args.state_root)
    candidate = generate(store.read(args.character), args.character)
    digest = store.publish(candidate)
    evidence = json.loads(candidate['motion-review.json'])
    print(json.dumps(dict(bundle_sha256=digest, geometry_passed=evidence['geometry_passed'],
                         loop_endpoint_error_px=evidence['loop_endpoint_error_px'])))


if __name__ == '__main__':
    main()
