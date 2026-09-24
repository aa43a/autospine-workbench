"""Record an isolated alternative-skinning counterexample without publishing."""
import argparse
import json
import math
from pathlib import Path

from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.asset.planning.component_local_solver import metrics
from autospine_workbench.targets.character43.affine_pose import sample, matrices
from autospine_workbench.targets.character43.dual_rotation_skinning import weighted_points


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('scene', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--animation', required=True)
    parser.add_argument('--slot', action='append', required=True)
    args = parser.parse_args()
    scene = json.loads(args.scene.read_bytes()); document = scene['skeleton']
    animation = document['animations'][args.animation]
    if animation.get('deform') or any(
            channels.get('deform') for slots in animation.get('attachments', {}).values()
            for slot, choices in slots.items() if slot in args.slot for channels in choices.values()):
        raise ValueError('dual_probe_existing_deform_would_be_discarded')
    times = sorted({k['time'] for channels in animation.get('bones', {}).values()
                    for k in channels.get('rotate', [])})
    if len(times) < 2:
        raise ValueError('dual_probe_missing_source_times')
    setup_doc = dict(document, animations={'setup': {}})
    setup = sample(setup_doc, 'setup', 0)[0]
    rest = matrices(setup_doc, 'setup', 0)
    records = []
    for time in times:
        before = sample(document, args.animation, time)[0]
        current = matrices(document, args.animation, time)
        for slot in args.slot:
            mesh = document['skins'][0]['attachments'][slot][slot]
            triangles = [mesh['triangles'][i:i+3] for i in range(0, len(mesh['triangles']), 3)]
            record = dict(time=time, slot=slot, before=metrics(setup[slot], before[slot], triangles))
            try:
                points = weighted_points(mesh, document['bones'], rest, current)
                record.update(after=metrics(setup[slot], points, triangles),
                              maximum_displacement_px=max(math.dist(a,b) for a,b in zip(before[slot],points)))
            except ValueError as error:
                record['unresolved'] = str(error)
            records.append(record)
    summary = {slot: dict(samples=sum(r['slot']==slot for r in records),
        unresolved=sum(r['slot']==slot and 'unresolved' in r for r in records),
        before_failed=sum(r['slot']==slot and (bool(r['before']['bad_triangles']) or r['before']['max_edge_stretch']>2) for r in records),
        after_failed=sum(r['slot']==slot and 'after' in r and (bool(r['after']['bad_triangles']) or r['after']['max_edge_stretch']>2) for r in records),
        worsened_inversions=sum(r['slot']==slot and 'after' in r and r['after']['inversions']>r['before']['inversions'] for r in records))
        for slot in args.slot}
    report = dict(source_artifact=scene.get('artifact_sha256'), source_sha256=canonical_sha256(document),
        source_path=str(args.scene.resolve()), records=records, summary=summary,
        authority='none', selected=False, runtime_status='not_evaluated',
        scope='source_rotation_keys_only_no_deform_bake_no_visual_acceptance')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
