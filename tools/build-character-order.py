"""Publish a reversible order experiment; BACK:FRONT names exact existing slots."""
import argparse
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.order_candidate import generate


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--behind', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    store = AnimatedStore(args.state_root)
    files, report = generate(store.read(args.source), [x.split(':') for x in args.behind])
    digest = store.publish(files)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'generation.json').write_bytes(canonical_bytes(dict(bundle_sha256=digest, report=report)))
    print(json.dumps(dict(bundle_sha256=digest, changed=report['changed'], authority='none')))
