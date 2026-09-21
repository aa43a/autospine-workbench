"""Measure full frozen source clips without changing views or excluding failures."""
import argparse
from collections import Counter
import json
from pathlib import Path

from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.torso_projection_source import anchors, shapes
from m4_motion_cohort import api, digest


def inspect(plan, state, workspace):
    if state['plan_sha256'] != digest(plan):
        raise ValueError('cohort_plan_identity_mismatch')
    rows = []
    for source in plan['motions']:
        job = state['sources'][source['id']]['job_id']
        current = api('http://127.0.0.1:8918', '/api/motions/' + job)
        if (current['status'] != 'succeeded' or current['source_sha256'] != source['sha256']
                or current['view'] != source['view']):
            raise ValueError('frozen_motion_identity_changed:' + source['id'])
        identity = current['result']['motion']
        bundle = VerifiedMotionBundleReader(workspace).load(
            identity['clip_sha256'], identity['bundle_sha256'])
        observed, ticks = anchors(bundle, source.get('projection', {}).get('yaw_degrees', 0))
        row = dict(source_id=source['id'], job_id=job, raw_sha256=source['sha256'],
            bundle_sha256=identity['bundle_sha256'], view=source['view'],
            projection=source.get('projection'), frame_count=len(ticks))
        try:
            report = shapes(observed, [t / 1e6 for t in ticks])
        except ValueError as exc:
            # Degenerate initial planes have no valid relative shape baseline.
            if not str(exc).startswith(('torso_initial_', 'torso_anchor_')):
                raise
            row.update(status='unmeasurable', reason_code=str(exc))
        else:
            failed = [r for r in report['records'] if r['reasons']]
            row.update(status='within_source_bounds' if not failed else 'outside_source_bounds',
                unsupported_frames=len(failed), reason_counts=dict(Counter(
                    reason for r in failed for reason in r['reasons'])), measurement=report)
        rows.append(row)
    return dict(schema='autospine.torso-source-support/v1', plan_sha256=digest(plan),
        scope='full_source_clips_only_not_target_or_runtime_acceptance', rows=rows,
        authority='none', production_authorized=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('state', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = inspect(json.loads(args.plan.read_bytes()), json.loads(args.state.read_bytes()), Path('workspace'))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps([{k: v for k, v in row.items() if k not in ('measurement',)}
        for row in report['rows']], ensure_ascii=False, indent=2))
