"""Read-only, separate visual-decision snapshot; never mutate a running matrix."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit

from m4_motion_cohort import api, digest, save


def collect(plan, state, request):
    if state['plan_sha256'] != digest(plan):
        raise ValueError('cohort_plan_identity_mismatch')
    output = dict(schema='autospine.motion-cohort-reviews/v1', plan_sha256=digest(plan),
                  captured_at=datetime.now(timezone.utc).isoformat(), cells={},
                  authority='none', production_authorized=False)
    for source in plan['motions']:
        for character in plan['characters']:
            key = source['id'] + '/' + character['id']
            job = state['cells'].get(key, {})
            if job.get('status') != 'succeeded':
                continue
            row = request('/api/motions/' + job['job_id'] + '/stage-review')
            if (row['job_id'] != job['job_id'] or
                    row['artifact_sha256'] != job['result']['artifact_sha256'] or
                    row['evidence_sha256'] != digest(row['readiness'])):
                raise ValueError('cohort_review_identity_mismatch:' + key)
            output['cells'][key] = {k: row[k] for k in (
                'job_id', 'artifact_sha256', 'evidence_sha256', 'revision', 'current', 'current_applies')}
    return output


def decision(snapshot, key, job, readiness):
    row = (snapshot or {}).get('cells', {}).get(key)
    if row is None:
        return 'not_evaluated', None
    if (row['job_id'] != job.get('job_id') or
            row['artifact_sha256'] != job.get('result', {}).get('artifact_sha256')):
        raise ValueError('cohort_review_candidate_mismatch:' + key)
    current = row['current']
    if current is None:
        return 'not_evaluated', None
    if (not row['current_applies'] or row['evidence_sha256'] != digest(readiness) or
            current['artifact_sha256'] != row['artifact_sha256'] or
            current['evidence_sha256'] != row['evidence_sha256']):
        return 'evidence_changed', current
    if current['decision'] not in ('accepted', 'accepted_with_exceptions', 'rejected', 'revoked'):
        raise ValueError('cohort_review_decision_invalid')
    return current['decision'], current


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path); parser.add_argument('state', type=Path)
    parser.add_argument('output', type=Path); parser.add_argument('--base', default='http://127.0.0.1:8918')
    args = parser.parse_args(); url = urlsplit(args.base)
    if args.output.resolve() in (args.plan.resolve(), args.state.resolve()):
        parser.error('review snapshot must not overwrite the plan or running state')
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.path:
        parser.error('only a local workbench origin is supported')
    plan, state = [json.loads(p.read_text(encoding='utf-8')) for p in (args.plan, args.state)]
    save(args.output, collect(plan, state, lambda path: api(args.base, path)))
