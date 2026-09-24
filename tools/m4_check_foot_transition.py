"""Check baked foot transition keys and midpoints; keep whole-leg failures visible."""
import argparse
import json
from pathlib import Path
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.pose_geometry_patch import _times
from autospine_workbench.asset.planning.component_local_solver import metrics
from autospine_workbench.resolved_project import canonical_sha256


def run(folder):
    d=json.loads((folder/'candidate.json').read_bytes())['skeleton'];animation='external-motion'
    keys=sorted(set([0.,*_times(d['animations'][animation])]))
    times=sorted(set(keys+[(a+b)/2 for a,b in zip(keys,keys[1:])]))
    frames=[];rows=[];names=[b['name'] for b in d['bones']]
    for time in times:
        frame=sample_active(d,animation,time)
        frames.append(dict(time=time,attachments=frame['attachments'],vertices=frame['vertices']))
        for slot,name in frame['attachments'].items():
            if name is None:continue
            mesh=d['skins'][0]['attachments'][slot][name]
            influences=[{names[i] for i,w in row if w>0} for row in entries(mesh)]
            bones=set().union(*influences)
            if not any({'foot_'+side,'calf_'+side}<=bones for side in ('l','r')):continue
            moving={i for i,row in enumerate(influences) if row&{'foot_l','foot_r'}}
            tri=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
            local=[t for t in tri if set(t)&moving]
            points=frame['vertices'][slot];setup=frame['setup_vertices'][slot]
            quality=metrics(setup,points,local);whole=metrics(setup,points,tri)
            rows.append(dict(time=time,slot=slot,attachment=name,transition=quality,
                transition_passed=not quality['bad_triangles'] and quality['max_edge_stretch']<=2,
                whole_attachment=whole))
    report=dict(document_sha256=canonical_sha256(d),authority='none',selected=False,
        scope='baked_keys_and_midpoints_cpu_geometry_not_visual_acceptance',
        sample_count=len(times),records=rows)
    for filename,value in [('interpolation.json',report),('active-reference.json',dict(animation=animation,frames=frames))]:
        with (folder/filename).open('x',encoding='utf-8') as f:json.dump(value,f)
    failures=[dict(time=r['time'],slot=r['slot'],**r['transition']) for r in rows if not r['transition_passed']]
    print(json.dumps(dict(samples=len(times),records=len(rows),transition_failures=len(failures),first_failures=failures[:4],
        whole_leg_failures=sum(bool(r['whole_attachment']['bad_triangles']) or r['whole_attachment']['max_edge_stretch']>2 for r in rows))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path)
    run(p.parse_args().folder)
