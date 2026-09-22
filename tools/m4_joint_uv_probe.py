"""Test a local source-UV hypothesis on key poses, never adopt the result."""
import argparse
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from PIL import Image
import numpy as np
from m4_pose_material_review import transfer
from m4_squat_stage_players import stage
from m4_experiment_player_export import export
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.targets.character43.joint_uv_band import contract


def finish(source,output):
    report=json.loads((output/'probe.json').read_bytes());folder=output/'uv'
    receipt=json.loads((folder/'report.json').read_bytes())
    runtime=json.loads((folder/'runtime/report.json').read_bytes())
    if runtime['bundle_sha256']!=receipt['candidate_bundle_sha256'] or runtime['passed'] is not True:
        raise ValueError('uv_probe_runtime_failed')
    log=(folder/'capture-1.log').read_text(encoding='utf-8')
    if 'character_setup_source_transform_unsupported' not in log:
        raise ValueError('uv_probe_unexpected_setup_result')
    if not (folder/'runtime/player-assets').exists():export(folder)
    source_runtime=json.loads((source/'runtime/report.json').read_bytes())
    if source_runtime['bundle_sha256']!=report['parent']:raise ValueError('uv_probe_camera_identity')
    scene_path=folder/'runtime/player-assets/scene.json';scene=json.loads(scene_path.read_bytes())
    scene['info']=source_runtime['info'];scene_path.write_text(json.dumps(scene),encoding='utf-8')
    report.update(candidate=receipt['candidate_bundle_sha256'],runtime_numeric_passed=True,
                  setup_check='unsupported_non_affine_uv',pipeline_passed=False,shared_camera=scene['info'])
    (output/'probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


def run(source,output):
    receipt=json.loads((source/'report.json').read_bytes());parent=receipt['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(parent);doc=json.loads(files['skeleton.json'])
    original=deepcopy(doc);setup=json.loads(files['rig-setup-reference.json'])['vertices']
    rest=matrices(dict(doc,animations={'setup':{}}),'setup',0);records=[]
    for slot in ('layer-003','layer-004'):
        mesh=doc['skins'][0]['attachments'][slot][slot]
        names={doc['bones'][i]['name'] for row in entries(mesh) for i,w in row if w>0}
        joints=[n for n in names if n.startswith('calf_')]
        if len(joints)!=1:raise ValueError('joint_uv_unique_knee')
        joint=joints[0];upper=next(b['parent'] for b in doc['bones'] if b['name']==joint)
        center=np.array(rest[joint][4:]);root=np.array(rest[upper][4:])
        # Two internal points define the source-space limb axis; no screenshot coordinates.
        queries=[center,center+(root-center)*.2]
        source_uv,covered=transfer(setup[slot],np.asarray(mesh['uvs']).reshape(-1,2),mesh['triangles'],queries)
        if not covered.all():raise ValueError('joint_uv_anchor_uncovered')
        size=Image.open(BytesIO(files['images/'+mesh.get('path',slot)+'.png'])).size
        source_px=source_uv*np.asarray(size);direction=source_px[1]-source_px[0]
        radius=float(np.linalg.norm(direction)*2.5)
        mesh['uvs'],detail=contract(mesh['uvs'],mesh['triangles'],size,source_px[0],direction,radius)
        records.append(dict(slot=slot,joint=joint,pivot=source_px[0].tolist(),**detail))
    if doc['animations']!=original['animations'] or doc['bones']!=original['bones']:
        raise ValueError('joint_uv_motion_changed')
    output.mkdir(parents=True,exist_ok=False)
    report=dict(parent=parent,records=records,authority='none',selected=False,
                limitation='static UV trial changes setup; not a production animation or an accepted repair')
    (output/'probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        digest=stage(doc,files,[0,.8,.9,1.2,1.866667],output/'uv',parent)
    except ValueError as error:
        if str(error)!='character_runtime_capture_failed':raise
        finish(source,output);return
    report['candidate']=digest
    (output/'probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    if args.resume:finish(args.source,args.output)
    else:run(args.source,args.output)
