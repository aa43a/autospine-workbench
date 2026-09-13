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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--boundary', action='store_true', help='Use pinned boundary shape trial instead of weight blend')
    mode.add_argument('--refine-trial', help='Refine failing intervals of an exact boundary trial')
    mode.add_argument('--temporal-trial', help='Continue only failed clips of an exact adaptive trial')
    parser.add_argument('--slot', action='append', help='Limit a new boundary trial to explicitly selected regions')
    args = parser.parse_args()
    if args.slot and not args.boundary: parser.error('--slot requires --boundary; refinement retains its source selection')
    store = AnimatedStore(args.state_root)
    if args.temporal_trial:
        from autospine_workbench.targets.character43.shoulder_temporal import generate as temporal
        files, report = temporal(store.read(args.character), args.character,
            store.read(args.temporal_trial), args.temporal_trial, progress=lambda m: print(m, flush=True))
    elif args.refine_trial:
        from autospine_workbench.targets.character43.shoulder_boundary_adaptive import generate as adaptive
        files, report = adaptive(store.read(args.character), args.character,
            store.read(args.refine_trial), args.refine_trial, progress=lambda m: print(m, flush=True))
    elif args.boundary:
        from autospine_workbench.targets.character43.shoulder_boundary_candidate import generate as boundary
        files, report = boundary(store.read(args.character), args.character, slot_ids=args.slot, progress=lambda m: print(m, flush=True))
    else:
        files, report = generate(store.read(args.character), args.character)
    report['artifact_sha256'] = store.publish(files)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
