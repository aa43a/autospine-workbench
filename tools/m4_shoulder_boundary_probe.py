"""Evaluate existing source-supported shoulder constraints at selected motion poses."""
import argparse
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.shoulder_source import contexts
from autospine_workbench.targets.character43.shoulder_boundary import prepare, solve
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.asset.planning.component_local_solver import metrics


def run(artifact,output,times):
    if not times or len(times)>9 or any(not math.isfinite(t) or t<0 for t in times):
        raise ValueError('shoulder_probe_times_invalid')
    files=AnimatedStore(Path('workspace')).read(artifact)
    document,rows=contexts(files);animation='external-motion'
    duration=max(k['time'] for tracks in document['animations'][animation]['bones'].values()
                 for keys in tracks.values() for k in keys)
    if max(times)>duration:raise ValueError('shoulder_probe_time_outside_motion')
    report=dict(source_candidate_sha256=artifact,profile='source-supported-shoulder-pose-probe-v1',
                authority='none',selected=False,scope='selected_poses_not_full_motion_or_visual_acceptance',rows=[])
    for row in rows:
        context=prepare(row['points'],row['triangles'],row['contact'],row['root'],row['distal'])
        movable=set(context['pins']+context['free'])
        for time in sorted(set(times)):
            print(json.dumps(dict(slot=row['slot'],time=time,stage='solve')),flush=True)
            world=sample(document,animation,time)[0][row['slot']]
            corrected,evidence=solve(document,animation,time,row['points'],row['triangles'],world,context)
            fixed_error=max((math.dist(a,b) for i,(a,b) in enumerate(zip(world,corrected,strict=True))
                             if i not in movable),default=0)
            quality=evidence['geometry']
            passed=not quality['bad_triangles'] and quality['max_edge_stretch']<=2 and evidence['within_budget'] and fixed_error<=1e-7
            report['rows'].append(dict(slot=row['slot'],time=time,context=context,
                source_contact_pixels=len(row['contact']),before=metrics(row['points'],world,row['triangles']),
                after=evidence,fixed_error_px=fixed_error,passed=passed))
    report['passed']=bool(report['rows']) and all(r['passed'] for r in report['rows'])
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as f:f.write(canonical_bytes(report))
    print(json.dumps(dict(passed=report['passed'],rows=[dict(slot=r['slot'],time=r['time'],passed=r['passed'],
        inversions=r['after']['geometry']['inversions'],stretch=r['after']['geometry']['max_edge_stretch'],
        displacement=r['after']['displacement_from_original_px'],budget=r['context']['budget_px']) for r in report['rows']])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact');p.add_argument('output',type=Path)
    p.add_argument('--time',type=float,action='append',required=True)
    a=p.parse_args();run(a.artifact,a.output,a.time)
