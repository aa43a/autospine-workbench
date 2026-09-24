"""Add outgoing-attachment boundary constraints to an existing pose experiment."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.attachment_exit_pose import exits,outgoing_document
from autospine_workbench.targets.character43.foot_material_transition import solve
from autospine_workbench.targets.character43.deform_addition import entries


def run(source_path,adjusted_path,poses_path,output):
    source=json.loads(source_path.read_bytes())['skeleton'];adjusted=json.loads(adjusted_path.read_bytes())['skeleton']
    raw=poses_path.read_bytes();report=json.loads(raw);animation=report['animation']
    if report['source_sha256']!=canonical_sha256(source) or report['adjusted_sha256']!=canonical_sha256(adjusted):
        raise ValueError('foot_guard_source_changed')
    names=[b['name'] for b in source['bones']];guards=[]
    for slot in sorted({r['slot'] for r in report['records']}):
        for boundary in exits(source,animation,slot):
            time=boundary['time'];attachment=boundary['attachment']
            if any(r['time']==time and r['slot']==slot and r['attachment']==attachment for r in report['records']):
                continue
            old=sample_active(outgoing_document(source,animation,slot,attachment,time),animation,time)
            new=sample_active(outgoing_document(adjusted,animation,slot,attachment,time),animation,time)
            mesh=source['skins'][0]['attachments'][slot][attachment]
            bones={names[i] for row in entries(mesh) for i,w in row if w>0}
            sides=[side for side in ('l','r') if {'foot_'+side,'calf_'+side}<=bones]
            if len(sides)!=1:raise ValueError('foot_guard_ambiguous_side')
            side=sides[0]
            points,evidence=solve(mesh,old['setup_vertices'][slot],old['vertices'][slot],new['vertices'][slot],
                names.index('foot_'+side),names.index('calf_'+side),refine_transition=True)
            guards.append(dict(time=time,slot=slot,attachment=attachment,guard='attachment_exit',points=points,**evidence))
    report['records'].extend(guards)
    report['times']=sorted({r['time'] for r in report['records']})
    report['parent_pose_report_sha256']=sha256(raw).hexdigest()
    with output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps([dict(slot=r['slot'],attachment=r['attachment'],time=r['time'],passed=r['transition_passed']) for r in guards]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','adjusted','poses','output'):p.add_argument(name,type=Path)
    a=p.parse_args();run(a.source,a.adjusted,a.poses,a.output)
