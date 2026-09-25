"""Recompute only leg corrective tracks after final endpoint solving; no adoption."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.projected_area_adaptive import build
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.spine43.continuous_pose import area


def run(folder,output,selected_slot=None,dual_floor=False):
    receipt=json.loads((folder/'report.json').read_bytes())
    files=AnimatedStore(folder/'isolated-store').read(receipt['candidate_bundle_sha256'])
    doc=json.loads(files['skeleton.json']);setup=json.loads(files['rig-setup-reference.json'])
    if setup['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest():
        raise ValueError('final_leg_probe_setup_identity')
    qa=json.loads(files['deformation.json']);slots=[]
    for row in qa['records']:
        if row['passed']:continue
        mesh=doc['skins'][0]['attachments'][row['slot']][row['slot']]
        data=mesh['vertices'];i=0;used=set()
        while i<len(data):
            n=data[i];i+=1
            for j in range(n):
                if data[i+j*4+3]>0:used.add(doc['bones'][data[i+j*4]]['name'])
            i+=4*n
        if used and used<={'thigh_l','calf_l','foot_l','thigh_r','calf_r','foot_r'}:slots.append(row['slot'])
    if selected_slot is not None:
        if selected_slot not in slots:raise ValueError('final_leg_probe_slot_not_failed_leg')
        slots=[selected_slot]
    if not slots:raise ValueError('final_leg_probe_no_failed_legs')
    isolated=deepcopy(doc);name='external-motion'
    isolated['skins'][0]['attachments']={s:isolated['skins'][0]['attachments'][s] for s in slots}
    isolated['animations'][name].pop('attachments',None)
    fixed,correction=build(isolated,name,setup['vertices'],temporal=True,dual_floor=dual_floor,
                           progress=lambda r:print(r['stage'],flush=True) if r['stage']=='refinement_round' else None)
    candidate=deepcopy(doc);tracks=candidate['animations'][name].setdefault('attachments',{}).setdefault('default',{})
    replacement=fixed['animations'][name].get('attachments',{}).get('default',{})
    for s in slots:
        tracks.pop(s,None)
        if s in replacement:tracks[s]=replacement[s]
    from autospine_workbench.automation.motion_target_pose import final_times
    from autospine_workbench.targets.character43.numeric_reference import read
    numeric=read(files);times=final_times(candidate,name,[r['time'] for r in numeric['animations'][name]])
    rows=[]
    for s in slots:
        flat=doc['skins'][0]['attachments'][s][s]['triangles'];tri=[flat[i:i+3] for i in range(0,len(flat),3)]
        base=[area(setup['vertices'][s],t) for t in tri]
        values=[];before=[]
        for time in times:
            points=sample(candidate,name,time)[0][s]
            values.extend(area(points,t)/a for t,a in zip(tri,base))
            prior=sample(doc,name,time)[0][s]
            before.extend(area(prior,t)/a for t,a in zip(tri,base))
        rows.append(dict(slot=s,min_area_ratio=min(values),max_area_ratio=max(values),inversions=sum(v<=0 for v in values),
                         before_min_area_ratio=min(before),before_max_area_ratio=max(before)))
    # Bone tracks, all nonselected deform tracks and setup assets are unchanged.
    check=deepcopy(candidate)
    check['animations'][name]['attachments']=deepcopy(doc['animations'][name].get('attachments',{}))
    if check!=doc:raise ValueError('final_leg_probe_unrelated_mutation')
    output.mkdir(parents=True,exist_ok=False)
    (output/'skeleton.json').write_bytes(canonical_bytes(candidate))
    (output/'correction.json').write_bytes(canonical_bytes(correction))
    result=dict(source_candidate=receipt['candidate_bundle_sha256'],rows=rows,samples=len(times),
                skeleton_sha256=sha256(canonical_bytes(candidate)).hexdigest(),authority='none',selected=False,
                scope='area_only_not_full_geometry_runtime_or_visual_acceptance')
    (output/'report.json').write_bytes(canonical_bytes(result));print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--slot');p.add_argument('--dual-floor',action='store_true')
    a=p.parse_args();run(a.folder,a.output,a.slot,a.dual_floor)
