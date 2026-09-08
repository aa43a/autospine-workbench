"""Exact alpha-width evidence to stepped 4.3 combined-pose inspection."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from ..asset.joints.combined_corrective import analyze,POSES
from ..resolved_project import canonical_sha256
from ..targets.spine43.ownership_preview import build_preview
from .artifacts import read_input,read_report
from .ownership_atlas_cli import compile_report as atlas_source
from .distal_width_cli import compile_report as width_source
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .elbow_target_cli import archive,export


def compile_report(state,manifest,atlas_sha,width_sha,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],atlas_sha)
    atlas,_,pages=atlas_source(state,manifest,saved['source_partitions_sha256'],workspace)
    if canonical_sha256(atlas)!=atlas_sha:raise ValueError('combined_atlas_mismatch')
    width=read_mesh_report(state,manifest['dataset_id'],width_sha)
    expected,_=width_source(state,manifest,width['source_mesh_sha256'],workspace)
    if canonical_sha256(expected)!=width_sha:raise ValueError('combined_width_mismatch')
    shared=read_mesh_report(state,manifest['dataset_id'],atlas['source_partitions_sha256'])
    if shared['source_mesh_sha256']!=width['source_mesh_sha256'] or atlas['source_skeleton_sha256']!=width['source_skeleton_sha256']:
        raise ValueError('combined_source_chain_mismatch')
    skeleton=read_report(state,manifest['dataset_id'],'assisted-skeleton-candidates',atlas['source_skeleton_sha256'])
    bones={b['id']:b for b in skeleton['bones']};sources={r['layer_id']:r for r in width['layers']};derived=deepcopy(atlas);results=[]
    for layer in derived['layers']:
        for part in layer['partitions']:
            if len(part['bone_ids'])!=3:continue
            trial=next(t for t in sources[part['id']]['trials'] if t['policy']['factor']==4)
            part['geometry']['weights']=deepcopy(trial['weights'])
            row={**part['geometry'],'layer_id':part['id'],'bone_ids':part['bone_ids']}
            results.append(analyze(row,[bones[b] for b in part['bone_ids']]))
    scope,files=build_preview(derived,skeleton,pages);doc=json.loads(files['skeleton.json']);tracks={};deforms={}
    for layer in derived['layers']:
        for part in layer['partitions']:
            if len(part['bone_ids'])!=3:continue
            result=next(r for r in results if r['layer_id']==part['id'])
            for index,axis in ((1,0),(2,1)):
                tracks[part['bone_ids'][index]]={'rotate':[{'time':i*.5,'value':-p[axis],'curve':'stepped'} for i,p in enumerate(POSES)]}
            keys=[{'time':i*.5,'curve':'stepped','vertices':[v for moves in p['offsets'] for x,y in moves for v in (x,-y)]} for i,p in enumerate(result['poses'])]
            deforms[part['id']]={part['id']:{'deform':keys}}
    doc['animations']={'combined-pose-inspection':{'bones':tracks,'attachments':{'default':deforms}}}
    encode=lambda d:json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    files['skeleton.json']=encode(doc);editor=deepcopy(doc);editor['skeleton']['images']='./images/';files['editor/skeleton.json']=encode(editor)
    scope.update(schema='autospine.combined-corrective-preview/v1',profile='distal-then-main-stepped-v1',
        source_original_atlas_sha256=atlas_sha,source_width_sha256=width_sha,animation='discrete_combined_corrective_inspection',
        width_factor=4,continuous_motion_status='not_evaluated',
        results=[{'layer_id':r['layer_id'],'status':r['status'],'poses':[{k:v for k,v in p.items() if k!='offsets'} for p in r['poses']]} for r in results])
    scope['files']={k:hashlib.sha256(v).hexdigest() for k,v in files.items()}
    files['preview-manifest.json']=encode(scope);data=archive(files)
    if len(data)>32<<20:raise ValueError('combined_archive_too_large')
    scope['zip_sha256']=hashlib.sha256(data).hexdigest()
    return scope,data,files


def read_combined(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    expected,_,_=compile_report(state,manifest,saved['source_original_atlas_sha256'],saved['source_width_sha256'],workspace)
    if canonical_sha256(expected)!=canonical_sha256(saved):raise ValueError('combined_replay_mismatch')
    return saved


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state-root',type=Path,default=Path(__file__).resolve().parents[3]/'workspace')
    for name in ('manifest','workspace','atlas','width','directory','output','zip'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        manifest=read_input(args.manifest);scope,data,files=compile_report(args.state_root,manifest,canonical_sha256(read_input(args.atlas)),canonical_sha256(read_input(args.width)),args.workspace)
        digest=publish_mesh_report(args.state_root,manifest['dataset_id'],scope);export_mesh(args.output,scope);export(args.zip,data)
        for name,raw in files.items():export(args.directory/name,raw)
        print(json.dumps({'status':'written','artifact_sha256':digest,'results':[{k:r[k] for k in ('layer_id','status')} for r in scope['results']]}));return 0
    except (ValueError,TypeError,KeyError,OSError,RuntimeError):
        print(json.dumps({'status':'blocked','reason_code':'combined_preview_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
