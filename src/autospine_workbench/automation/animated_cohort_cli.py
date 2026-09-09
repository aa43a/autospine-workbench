"""Build current local projects in sequence, without SHA entry or review mutations."""
import argparse
import json
from pathlib import Path
import time
import re
from urllib.parse import urlparse, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

from ..manifest_artifacts import require_safe_token
from .animated_cohort_report import build_report, publish_report


class LocalWorkbench:
    def __init__(self, base):
        url = urlparse(base)
        if (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost', '::1'} or
            url.username or url.password or url.path not in {'', '/'} or url.query or url.fragment):
            raise ValueError('cohort_local_service_required')
        self.base = base.rstrip('/')
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise ValueError('cohort_redirect_rejected')
        self.opener = build_opener(NoRedirect())

    def request(self, path, body=None):
        headers = {'Origin': self.base, 'X-Autospine-Intent': 'pipeline-preview', 'Content-Type': 'application/json'}
        request = Request(self.base + path, None if body is None else json.dumps(body).encode(), headers)
        with self.opener.open(request, timeout=120) as response:
            if response.url != self.base + path:
                raise ValueError('cohort_redirect_rejected')
            raw = response.read((4 << 20) + 1)
        if len(raw) > 4 << 20:
            raise ValueError('cohort_response_limit')
        return json.loads(raw)


def build_case(client, project, clip, expected, timeout=600):
    endpoint = '/api/projects/' + quote(project, safe='') + '/automation/animated'
    job = client.request(endpoint + '/preview', dict(expected_resolved_sha256=expected, clip=clip, resume=True))
    job_id = job['job_id']
    if not re.fullmatch(r'job-[0-9a-f]{32}', job_id):
        raise ValueError('cohort_job_mismatch')
    deadline = time.monotonic() + timeout
    while True:
        if job.get('project_id') != project or job.get('job_id') != job_id or job.get('authority') != 'none':
            raise ValueError('cohort_job_mismatch')
        if job['status'] not in {'pending', 'running'}:
            break
        if time.monotonic() >= deadline:
            client.request(endpoint + '/jobs/' + job_id + '/cancel', {})
            raise ValueError('cohort_job_timeout')
        time.sleep(1)
        job = client.request(endpoint + '/jobs/' + job_id)
    run = job.get('run') or {}
    if run and (run.get('clip') != clip or run.get('source_addresses', {}).get('resolved_project_sha256') != expected):
        raise ValueError('cohort_source_mismatch')
    return dict(project_id=project, clip=clip, expected_resolved_sha256=expected,
                job_id=job_id, run_id=run.get('run_id'), source_addresses=run.get('source_addresses', {}),
                status=job['status'], preview_available=bool(run.get('preview_available')),
                summary=run.get('summary', {}), review_items=run.get('review_items', []),
                reason_code=job.get('reason_code'), bundle_sha256=(run.get('steps') or [{}, {}, {}])[2].get('outputs', {}).get('bundle_sha256'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8918')
    parser.add_argument('--projects', nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if not 1 <= len(args.projects) <= 20 or len(set(args.projects)) != len(args.projects):
        raise ValueError('cohort_project_list_invalid')
    for project in args.projects:
        require_safe_token(project, 'Project')
    client = LocalWorkbench(args.base_url)
    rows = []
    for project in args.projects:
        overview = client.request('/api/projects/' + quote(project, safe='') + '/automation/animated')
        for clip in ('limb-flex-15', 'limb-flex-30'):
            try:
                row = build_case(client, project, clip, overview['resolved_project_sha256'])
            except (OSError, ValueError, KeyError) as exc:
                reason = str(exc) if re.fullmatch(r'cohort_[a-z_]+', str(exc)) else 'cohort_request_failed'
                row = dict(project_id=project, clip=clip, expected_resolved_sha256=overview['resolved_project_sha256'],
                           status='failed', preview_available=False, summary={}, review_items=[], reason_code=reason)
            rows.append(row)
            print(json.dumps(dict(project=project, clip=clip, preview=row['preview_available'], summary=row['summary'])), flush=True)
    for project in args.projects:
        current = client.request('/api/projects/' + quote(project, safe='') + '/automation/animated')
        for row in rows:
            if row['project_id'] == project and (row['expected_resolved_sha256'] != current['resolved_project_sha256'] or
                row['preview_available'] and row['source_addresses'].get('input_identity_sha256') != current.get('input_identity_sha256')):
                row.update(status='blocked', preview_available=False, reason_code='cohort_source_changed')
    digest, folder = publish_report(args.output, build_report(rows))
    print(json.dumps(dict(report_sha256=digest, report=str(folder / 'index.html'), authority='none')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
