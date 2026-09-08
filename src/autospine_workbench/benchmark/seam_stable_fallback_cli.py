"""Materialize explicit whole-clip fallback selections with fresh geometry and alpha QA."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.seam_stable_fallback import build
from ..targets.spine43.continuous_pose import inspect
from ..targets.spine43.alpha_seam import analyze
from ..targets.spine43.same_frame_seam import analyze as raster
from .seam_gap_context_cli import load
from .elbow_target_cli import archive


def compile_report(before,after,before_dir,after_dir,followers):
    if before['schema']!='autospine.continuous-anchor-preview/v1' or after['schema']!='autospine.seam-increment-preview/v1':
        raise ValueError('fallback_source_schema')
    if after['source_anchor_sha256']!=canonical_sha256(before): raise ValueError('fallback_source_identity')
    reference=json.loads(load(before,before_dir,'skeleton.json'));candidate=json.loads(load(after,after_dir,'skeleton.json'))
    files={name:load(after,after_dir,name) for name in after['files']}
    doc=build(reference,candidate,followers);geometry=inspect(doc);alpha=analyze(doc,files)
    original=before['alpha_seam_qa']['after']
    for key in ('boundaries',):
        if alpha[key]!=original[key]: raise ValueError('fallback_boundary_identity')
    if [r['pairs'] for r in alpha['relations']]!=[r['pairs'] for r in original['relations']]:raise ValueError('fallback_pair_identity')
    comparison,images=raster(reference,doc,files,original['boundaries'],original['relations'])
    encode=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    files['skeleton.json']=encode(doc);editor=deepcopy(doc);editor['skeleton']['images']='./images/';files['editor/skeleton.json']=encode(editor)
    files.update({'fallback-raster/'+name:raw for name,raw in images.items()});files.pop('preview-manifest.json',None)
    # Narrow metadata needed by the existing renderer; do not carry stale solver QA.
    manifest={k:deepcopy(after[k]) for k in ('regions',) if k in after}
    manifest.update(schema='autospine.seam-stable-fallback-preview/v1',authority='none',production_authorized=False,status='needs_review',
                    animation='seam_increment_inspection',bake_qa=geometry,shape_qa={'after':alpha},
                    files={n:hashlib.sha256(raw).hexdigest() for n,raw in files.items()})
    files['preview-manifest.json']=encode(manifest)
    report=dict(schema='autospine.seam-stable-fallback/v1',profile='explicit-whole-attachment-track-v1',
                source_reference_sha256=canonical_sha256(before),source_candidate_sha256=canonical_sha256(after),
                followers=followers,authority='none',production_authorized=False,status='needs_review',
                geometry=geometry,alpha=alpha,comparison=comparison,files={n:hashlib.sha256(raw).hexdigest() for n,raw in files.items()})
    return report,files


def read_fallback(saved,before,after,before_dir,after_dir):
    expected,_=compile_report(before,after,before_dir,after_dir,saved['followers'])
    if canonical_sha256(expected)!=canonical_sha256(saved):raise ValueError('fallback_reader_mismatch')
    return saved


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','after','before-dir','after-dir','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--follower',action='append',required=True);args=p.parse_args()
    try:
        report,files=compile_report(json.loads(args.before.read_text()),json.loads(args.after.read_text()),args.before_dir,args.after_dir,args.follower)
        digest=canonical_sha256(report);args.output_dir.mkdir(parents=True,exist_ok=True)
        report_path=args.output_dir/(digest+'.json')
        if report_path.exists() and canonical_sha256(json.loads(report_path.read_text()))!=digest:
            raise ValueError('fallback_existing_corrupt')
        for name,raw in files.items():
            target=args.output_dir/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        (args.output_dir/'preview.zip').write_bytes(archive(files))
        print(json.dumps(dict(artifact_sha256=digest,geometry_passed=all(r['passed'] for r in report['geometry']['regions'].values()),growth=[r['max_distance_growth_px'] for r in report['alpha']['relations']])));return 0
    except (ValueError,KeyError,TypeError,OSError):
        print(json.dumps(dict(status='blocked',reason_code='stable_fallback_failed',authority='none')));return 1


if __name__=='__main__':raise SystemExit(main())
