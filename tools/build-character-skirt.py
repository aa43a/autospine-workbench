"""Build a source-preserving whole-character skirt mesh trial for selected layers."""
import argparse
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.skirt_candidate import generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--character', required=True)
    parser.add_argument('--layer', action='append', required=True)
    parser.add_argument('--step', type=int, default=32)
    parser.add_argument('--waist-driver', choices=['reviewed-chest-v1'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    store = AnimatedStore(args.state_root)
    files, report = generate(store.read(args.character), args.character, args.layer, step=args.step,
                             waist_driver=args.waist_driver)
    digest = store.publish(files)
    args.output.mkdir(parents=True, exist_ok=True)
    receipt = dict(bundle_sha256=digest, source_character_sha256=args.character,
                   status=report['status'], geometry_passed=report['geometry_passed'],
                   setup_error_px=report['setup_error_px'], layers=[r['layer_id'] for r in report['rows']],
                   authority='none', selected=False)
    if report.get('blocked_layers'): receipt['blocked_layers'] = report['blocked_layers']
    (args.output/'generation.json').write_bytes(canonical_bytes(receipt))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
