"""Compare an independent observed hand region with a single boundary transport band."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.partition_rebind import apply
from autospine_workbench.targets.character43.partition_boundary_blend import blend
from m4_squat_stage_players import stage,shared_camera


def run(parent,hand,selected,times):
    doc=deepcopy(parent);name='external-motion';helper='observed_hand_l';slot='layer-004'
    if any(b['name']==helper for b in doc['bones']):raise ValueError('helper_already_exists')
    bone=deepcopy(next(b for b in doc['bones'] if b['name']=='hand_l'));bone['name']=helper;doc['bones'].append(bone)
    doc['animations'][name]['bones'][helper]=deepcopy(hand['animations'][name]['bones']['hand_l'])
    from autospine_workbench.targets.character43.affine_pose import sample
    rest=deepcopy(doc);rest['animations']={name:{}};setup=sample(rest,name,0)[0][slot]
    mesh=doc['skins'][0]['attachments'][slot][slot]
    plan=dict(slot=slot,animation=name,partition=dict(mesh_sha256=canonical_sha256(mesh),triangles=selected,bone=helper))
    rigid,points,partition=apply(doc,plan,setup)
    transported,report=blend(rigid,name,slot,partition,points,times)
    return rigid,transported,dict(partition=partition,transport=report,helper=helper,authority='none',selected=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args()
    parent_id='229a27bd7b4daa90b0c306bcf2e42d0fb6823b285c97f914200bce73a47e23a7'
    files=AnimatedStore(Path('workspace')).read(parent_id);parent=json.loads(files['skeleton.json'])
    handroot=Path('tmp/kimodo-hand-candidate-v1/hand');receipt=json.loads((handroot/'report.json').read_bytes())
    handfiles=AnimatedStore(handroot/'isolated-store').read(receipt['candidate_bundle_sha256'])
    hand=json.loads(handfiles['skeleton.json'])
    selected=json.loads(Path('tmp/partition-execution-v1/submission.json').read_bytes())['draft_body']['partition']['triangles']
    times=[0.,2.,3.966667];rigid,transported,report=run(parent,hand,selected,times)
    a.output.mkdir(parents=True,exist_ok=False)
    report.update(parent=parent_id,hand_candidate=receipt['candidate_bundle_sha256'],times=times)
    (a.output/'probe.json').write_bytes(canonical_bytes(report))
    stage(rigid,files,times,a.output/'rigid',parent_id)
    stage(transported,files,times,a.output/'transported',parent_id)
    shared_camera(a.output,('rigid','transported'))
    print(json.dumps(report['transport']))
