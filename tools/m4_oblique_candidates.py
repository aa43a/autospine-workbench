"""Compile constant-yaw candidates from exact sources, retaining failed angles."""
import argparse
import json
from pathlib import Path

from m4_motion_cohort import api,digest,save
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.oblique_source import extract
from autospine_workbench.targets.character43.oblique_motion import compile_candidate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args()
    plan=json.loads(args.plan.read_text(encoding='utf-8'))
    reader=VerifiedMotionBundleReader(Path('workspace')); summary=[]
    for source in plan['motions']:
        job=api('http://127.0.0.1:8918','/api/motions/'+source['job_id'])
        if job['source_sha256']!=source['sha256'] or job['view']!=source['view']:
            raise ValueError('frozen_source_mismatch')
        identity=job['result']['motion']
        bundle=reader.load(identity['clip_sha256'],identity['bundle_sha256'])
        data=extract(bundle); records=[]
        directory=args.output/source['id']; directory.mkdir(parents=True,exist_ok=True)
        for yaw in range(-90,91,15):
            prefix='yaw-'+str(yaw)
            try:
                motion,receipt=compile_candidate(bundle.motion,*data,yaw,
                                                  precision=5 if bundle.source_kind=='kimodo_npz' else 12)
            except ValueError as exc:
                records.append(dict(yaw=yaw,status='rejected',reason=str(exc)))
                continue
            if yaw==0 and motion['tracks']!=bundle.motion['tracks']:
                # Floating operation order may differ below compiler precision;
                # never silently claim exact compatibility on a real source.
                maximum=max(abs(a-b) for old,new in zip(bundle.motion['tracks'],motion['tracks'])
                    for ka,kb in zip(old['keys'],new['keys'])
                    for a,b in zip(ka['value'] if isinstance(ka['value'],list) else [ka['value']],
                                   kb['value'] if isinstance(kb['value'],list) else [kb['value']]))
                if maximum>1e-9: raise ValueError('zero_yaw_transfer_regression')
            receipt.update(source_job_id=source['job_id'],source_sha256=source['sha256'],
                           motion_identity=identity,plan_sha256=digest(plan))
            save(directory/(prefix+'-motion.json'),motion)
            save(directory/(prefix+'-receipt.json'),receipt)
            records.append(dict(yaw=yaw,status='compiled',projection_passed=receipt['projection']['passed'],
                failed_roles=[r['role'] for r in receipt['projection']['records'] if not r['passed']],
                motion_sha256=receipt['motion_sha256']))
        passing=[r['yaw'] for r in records if r.get('projection_passed')]
        suggested=min(passing,key=lambda yaw:(abs(yaw),yaw)) if passing else None
        summary.append(dict(source=source['id'],records=records,source_qualified_yaw=suggested))
        print(source['id'],passing,flush=True)
    save(args.output/'summary.json',dict(plan_sha256=digest(plan),records=summary,authority='none',
        scope='source_projection_only_not_artwork_or_target_motion_acceptance'))


if __name__=='__main__': main()
