"""Evaluate explicit distal material coupling at supplied diagnostic poses."""
import argparse
import json
import struct
from pathlib import Path
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.foot_material_transition import solve
from autospine_workbench.targets.character43.isolated_foot_surface import build
from autospine_workbench.targets.character43.pose_geometry_patch import _times


def run(source,adjusted,output,times,animation,hard=False,source_keys=False):
    original=json.loads(source.read_bytes())['skeleton']
    corrected=json.loads(adjusted.read_bytes())['skeleton']
    names=[b['name'] for b in original['bones']]
    setup=sample_active(original,animation,0)
    bindings={}
    for slot,name in setup['attachments'].items():
        if name is None:continue
        mesh=original['skins'][0]['attachments'][slot][name]
        bones={names[i] for row in entries(mesh) for i,w in row if w>0}
        if bones in ({'foot_l'},{'foot_r'}):bindings[slot]=next(iter(bones))
    # Also validates that the adjusted input changes only foot channels.
    build(original,corrected,animation,bindings)
    duration=max(_times(original['animations'][animation]))
    if source_keys:
        runtime_time=lambda t:struct.unpack('f',struct.pack('f',t))[0]
        keys=sorted({runtime_time(t) for t in [0.,*_times(original['animations'][animation])]})
        times=sorted(set(keys)|{runtime_time((a+b)/2) for a,b in zip(keys,keys[1:])})
        duration=max(duration,keys[-1])
    if not times or any(not 0<=t<=duration for t in times):raise ValueError('foot_probe_times')
    rows=[]
    for time in sorted(set(times)):
        before=sample_active(original,animation,time);after=sample_active(corrected,animation,time)
        if before['attachments']!=after['attachments']:raise ValueError('foot_probe_identity_changed')
        for slot,name in before['attachments'].items():
            if name is None:continue
            mesh=original['skins'][0]['attachments'][slot][name]
            bones={names[i] for row in entries(mesh) for i,w in row if w>0}
            for side in ('l','r'):
                foot,calf='foot_'+side,'calf_'+side
                if not {foot,calf}<=bones:continue
                points,report=solve(mesh,before['setup_vertices'][slot],before['vertices'][slot],
                    after['vertices'][slot],names.index(foot),names.index(calf),refine_transition=hard)
                rows.append(dict(time=time,slot=slot,attachment=name,points=points,**report))
    report=dict(source_sha256=canonical_sha256(original),adjusted_sha256=canonical_sha256(corrected),
        animation=animation,times=sorted(set(times)),authority='none',selected=False,records=rows)
    with output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps(dict(samples=len(set(times)),records=len(rows),passed=sum(r['transition_passed'] for r in rows),
        failures=[dict(time=r['time'],slot=r['slot'],constraints=r['constraints']['status'],
            inversions=r['after']['inversions'],stretch=r['after']['max_edge_stretch'])
            for r in rows if not r['transition_passed']])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','adjusted','output'):p.add_argument(name,type=Path)
    sampling=p.add_mutually_exclusive_group(required=True)
    sampling.add_argument('--times',type=float,nargs='+')
    sampling.add_argument('--source-keys',action='store_true')
    p.add_argument('--animation',default='external-motion')
    p.add_argument('--hard',action='store_true')
    a=p.parse_args();run(a.source,a.adjusted,a.output,a.times,a.animation,a.hard,a.source_keys)
