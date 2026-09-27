"""Locate fixed and movable area counterexamples on an audited full time grid."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.spine43.continuous_pose import area
from m4_transverse_batch_audit import audit


def classify(setup, triangles, influences, frames):
    free = [sum(w > 0 for _, w in row) > 1 for row in influences]
    bases = [area(setup, tri) for tri in triangles]
    rows = [dict(triangle=i, vertices=tri, fixed=all(not free[v] for v in tri),
                 drivers=sorted({bone for v in tri for bone,w in influences[v] if w > 0}),
                 minimum_area_ratio=float('inf'), time=None) for i,tri in enumerate(triangles)]
    for time, points in frames:
        for row, base in zip(rows, bases):
            ratio = area(points, row['vertices'])/base
            if ratio < row['minimum_area_ratio']:
                row.update(minimum_area_ratio=ratio, time=time)
    return [row for row in rows if row['minimum_area_ratio'] < .5]


def run(state_root, probe, root, output):
    coverage = audit(state_root, probe, root)
    manifest = json.loads((root/'report.json').read_bytes())
    slot = json.loads((probe/'report.json').read_bytes())['slot']
    parent = AnimatedStore(state_root).read(manifest['parent_artifact_sha256'])
    original = json.loads(parent['skeleton.json']); setup = json.loads(parent['rig-setup-reference.json'])['vertices'][slot]
    mesh = original['skins'][0]['attachments'][slot][slot]
    triangles = [mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    def frames():
        for index, row in enumerate(manifest['rows']):
            files = AnimatedStore(root/row['folder']/'isolated-store').read(row['candidate_bundle_sha256'])
            sampled = read(files)['animations']['external-motion']
            for frame in sampled[1:] if index else sampled:
                yield frame['time'], frame['vertices'][slot]
    failures = classify(setup, triangles, entries(mesh), frames())
    poses = {}
    for row in failures:
        time = row['time']
        if time not in poses:poses[time] = sample(original,'external-motion',time)[0][slot]
        row['parent_area_ratio_at_same_time'] = area(poses[time],row['vertices'])/area(setup,row['vertices'])
        row['regressed'] = row['minimum_area_ratio'] < row['parent_area_ratio_at_same_time']-1e-6
        row['setup_points'] = [setup[v] for v in row['vertices']]
    report = dict(skeleton_sha256=manifest['skeleton_sha256'],parent_artifact_sha256=manifest['parent_artifact_sha256'],
        batch_report_sha256=sha256((root/'report.json').read_bytes()).hexdigest(),slot=slot,frames=coverage['frames'],
        failing_triangles=len(failures), fixed_failing_triangles=sum(r['fixed'] for r in failures),
        single_bone_fixed_failures=sum(r['fixed'] and len(r['drivers'])==1 for r in failures),
        movable_regressions=sum(not r['fixed'] and r['regressed'] for r in failures),
        failures=failures, authority='none', selected=False,
        scope='minimum_area_counterexamples_not_complete_feasibility_or_causal_proof')
    with output.open('xb') as handle:handle.write(canonical_bytes(report))
    print(json.dumps({k:v for k,v in report.items() if k!='failures'}),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('state_root','probe','root','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();run(args.state_root,args.probe,args.root,args.output)
