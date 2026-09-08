"""Predeclared reference-boundary probes, independent of candidate gap detection."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from ..resolved_project import canonical_sha256
from ..targets.spine43.alpha_seam import position
from ..targets.spine43.continuous_pose import world
from .seam_candidate_hub import bundle_bytes


def build(doc, alpha, follower):
    animation = next(iter(doc['animations'].values()))
    if max(k['time'] for bone in animation['bones'].values() for k in bone.get('rotate', [])) != 2:
        raise ValueError('boundary_probe_duration')
    relations = [r for r in alpha['relations'] if r['follower'] == follower]
    if len(relations) != 1 or not relations[0]['pairs']:
        raise ValueError('boundary_probe_relation')
    relation = relations[0]
    driver = relation['driver']
    boundaries = alpha['boundaries']
    setup = world(doc, 0)

    def midpoint(pair, pose):
        a = position(boundaries[driver]['samples'][pair['driver_sample']], pose[driver])
        b = position(boundaries[follower]['samples'][pair['follower_sample']], pose[follower])
        return [(x + y) / 2 for x, y in zip(a, b)]

    ordered = sorted(range(len(relation['pairs'])),
                     key=lambda i: (*midpoint(relation['pairs'][i], setup), i))
    selected = sorted({ordered[0], ordered[(len(ordered)-1)//2], ordered[-1]})
    samples = []
    for frame in range(61):
        pose = world(doc, frame / 30)
        for pair_index in selected:
            point = midpoint(relation['pairs'][pair_index], pose)
            if not all(math.isfinite(v) for v in point):
                raise ValueError('boundary_probe_nonfinite')
            samples.append(dict(frame=frame, pair_index=pair_index, reference_midpoint=point,
                                world_point=[math.floor(v) + .5 for v in point]))
    return dict(schema='autospine.seam-boundary-probes/v1', profile='reference-setup-x-y-extrema-median-30fps-v1',
                authority='none', production_authorized=False, status='needs_review',
                fps=30, duration=2, selection_basis='reference_only_not_gap_detection',
                relations=[dict(driver=driver, follower=follower, selected_pair_indices=selected, samples=samples)])


def compile_report(reference_path, manifest_path, follower):
    reference = json.loads(reference_path.read_bytes())
    if reference['schema'] != 'autospine.continuous-anchor-preview/v1':
        raise ValueError('boundary_probe_reference')
    files = bundle_bytes(manifest_path.parent, reference['files'])
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    bundle_bytes(manifest_path.parent, manifest['files'])
    if manifest['files'].get('skeleton.json') != hashlib.sha256(files['skeleton.json']).hexdigest():
        raise ValueError('boundary_probe_manifest')
    report = build(json.loads(files['skeleton.json']), reference['alpha_seam_qa']['after'], follower)
    report.update(source_reference_sha256=canonical_sha256(reference),
                  reference_manifest_sha256=hashlib.sha256(raw).hexdigest())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('reference', 'manifest', 'output-dir'):
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--follower', required=True)
    args = parser.parse_args()
    report = compile_report(args.reference, args.manifest, args.follower)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / (canonical_sha256(report)+'.json')
    if target.exists() and json.loads(target.read_bytes()) != report:
        raise ValueError('boundary_probe_existing_corrupt')
    target.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(target)


if __name__ == '__main__':
    main()
