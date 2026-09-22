"""Same-pose local ARAP comparison on the target-constrained character."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from statistics import median
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample, matrices
from autospine_workbench.targets.character43.local_arap import solve
from autospine_workbench.targets.character43.deform_addition import entries, local_delta
from autospine_workbench.asset.planning.component_local_solver import metrics
from m4_squat_stage_players import stage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--hard-area', action='store_true')
    parser.add_argument('--full-clip', action='store_true')
    args = parser.parse_args()
    parent = json.loads((args.source/'report.json').read_bytes())['candidate_bundle_sha256']
    files = AnimatedStore(args.source/'isolated-store').read(parent)
    document = json.loads(files['skeleton.json'])
    result = deepcopy(document)
    rest = sample(dict(document, animations={'setup': {}}), 'setup', 0)[0]
    times = [0., .933333, 1.866667]
    if args.full_clip:
        times = sorted({key['time'] for row in document['animations']['external-motion']['bones'].values()
                        for key in row.get('rotate', [])})
        if len(times) < 2: raise ValueError('arap_probe_motion_keys_missing')
    rows = []
    for slot in ('layer-003', 'layer-004'):
        mesh = document['skins'][0]['attachments'][slot][slot]
        triangles = [mesh['triangles'][i:i+3] for i in range(0, len(mesh['triangles']), 3)]
        edges = {tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])}
        budget = median(math.dist(rest[slot][a], rest[slot][b]) for a,b in edges)
        owners = entries(mesh)
        corrections = []
        for time in times:
            points = sample(document, 'external-motion', time)[0][slot]
            before = metrics(rest[slot], points, triangles)
            bad = {v for i in before['bad_triangles'] for v in triangles[i]}
            free = sorted({v for t in triangles if any(v in bad for v in t) for v in t})
            after, evidence = solve(rest[slot], points, triangles, free, budget)
            if args.hard_area and free:
                from autospine_workbench.targets.character43.boundary_shape_feasible import refine
                print(json.dumps(dict(stage='hard_area',slot=slot,time=time,free_vertices=len(free))),flush=True)
                regions = [dict(vertex=i, center=points[i], inverse=[[1.,0.],[0.,1.]], radius=budget) for i in free]
                after, hard = refine(rest[slot], triangles, points, free, points, after, budget, regions=regions)
                evidence['hard_area'] = hard
            rows.append(dict(slot=slot, time=time, budget=budget, free_vertices=len(free),
                before=before, after=metrics(rest[slot], after, triangles), solver=evidence))
            corrections.append(dict(time=time, vertices=local_delta(document, owners,
                matrices(document, 'external-motion', time), points, after)))
        target = result['animations']['external-motion'].setdefault('attachments', {}).setdefault('default', {}).setdefault(slot, {}).setdefault(slot, {})
        if target.get('deform'): raise ValueError('arap_probe_existing_deform')
        target['deform'] = corrections
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'probe.json').write_text(json.dumps(dict(parent=parent, authority='none', selected=False,
        hard_area=args.hard_area, full_clip=args.full_clip, solved_times=times,
        scope='source_keys_with_midpoint_checks_not_visual_acceptance' if args.full_clip else
              'three_key_poses_not_interpolation_or_visual_acceptance', records=rows), indent=2), encoding='utf-8')
    capture_times = sorted(set(times) | {(a+b)/2 for a,b in zip(times,times[1:])}) if args.full_clip else times
    stage(result, files, capture_times, args.output/'candidate', parent)
    print(json.dumps([dict(slot=r['slot'], time=r['time'], before=r['before']['inversions'],
        after=r['after']['inversions'], bad_after=len(r['after']['bad_triangles'])) for r in rows]))


if __name__ == '__main__': main()
