"""Run a frozen external-motion matrix through the public workbench API.

One step submits at most one task. Failed tasks remain evidence, never replaced.
An uncertain POST leaves a submission marker for explicit reconciliation.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import time
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False).encode()).hexdigest()


def save(path, value):
    temporary = path.with_suffix('.writing')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def api(base, path, body=None, headers=None):
    supplied = {'X-Autospine-Intent': 'pipeline-preview', 'Origin': base}
    if isinstance(body, dict):
        body = json.dumps(body).encode()
        supplied['Content-Type'] = 'application/json'
    supplied.update(headers or {})
    with urlopen(Request(base + path, data=body, headers=supplied), timeout=180) as response:
        return json.load(response)


def step(plan, state, publish, request):
    """Resume exact IDs, retaining terminal failures and explicit evidence gaps."""
    if state.get('submitting'):
        raise ValueError('uncertain_submission_reconcile_before_resuming')
    for source in plan['motions']:
        key = source['id']
        record = state['sources'].get(key)
        if record is None:
            if source.get('job_id'):
                record = {'job_id': source['job_id']}
            else:
                raw = Path(source['path']).read_bytes()
                if sha256(raw).hexdigest() != source['sha256']:
                    raise ValueError('frozen_motion_source_changed:' + key)
                state['submitting'] = {'source': key}
                publish(state)
                record = request('/api/motions', raw, {
                    'Content-Type': 'application/octet-stream',
                    'X-Autospine-File-Name': quote(Path(source['path']).name),
                    'X-Autospine-Motion-View': source['view']})
                state.pop('submitting')
            state['sources'][key] = record
            publish(state)
            return 'source_registered'
        value = request('/api/motions/' + record['job_id'])
        state['sources'][key] = value
        publish(state)
        if value['status'] in ('pending', 'running'):
            return 'waiting_source'
        if value['status'] != 'succeeded':
            continue
        if value['source_sha256'] != source['sha256'] or value['view'] != source['view']:
            raise ValueError('frozen_motion_identity_changed:' + key)
        for character in plan['characters']:
            cell = key + '/' + character['id']
            current = state['cells'].get(cell)
            if current is None:
                target = request('/api/projects/' + character['project_id'] +
                                 '/automation/character/jobs/' + character['job_id'])
                if target.get('artifact_sha256') != character['sha256']:
                    raise ValueError('frozen_character_changed:' + character['id'])
                state['submitting'] = {'cell': cell, 'source_job_id': value['job_id']}
                publish(state)
                current = request('/api/motions/' + value['job_id'] + '/adapt', {
                    'project_id': character['project_id'], 'character_job_id': character['job_id'],
                    'contact_correction': True})
                state.pop('submitting')
                state['cells'][cell] = current
                publish(state)
                return 'target_submitted'
            value_target = request('/api/motions/' + current['job_id'])
            state['cells'][cell] = value_target
            publish(state)
            expected = plan.get('expected_profiles', {})
            cached = state.get('diagnostics', {}).get(cell, {})
            checked = (cached.get('job_id') == current['job_id'] and
                       cached.get('artifact_sha256') == value_target.get('result', {}).get('artifact_sha256') and
                       cached.get('profiles') == expected)
            if value_target['status'] == 'succeeded' and expected and not checked:
                result = value_target['result']
                depth = request('/api/motions/' + current['job_id'] + '/view/motion-depth.json')
                actual = {name: result.get(name) for name in
                          ('inferred_contact_profile', 'runtime_reference_profile')}
                actual['depth_review_profile'] = depth.get('profile')
                if any(actual.get(name) != profile for name, profile in expected.items()):
                    raise ValueError('cohort_execution_profile_mismatch:' + cell)
            if value_target['status'] == 'succeeded' and cell not in state.setdefault('diagnostics', {}):
                geometry = request('/api/motions/' + current['job_id'] + '/view/deformation.json')
                state['diagnostics'][cell] = dict(job_id=current['job_id'], geometry=geometry,
                    report_sha256=value_target['result']['runtime']['files']['deformation.json'])
            if value_target['status'] == 'succeeded' and expected and not checked:
                state['diagnostics'][cell]['profiles'] = actual
                state['diagnostics'][cell]['artifact_sha256'] = result['artifact_sha256']
                state['diagnostics'][cell]['readiness'] = request(
                    '/api/motions/' + current['job_id'] + '/view/readiness.json')
            publish(state)
            if value_target['status'] in ('pending', 'running'):
                return 'waiting_target'
    return 'terminal'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('state', type=Path)
    parser.add_argument('--base', default='http://127.0.0.1:8918')
    parser.add_argument('--steps', type=int, default=1, help='bounded steps, waiting 5s only on a live task')
    args = parser.parse_args()
    url = urlsplit(args.base)
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.path:
        parser.error('only a local workbench origin is supported')
    if not 1 <= args.steps <= 1000:
        parser.error('steps must be 1..1000')
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    state = json.loads(args.state.read_text(encoding='utf-8')) if args.state.exists() else {
        'schema': 'autospine.motion-cohort-run/v1', 'plan_sha256': digest(plan),
        'sources': {}, 'cells': {}, 'authority': 'none'}
    if state['plan_sha256'] != digest(plan):
        raise ValueError('cohort_plan_changed_use_new_run')
    lock = args.state.with_suffix('.lock')
    # An interrupted runner leaves a lock; inspect its PID before removing it.
    with lock.open('x', encoding='ascii') as handle:
        handle.write(str(os.getpid()))
    try:
        for _ in range(args.steps):
            result = step(plan, state, lambda value: save(args.state, value),
                          lambda path, body=None, headers=None: api(args.base, path, body, headers))
            print(result, flush=True)
            if result == 'terminal':
                break
            if result.startswith('waiting_') and args.steps > 1:
                time.sleep(5)
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
