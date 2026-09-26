"""Read-only live API audit; hashes immutable downloads and existing review journals."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.request import urlopen
from zipfile import ZipFile

from autospine_workbench.automation.storage_io import canonical_bytes


def journals(state):
    root = state / 'jobs/motion-intake-v1'
    paths = [*root.glob('motion-*/stage-reviews/review-*.json'),
             *root.glob('motion-*/related-stage-reviews/*/review-*.json')]
    return {p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, default=Path('workspace'))
    parser.add_argument('--port', type=int, default=8918)
    parser.add_argument('--job', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--snapshot', action='store_true')
    args = parser.parse_args()
    if any(not re.fullmatch('motion-[a-f0-9]{32}', j) for j in args.job): raise ValueError('invalid job')
    if args.output.exists(): raise ValueError('output already exists')
    origin = f'http://127.0.0.1:{args.port}'
    def get(path):
        with urlopen(origin + path, timeout=180) as response: return response.read()
    def data(path): return json.loads(get(path))
    before = journals(args.state)
    rows = []; baselines = {}
    for job in args.job:
        base = '/api/motions/' + job
        baselines[job] = data(base + '/stage-review')
        if args.snapshot: continue
        listing = data(base + '/view/related-candidates.json')
        if listing['baseline_sha256'] != baselines[job]['artifact_sha256']: raise ValueError('baseline changed')
        for item in listing['rows']:
            registration = item['registration_sha256']
            review = data(base + '/related-candidates/' + registration + '/stage-review')
            if review['artifact_sha256'] != item['candidate_sha256']: raise ValueError('candidate changed')
            if review['registration_sha256'] != registration: raise ValueError('registration changed')
            if item['stage_review']['evidence_sha256'] != review['evidence_sha256']: raise ValueError('evidence changed')
            path = base + '/view/related-candidates/' + registration + '/'
            if b'player-assets/client.js' not in get(path + 'player.html'): raise ValueError('player unavailable')
            exported = get(path + 'candidate.zip')
            with ZipFile(BytesIO(exported)) as archive:
                manifest = json.loads(archive.read('related-export.json'))
                if manifest['candidate_sha256'] != item['candidate_sha256']: raise ValueError('export candidate')
                if manifest['registration_sha256'] != registration: raise ValueError('export registration')
                if json.loads(archive.read('related-stage-review.json')) != review: raise ValueError('export review')
                for name, digest in {**manifest['candidate_files'], **manifest['evidence_files']}.items():
                    if sha256(archive.read(name)).hexdigest() != digest: raise ValueError('export hash ' + name)
                if sha256(canonical_bytes(manifest['candidate_files'])).hexdigest() != item['candidate_sha256']:
                    raise ValueError('export bundle')
            rows.append(dict(job_id=job, registration_sha256=registration,
                artifact_sha256=review['artifact_sha256'], revision=review['revision'],
                imported_visual=review['imported_visual'], status=review['readiness']['status'],
                stages=[dict(stage=s['stage'], status=s['status']) for s in review['readiness']['stages']],
                export_sha256=sha256(exported).hexdigest(), candidate_files=len(manifest['candidate_files']),
                export_review_matches=True, candidate_hashes_verified=True, player_shell_served=True))
            print(json.dumps(dict(registration=registration, status='verified')), flush=True)
        if data(base + '/stage-review') != baselines[job]: raise ValueError('baseline review changed')
    if journals(args.state) != before: raise ValueError('review history changed during read')
    modules = ['motion-related-candidates.js', 'motion-stage-review.js', 'motion-related-summary.js', 'motion-cohort-status.js']
    if not args.snapshot:
        for name in modules:
            if get('/modules/' + name) != (Path('web/modules') / name).read_bytes(): raise ValueError('web module outdated')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = dict(profile='motion-related-review-api-audit-v1', rows=rows, baselines=baselines,
        journal_hashes=before, mutations=0, browser_interaction_verified=False, new_runtime_capture=False)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(dict(registrations=len(rows), journals=len(before), output=str(args.output))), flush=True)


if __name__ == '__main__': main()
