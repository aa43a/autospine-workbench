"""Prepare an explicitly projected Mixamo BVH map and publish existing MotionIR bundle."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion2d.mixamo_map import build_map
from autospine_workbench.motion_bvh_commands import compile_bvh_motion_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bvh', type=Path, required=True)
    parser.add_argument('--map-output', type=Path, required=True)
    parser.add_argument('--state-root', type=Path, required=True)
    parser.add_argument('--clip-id', required=True)
    parser.add_argument('--reference-length', type=float, required=True)
    parser.add_argument('--screen-x', required=True)
    parser.add_argument('--screen-y', required=True)
    parser.add_argument('--depth', required=True)
    parser.add_argument('--prefix', default='')
    parser.add_argument('--contact-parameters', type=Path)
    args = parser.parse_args()
    contact = json.loads(args.contact_parameters.read_bytes()) if args.contact_parameters else None
    mapping = build_map(parse_bvh(args.bvh.read_bytes()), clip_id=args.clip_id,
                        reference_length=args.reference_length, screen_x=args.screen_x,
                        screen_y=args.screen_y, depth=args.depth, prefix=args.prefix, contact=contact)
    args.map_output.parent.mkdir(parents=True, exist_ok=True)
    args.map_output.write_text(json.dumps(mapping, indent=2), encoding='utf-8')
    result = compile_bvh_motion_bundle(args.state_root, args.bvh, args.map_output)
    print(json.dumps(asdict(result), default=str))


if __name__ == '__main__':
    main()
