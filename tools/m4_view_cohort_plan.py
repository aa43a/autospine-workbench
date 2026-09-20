"""Freeze separate target regressions for source-qualified alternative views."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from m4_motion_cohort import digest, save
from m4_prepare_views import PROFILE


def build(plan, prepared):
    if prepared['plan_sha256'] != digest(plan) or prepared.get('submitting'):
        raise ValueError('view_preparation_identity_or_submission_unresolved')
    result = deepcopy(plan)
    result['baseline_plan_sha256'] = digest(plan)
    result['view_preparation_sha256'] = digest(prepared)
    result['motions'] = []
    result['unchanged_or_unsupported_sources'] = []
    for source in plan['motions']:
        row = prepared['sources'][source['id']]
        if (row['source_sha256'] != source['sha256'] or row['parent_job_id'] != source['job_id']
                or row['profile'] != PROFILE):
            raise ValueError('prepared_source_identity_changed')
        if row['status'] not in ('succeeded', 'unsupported_projection'):
            raise ValueError('view_preparation_incomplete:' + source['id'])
        if row['status'] == 'unsupported_projection' or row['view'] == source['view']:
            result['unchanged_or_unsupported_sources'].append(dict(id=source['id'], status=row['status'], view=row['view']))
            continue
        if not any(v['view'] == row['view'] and v['passed'] for v in row['views']):
            raise ValueError('prepared_view_not_qualified')
        item = deepcopy(source)
        item.update(job_id=row['job_id'], view=row['view'], parent_job_id=source['job_id'],
                    selection_profile=PROFILE, comparison_sha256=row['comparison_sha256'],
                    prepared_motion_identity=row['motion_identity'])
        result['motions'].append(item)
    result['scope'] = 'alternative_views_require_new_target_geometry_contact_depth_and_visual_checks'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'prepared', 'output'): parser.add_argument(name, type=Path)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError('frozen_output_already_exists')
    plan, prepared = [json.loads(p.read_text(encoding='utf-8')) for p in (args.baseline, args.prepared)]
    save(args.output, build(plan, prepared))


if __name__ == '__main__': main()
