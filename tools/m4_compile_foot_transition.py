"""Bake explicit diagnostic foot poses; interpolation still requires validation."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import struct
from pathlib import Path
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.deform_addition import entries,local_delta,add
from autospine_workbench.targets.character43.attachment_exit_pose import outgoing_document


def runtime_keys(keys):
    result=[];merged=0;error=0.
    for key in keys:
        time=struct.unpack('f',struct.pack('f',key['time']))[0]
        canonical=dict(key,time=time)
        if result and time==result[-1]['time']:
            delta=max(abs(a-b) for a,b in zip(key['vertices'],result[-1]['vertices'],strict=True))
            if delta>1e-5:raise ValueError('foot_bake_conflicting_float32_keys')
            error=max(error,delta);merged+=1;result[-1]=canonical
        else:result.append(canonical)
    return result,dict(merged_keys=merged,maximum_local_delta=error)


def run(source_path,shoe_path,report_path,output):
    source=json.loads(source_path.read_bytes());shoe=json.loads(shoe_path.read_bytes())
    original=source['skeleton'];result=deepcopy(shoe['skeleton'])
    raw=report_path.read_bytes();report=json.loads(raw)
    if report['source_sha256']!=canonical_sha256(original):raise ValueError('foot_bake_source_changed')
    # Shoe helper experiment must preserve every original leg and original bone.
    if result['bones'][:len(original['bones'])]!=original['bones']:
        raise ValueError('foot_bake_original_bones_changed')
    name=report['animation'];motion=result['animations'][name]
    if any(motion.get('bones',{}).get(b['name'])!=original['animations'][name].get('bones',{}).get(b['name'])
           for b in original['bones']):raise ValueError('foot_bake_original_motion_changed')
    rows={}
    for row in report['records']:
        if not row['transition_passed']:raise ValueError('foot_bake_failed_pose')
        rows.setdefault(row['time'],[]).append(row)
    if sorted(rows)!=report['times']:raise ValueError('foot_bake_time_inventory')
    corrections={};counts={}
    for time,records in sorted(rows.items()):
        before=sample_active(original,name,time);transforms=matrices(result,name,time)
        for row in records:
            slot,attachment=row['slot'],row['attachment'];key=(slot,attachment)
            pose=before
            if row.get('guard')=='attachment_exit':
                pinned=outgoing_document(original,name,slot,attachment,time)
                pose=sample_active(pinned,name,time)
            elif row.get('guard') is not None:raise ValueError('foot_bake_unknown_guard')
            if pose['attachments'][slot]!=attachment:raise ValueError('foot_bake_attachment_changed')
            mesh=original['skins'][0]['attachments'][slot][attachment]
            if result['skins'][0]['attachments'][slot][attachment]!=mesh:raise ValueError('foot_bake_mesh_changed')
            influences=entries(mesh)
            offsets=local_delta(result,influences,transforms,pose['vertices'][slot],row['points'])
            corrections.setdefault(key,[]).append(dict(time=time,vertices=offsets));counts[key]=len(offsets)
    key_reports=[]
    for (slot,attachment),keys in corrections.items():
        channels=motion.setdefault('attachments',{}).setdefault('default',{}).setdefault(slot,{}).setdefault(attachment,{})
        original_keys,_=runtime_keys(channels.get('deform',[]))
        channels['deform'],key_report=runtime_keys(add(original_keys,keys,counts[(slot,attachment)]))
        key_reports.append(dict(slot=slot,attachment=attachment,**key_report))
    shoe['skeleton']=result;shoe['artifact']=None
    output.mkdir(parents=True,exist_ok=False)
    (output/'candidate.json').write_text(json.dumps(shoe),encoding='utf-8')
    receipt=dict(source_sha256=canonical_sha256(original),shoe_sha256=canonical_sha256(json.loads(shoe_path.read_bytes())['skeleton']),
        pose_report_sha256=sha256(raw).hexdigest(),output_sha256=canonical_sha256(result),
        authority='none',selected=False,scope='baked_pose_candidate_interpolation_geometry_runtime_and_material_contact_unverified',
        times=report['times'],float32_keys=key_reports,
        attachments=[dict(slot=s,attachment=a,keys=len(k)) for (s,a),k in corrections.items()])
    (output/'report.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='times'}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','shoe','poses','output'):p.add_argument(name,type=Path)
    a=p.parse_args();run(a.source,a.shoe,a.poses,a.output)
