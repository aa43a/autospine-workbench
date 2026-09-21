"""Refresh diagnostics for frozen candidates using GET only, into a new snapshot."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit
from m4_motion_cohort import api, digest


def refresh(plan, state, request, progress=lambda key: None):
    if state.get('plan_sha256') != digest(plan):
        raise ValueError('cohort_plan_identity_mismatch')
    output = deepcopy(state)
    for source in plan['motions']:
        original = state['sources'].get(source['id'], {})
        if original.get('status') != 'succeeded':
            continue
        actual = request('/api/motions/' + original['job_id'])
        if (actual.get('status') != 'succeeded' or actual.get('job_id') != original['job_id']
                or actual.get('source_sha256') != source['sha256']):
            raise ValueError('cohort_source_changed')
        for character in plan['characters']:
            key = source['id'] + '/' + character['id']
            job = state['cells'].get(key, {})
            if job.get('status') != 'succeeded':
                continue
            base = '/api/motions/' + job['job_id']
            artifact = job['result']['artifact_sha256']
            def current():
                value = request(base)
                if (value.get('job_id') != job['job_id'] or value.get('status') != 'succeeded'
                        or value.get('result', {}).get('artifact_sha256') != artifact):
                    raise ValueError('cohort_candidate_changed:' + key)
            current()
            diagnostic = output.setdefault('diagnostics', {}).setdefault(key, {})
            if diagnostic.get('job_id', job['job_id']) != job['job_id']:
                raise ValueError('cohort_diagnostic_job_mismatch')
            diagnostic.update(job_id=job['job_id'], artifact_sha256=artifact)
            for name in ('readiness', 'depth-status'):
                value = request(base + '/view/' + name + '.json')
                if value.get('artifact_sha256') != artifact:
                    raise ValueError('cohort_diagnostic_artifact_mismatch:' + key)
                diagnostic[name.replace('-', '_')] = value
            current()
            progress(key)
    output['diagnostics_refreshed_at'] = datetime.now(timezone.utc).isoformat()
    output['diagnostic_snapshot_scope'] = 'read_only_existing_candidates_no_recapture'
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path); parser.add_argument('state', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--base', default='http://127.0.0.1:8918')
    args = parser.parse_args(); origin = urlsplit(args.base)
    if origin.scheme != 'http' or origin.hostname != '127.0.0.1' or origin.path:
        parser.error('only a local workbench origin is supported')
    if args.output.exists() or args.output.resolve() in (args.plan.resolve(), args.state.resolve()):
        parser.error('output must be a new snapshot')
    plan, state = [json.loads(p.read_text(encoding='utf-8')) for p in (args.plan, args.state)]
    result = refresh(plan, state, lambda path: api(args.base, path),
                     lambda key: print(key, flush=True))
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
