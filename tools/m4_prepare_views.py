"""Prepare source-qualified views without changing the frozen front baseline."""
import argparse
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError

from m4_motion_cohort import api, digest, save

PROFILE = 'full-source-front-side-projection-selection-v1'


def step(plan, state, publish, request):
    if state.get('submitting'):
        raise ValueError('uncertain_view_submission_reconcile_before_resuming')
    for source in plan['motions']:
        key = source['id']; row = state['sources'].get(key)
        if row and row['status'] in ('succeeded', 'unsupported_projection', 'failed', 'canceled', 'interrupted'):
            continue
        if row and row.get('job_id'):
            job = request('/api/motions/' + row['job_id'])
            row['status'] = job['status']
            row['reason_code'] = job.get('reason_code')
            if job['status'] == 'succeeded':
                if (job['source_sha256'] != source['sha256'] or job['view'] != row['view'] or
                        job.get('result', {}).get('motion_status') != 'compiled'):
                    raise ValueError('prepared_view_identity_mismatch:' + key)
                row['motion_identity'] = job['result']['motion']
            publish(state)
            if job['status'] in ('pending', 'running'): return 'waiting_source'
            continue
        comparison = request('/api/motions/' + source['job_id'] + '/compare-views')
        if (comparison['profile'] != PROFILE or comparison['source_sha256'] != source['sha256'] or
                comparison['source_job_id'] != source['job_id']):
            raise ValueError('view_comparison_identity_mismatch:' + key)
        selected = comparison['recommended_view']
        row = dict(parent_job_id=source['job_id'], source_sha256=source['sha256'], view=selected,
                   comparison_sha256=comparison['comparison_sha256'],
                   profile=PROFILE, status='ready_to_submit',
                   views=[{k: r[k] for k in ('view', 'passed', 'failed_roles', 'missing_roles')}
                          for r in comparison['records']])
        state['sources'][key] = row
        if selected is None:
            row['status'] = 'unsupported_projection'; publish(state); return 'unsupported_projection'
        if selected == source['view']:
            row['job_id'] = source['job_id']; row['status'] = 'pending_verification'
            publish(state); return 'current_view_retained'
        if sum(j['status'] in ('pending', 'running') for j in request('/api/motions')['jobs']) >= 2:
            publish(state); return 'waiting_capacity'
        state['submitting'] = dict(source=key, parent_job_id=source['job_id'], view=selected,
                                   comparison_sha256=comparison['comparison_sha256'])
        publish(state)
        try:
            job = request('/api/motions/' + source['job_id'] + '/reproject', {
                'view': selected, 'comparison_sha256': comparison['comparison_sha256']})
        except HTTPError as exc:
            # Only an explicit pre-submission capacity rejection is safe to retry.
            try:
                reason = json.loads(exc.read()).get('reason_code')
            except (ValueError, AttributeError):
                raise exc
            finally:
                exc.close()
            if exc.code != 400 or reason != 'motion_queue_full':
                raise
            state.pop('submitting'); publish(state)
            return 'waiting_capacity'
        state.pop('submitting'); row.update(job_id=job['job_id'], status=job['status'])
        publish(state); return 'view_submitted'
    return 'terminal'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path); parser.add_argument('state', type=Path)
    parser.add_argument('--steps', type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.steps <= 1000: parser.error('steps must be 1..1000')
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    state = json.loads(args.state.read_text(encoding='utf-8')) if args.state.exists() else dict(
        schema='autospine.prepared-cohort-views/v1', plan_sha256=digest(plan), sources={}, authority='none')
    if state['plan_sha256'] != digest(plan): raise ValueError('view_plan_changed')
    lock = args.state.with_suffix('.lock')
    with lock.open('x', encoding='ascii') as handle: handle.write(str(os.getpid()))
    try:
        for _ in range(args.steps):
            if args.state.with_suffix('.stop').exists(): break
            result = step(plan, state, lambda value: save(args.state, value),
                          lambda path, body=None: api('http://127.0.0.1:8918', path, body))
            print(result, flush=True)
            if result == 'terminal': break
            if result.startswith('waiting_'): time.sleep(5)
    finally: lock.unlink()


if __name__ == '__main__': main()
