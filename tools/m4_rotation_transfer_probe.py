"""Correlate frozen source directions and actual exported target rotation keys."""
import argparse
import json
from pathlib import Path

from m4_motion_cohort import api, digest, save
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.rotation_transfer_diagnostics import compare


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('plan','state','source_diagnostics','output'): parser.add_argument(name,type=Path)
    parser.add_argument('--motion', default='walking')
    args=parser.parse_args()
    plan=json.loads(args.plan.read_text(encoding='utf-8'))
    state=json.loads(args.state.read_text(encoding='utf-8'))
    if state['plan_sha256'] != digest(plan): raise ValueError('frozen_plan_mismatch')
    source=next(s for s in plan['motions'] if s['id']==args.motion)
    diagnostic=json.loads((args.source_diagnostics/(args.motion+'.json')).read_text(encoding='utf-8'))
    if diagnostic['plan_sha256'] != digest(plan) or diagnostic['source_job_id'] != source['job_id']:
        raise ValueError('source_diagnostic_mismatch')
    base='http://127.0.0.1:8918'
    current=api(base,'/api/motions/'+source['job_id'])
    identity=current['result']['motion']
    if (identity != diagnostic['motion_identity'] or current['source_sha256'] != source['sha256']
            or current['view'] != source['view']): raise ValueError('source_identity_changed')
    motion=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256']).motion
    args.output.mkdir(parents=True,exist_ok=True)
    for character in plan['characters']:
        cell=args.motion+'/'+character['id']; recorded=state['cells'][cell]
        if recorded['status'] != 'succeeded': raise ValueError('target_not_complete:'+cell)
        job=api(base,'/api/motions/'+recorded['job_id'])
        if job['result']['artifact_sha256'] != recorded['result']['artifact_sha256']:
            raise ValueError('target_identity_changed')
        prefix='/api/motions/'+job['job_id']+'/view/'
        # Public reader verifies exact candidate and captured Runtime context.
        skeleton=api(base,prefix+'player-assets/skeleton.json')
        names=job['result']['animations']
        if len(names)!=1: raise ValueError('external_animation_ambiguous')
        report=compare(motion,skeleton,names[0],diagnostic)
        report.update(job_id=job['job_id'],artifact_sha256=job['result']['artifact_sha256'],
                      plan_sha256=digest(plan),source_diagnostic_sha256=digest(diagnostic),
                      source_job_id=source['job_id'],motion_identity=identity,
                      player_url=base+prefix+'player.html')
        save(args.output/(character['id']+'.json'),report)
        print(character['id'],json.dumps([dict(bone=r['bone'],difference=r['maximum_transfer_difference_deg'],
            extra_turn=r['extra_turn_suspected']) for r in report['records']]),flush=True)


if __name__=='__main__': main()
