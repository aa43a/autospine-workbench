"""Foot-source parity on three exact candidates; other quality failures stay separate."""
import argparse
import json
import math
from pathlib import Path
from m4_foot_target_check import run


def save_exact(path,report):
    if path.exists():
        if json.loads(path.read_bytes())!=report:raise ValueError('cohort_receipt_changed')
        return
    with path.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)


def summarize(reports):
    if len(reports)!=3 or len({r['job_id'] for r in reports.values()})!=3:
        raise ValueError('three_distinct_candidates_required')
    identities=[r['motion_identity'] for r in reports.values()]
    if any(i!=identities[0] for i in identities[1:]):raise ValueError('cohort_motion_identity_mismatch')
    rows=[]
    for character,r in reports.items():
        matrix=r['maximum_key_matrix_error'];shift=r['maximum_ankle_shift_from_foot_channels_px']
        foot_ok=(math.isfinite(matrix) and matrix<=1e-8 and math.isfinite(shift) and shift<=1e-8
                 and r['source_contact_markers_preserved'] is True and r['key_samples']>0)
        rows.append(dict(character=character,job_id=r['job_id'],artifact=r['artifact_sha256'],
            foot_frame_passed=foot_ok,matrix_error=matrix,ankle_channel_shift_px=shift,
            source_key_samples=r['key_samples'],runtime_samples=r['timeline_samples'],
            geometry_passed=r['geometry_passed'],contact_status=r['contact_status'],
            runtime=r['runtime'],failed_slots=[x['slot'] for x in r['geometry_failures']]))
    return dict(profile='kimodo-foot-three-structure-regression-v1',motion_identity=identities[0],
        required=3,foot_frame_passed=sum(r['foot_frame_passed'] for r in rows),
        geometry_passed=sum(r['geometry_passed'] is True for r in rows),rows=rows,
        authority='none',selected=False,scope='source_foot_frame_parity_not_complete_motion_acceptance')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    args=parser.parse_args();reports={}
    for character in ('hongmeiling','alice','huiye'):
        root=args.root/character
        job=json.loads((root/'submitted.json').read_bytes())['job_id']
        report=run(job);reports[character]=report
        save_exact(root/'cohort-check.json',report)
        print(character+' checked',flush=True)
    report=summarize(reports)
    save_exact(args.root/'cohort-summary.json',report)
    print(json.dumps({k:report[k] for k in ('required','foot_frame_passed','geometry_passed','scope')}),flush=True)
