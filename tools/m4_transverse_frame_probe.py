"""Isolate inherited leg shear in an exact candidate; never auto-adopt it."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from m4_squat_stage_players import stage
from m4_direction_stage_probe import load_stages
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample, matrices
from autospine_workbench.targets.character43.deform_addition import entries, local_delta
from autospine_workbench.targets.character43.transverse_frame import weighted_points
from autospine_workbench.targets.character43.pivot_frame_blend import weighted_points as pivot_points
from autospine_workbench.asset.planning.component_local_solver import metrics
from autospine_workbench.targets.spine43.continuous_pose import area


def run(source, output, slots, pivot_blend=False, capture_runtime=True):
    receipt=json.loads((source/'report.json').read_bytes())
    _,_,pose,_,_,parent,_=load_stages(receipt['source_job_id'])
    if parent!=receipt['source_candidate_sha256']:raise ValueError('transverse_source_mismatch')
    files=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    original=json.loads(files['skeleton.json']); bare=deepcopy(original); name='external-motion'
    for slot in slots:
        bare['animations'][name].get('attachments',{}).get('default',{}).pop(slot,None)
    document=deepcopy(bare); setup_doc=dict(original,animations={'setup':{}})
    setup=sample(setup_doc,'setup',0)[0]; rest=matrices(setup_doc,'setup',0)
    times=sorted(set(pose['times'])|{(a+b)/2 for a,b in zip(pose['times'],pose['times'][1:])})
    records=[]
    for slot in slots:
        mesh=original['skins'][0]['attachments'][slot][slot]; influences=entries(mesh)
        owners={original['bones'][i]['name'] for row in influences for i,w in row if w>0}
        selected=sorted(n for n in owners if n.startswith(('thigh_','calf_')))
        if not selected:raise ValueError('transverse_leg_selection')
        triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]; keys=[]
        for time in pose['times']:
            transforms=matrices(bare,name,time)
            if pivot_blend:
                points=pivot_points(mesh,original['bones'],rest,transforms,selected)
            else:
                points,_=weighted_points(mesh,original['bones'],rest,transforms,selected)
            before=sample(bare,name,time)[0][slot]
            keys.append(dict(time=time,vertices=local_delta(bare,influences,transforms,before,points)))
        document['animations'][name].setdefault('attachments',{}).setdefault('default',{}).setdefault(slot,{})[slot]={'deform':keys}
        for time in (0.,.966667,1.12):
            before=sample(bare,name,time)[0][slot]; after=sample(document,name,time)[0][slot]
            records.append(dict(slot=slot,time=time,before=metrics(setup[slot],before,triangles),
                after=metrics(setup[slot],after,triangles),maximum_displacement_px=max(map(math.dist,before,after)),
                inverted=[dict(triangle=i,bones=sorted({original['bones'][b]['name']
                    for v in tri for b,w in influences[v] if w>0}))
                    for i,tri in enumerate(triangles) if area(after,tri)*area(setup[slot],tri)<=0]))
    if document['animations'][name]['bones']!=original['animations'][name]['bones']:
        raise ValueError('transverse_bones_changed')
    output.mkdir(parents=True,exist_ok=False)
    (output/'probe.json').write_bytes(canonical_bytes(dict(profile='pivot-frame-probe-v1' if pivot_blend else 'transverse-frame-probe-v1',
        source=receipt['candidate_bundle_sha256'],selected=False,authority='none',records=records,
        baseline='selected_leg_deforms_removed_other_attachments_preserved',
        scope='source_frames_and_midpoints_diagnostic_not_full_parent_grid_or_contact_acceptance')))
    print(json.dumps([dict(slot=r['slot'],time=r['time'],before_inversions=r['before']['inversions'],
        after_inversions=r['after']['inversions'],maximum_displacement_px=r['maximum_displacement_px']) for r in records]),flush=True)
    if capture_runtime:stage(document,files,times,output/'trial',receipt['candidate_bundle_sha256'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--slots',nargs='+',required=True);p.add_argument('--pivot-blend',action='store_true')
    p.add_argument('--probe-only',action='store_true')
    a=p.parse_args();run(a.source,a.output,a.slots,a.pivot_blend,not a.probe_only)
