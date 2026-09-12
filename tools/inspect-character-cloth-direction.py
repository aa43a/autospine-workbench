"""Inspect the existing cloth direction driver without registering or adopting it."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.wave_motion import build_wave
from autospine_workbench.targets.character43.cloth_direction_probe import sweep


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--character', required=True)
    parser.add_argument('--helper', action='append', required=True)
    parser.add_argument('--samples', type=int, default=65)
    parser.add_argument('--shape-trial', action='store_true', help='Try pinned cloth shape on one helper')
    parser.add_argument('--constrained', action='store_true')
    parser.add_argument('--existing-wave', action='store_true', help='Preserve an existing repaired wave')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    files = AnimatedStore(args.state_root).read(args.character)
    document = json.loads(files['skeleton.json'])
    if args.constrained and not args.shape_trial: parser.error('constraints require shape trial')
    if not args.existing_wave: document, _ = build_wave(document)
    elif 'wave-left' not in document['animations']: parser.error('source has no wave-left')
    if args.shape_trial:
        if len(args.helper) != 1: parser.error('shape trial requires exactly one helper')
        from autospine_workbench.targets.character43.cloth_shape_probe import probe
        report = probe(document, 'wave-left', args.helper[0], samples=args.samples, constrained=args.constrained)
    else:
        report = sweep(document, 'wave-left', args.helper, samples=args.samples)
    report['source_character_sha256'] = args.character
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(report))
    print(json.dumps(report, ensure_ascii=False))
