"""Exact alpha-seam candidate to CPU raster/conflict comparison."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.seam_raster import analyze as raster
from ..targets.spine43.seam_conflicts import analyze as conflicts
from .alpha_seam_cli import compile_report as alpha_source
from .artifacts import read_input
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .elbow_target_cli import export
from .seam_raster_view import render


def compile_report(state,manifest,digest,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.alpha-seam-preview/v1':raise ValueError('raster_source_schema_invalid')
    source,_,files=alpha_source(state,manifest,saved['source_continuous_sha256'],workspace)
    if canonical_sha256(source)!=digest:raise ValueError('raster_source_replay_mismatch')
    baseline=read_mesh_report(state,manifest['dataset_id'],source['source_continuous_sha256'])
    doc=json.loads(files['skeleton.json']);before=deepcopy(doc);animation=before['animations'].pop('alpha-seam-inspection')
    for constraint in source['alpha_seam_qa']['constraints']:animation['attachments']['default'].pop(constraint['follower'])
    before['animations']['continuous-corrective-inspection']=animation
    raw=json.dumps(before,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if hashlib.sha256(raw).hexdigest()!=baseline['files']['skeleton.json']:raise ValueError('raster_baseline_reconstruction_mismatch')
    qa=source['alpha_seam_qa'];old,old_images=raster(before,files,qa['before']);new,new_images=raster(doc,files,qa['after'])
    images={**{'before/'+k:v for k,v in old_images.items()},**{'after/'+k:v for k,v in new_images.items()}}
    result={'schema':'autospine.seam-raster-diagnostic/v1','profile':'alpha-corridor-comparison-v1',
        'source_alpha_sha256':digest,'source_continuous_sha256':source['source_continuous_sha256'],
        'before':old,'after':new,'conflicts':conflicts(before,qa['before']),
        'authority':'none','production_authorized':False,'status':'needs_review',
        'runtime_raster_status':'not_evaluated','files':{k:hashlib.sha256(v).hexdigest() for k,v in images.items()}}
    return result,images


def read_raster(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    expected,_=compile_report(state,manifest,saved['source_alpha_sha256'],workspace)
    if canonical_sha256(expected)!=canonical_sha256(saved):raise ValueError('raster_replay_mismatch')
    return saved


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-root',type=Path,default=Path(__file__).resolve().parents[3]/'workspace')
    for name in ('manifest','workspace','source','directory','output'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args(argv)
    try:
        manifest=read_input(args.manifest);result,images=compile_report(args.state_root,manifest,canonical_sha256(read_input(args.source)),args.workspace)
        digest=publish_mesh_report(args.state_root,manifest['dataset_id'],result);export_mesh(args.output,result)
        for name,raw in images.items():export(args.directory/name,raw)
        export(args.directory/'index.html',render(result).encode('utf-8'))
        print(json.dumps({'status':'written','artifact_sha256':digest,'relations':len(result['after']['relations'])}));return 0
    except (ValueError,TypeError,KeyError,OSError,RuntimeError):
        print(json.dumps({'status':'blocked','reason_code':'seam_raster_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
