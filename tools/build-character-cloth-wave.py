"""Publish a diagnostic cloth wave for independent Runtime inspection, without adoption."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.cloth_shape_bake import bake


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-root', type=Path, required=True); p.add_argument('--wave', required=True)
    p.add_argument('--helper', required=True); p.add_argument('--samples', type=int, default=65)
    p.add_argument('--adaptive', action='store_true')
    p.add_argument('--temporal', action='store_true')
    p.add_argument('--exact-temporal', action='store_true')
    p.add_argument('--continuation', action='store_true')
    p.add_argument('--material', action='store_true')
    p.add_argument('--material-subframes', action='store_true')
    args = p.parse_args(); store = AnimatedStore(args.state_root); source = store.read(args.wave)
    builder = bake
    if args.adaptive:
        from autospine_workbench.targets.character43.cloth_shape_adaptive import build
        builder = build
    options = dict(samples=args.samples, temporal=args.temporal, exact_temporal=args.exact_temporal,
                   continuation=args.continuation, material=args.material, material_subframes=args.material_subframes)
    if args.adaptive: options['progress'] = lambda row: print(json.dumps(row), flush=True)
    result = builder(json.loads(source['skeleton.json']), 'wave-left', args.helper, **options)
    result.update({k: v for k, v in source.items() if k.endswith('.png') or k == 'skeleton.atlas'})
    qa = json.loads(result['deformation.json'])
    material_status = json.loads(result['cloth-strain.json'])['passed'] if 'cloth-strain.json' in result else None
    result['character-manifest.json'] = canonical_bytes(dict(
        schema='autospine.character-cloth-wave-trial/v1', source_wave_sha256=args.wave,
        authority='none', production_authorized=False, geometry_passed=qa['passed'],
        files={k: sha256(v).hexdigest() for k, v in result.items()}))
    print(json.dumps(dict(bundle_sha256=store.publish(result), geometry_passed=qa['passed'],
                         material_passed=material_status, production_authorized=False)))
