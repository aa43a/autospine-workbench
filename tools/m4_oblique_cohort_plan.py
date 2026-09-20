"""Freeze source-qualified oblique target cases without replacing the baseline."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from m4_motion_cohort import digest,save


def build(plan,summary):
    if summary['plan_sha256']!=digest(plan): raise ValueError('oblique_summary_plan_mismatch')
    reports={r['source']:r for r in summary['records']}
    if len(reports)!=len(summary['records']) or set(reports)!={s['id'] for s in plan['motions']}:
        raise ValueError('oblique_summary_inventory_mismatch')
    result=deepcopy(plan); result['motions']=[]; result['unchanged_or_unsupported_sources']=[]
    result.update(baseline_plan_sha256=digest(plan),oblique_summary_sha256=digest(summary))
    for source in plan['motions']:
        row=reports[source['id']]; yaw=row['source_qualified_yaw']
        if yaw is None or yaw==0:
            result['unchanged_or_unsupported_sources'].append(dict(id=source['id'],yaw=yaw))
            continue
        matches=[r for r in row['records'] if r['yaw']==yaw and r.get('projection_passed') and r['status']=='compiled']
        if len(matches)!=1: raise ValueError('oblique_selected_angle_not_qualified')
        item=deepcopy(source)
        item.update(projection=dict(profile='constant-yaw-source-motion-v1',yaw_degrees=yaw),
                    prepared_motion_sha256=matches[0]['motion_sha256'])
        result['motions'].append(item)
    result['scope']='source_qualified_oblique_angles_require_target_regression'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('plan','summary','output'): parser.add_argument(name,type=Path)
    args=parser.parse_args()
    if args.output.exists(): raise ValueError('frozen_oblique_plan_already_exists')
    save(args.output,build(json.loads(args.plan.read_text(encoding='utf-8')),
                          json.loads(args.summary.read_text(encoding='utf-8'))))


if __name__=='__main__': main()
