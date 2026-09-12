"""Compare every BVH joint/frame against independently sampled Blender world heads."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.bvh_fk import _world_matrices, _origin


def verify(raw, evidence):
    if hashlib.sha256(raw).hexdigest() != evidence['bridge']['bvh_sha256']:
        raise ValueError('bvh_identity_mismatch')
    bvh = parse_bvh(raw)
    samples = evidence['samples']
    if len(samples) != len(bvh.frames):
        raise ValueError('frame_count_mismatch')
    parents = {b['name']: b['parent'] for b in evidence['bones']}
    actual = {b.name: bvh.joints[b.parent_index].name if b.parent_index is not None else None
              for b in bvh.joints}
    if actual != parents:
        raise ValueError('joint_topology_mismatch')
    transform = evidence['bridge']['local_to_blender_world']
    worst, time_error = 0.0, 0.0
    for index, (frame, sample) in enumerate(zip(bvh.frames, samples)):
        time_error = max(time_error, abs(index*bvh.frame_time_seconds-sample['seconds']))
        if set(sample['joints']) != set(actual):
            raise ValueError('sample_joint_inventory_mismatch')
        for joint, matrix in zip(bvh.joints, _world_matrices(bvh, frame)):
            local = (*_origin(matrix), 1.0)
            world = [sum(row[j]*local[j] for j in range(4)) for row in transform[:3]]
            error = math.dist(world, sample['joints'][joint.name])
            if not math.isfinite(error):
                raise ValueError('nonfinite_joint_error')
            worst = max(worst, error)
    return {'schema': 'local.fbx-bvh-verification/v1', 'authority': 'none',
            'source_sha256': evidence['source_sha256'], 'bvh_sha256': bvh.source_sha256,
            'frames': len(samples), 'joints': len(actual), 'max_world_error': worst,
            'max_time_error_seconds': time_error, 'world_tolerance': 0.0001,
            'passed': worst <= 0.0001 and time_error <= 1e-8,
            'scope': 'joint_heads_and_time_only_not_mesh_or_runtime'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bvh', type=Path)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = verify(args.bvh.read_bytes(), json.loads(args.evidence.read_bytes()))
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    if not result['passed']:
        raise SystemExit(1)
