"""Verify two completed local generations; report actual byte equality, not a guarantee."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.request import urlopen
from zipfile import ZipFile


def inspect(job, state_root):
    if not re.fullmatch(r'motion-[a-f0-9]{32}', job):
        raise ValueError('invalid_generation_job')
    base = 'http://127.0.0.1:8918/api/motions/' + job
    with urlopen(base, timeout=30) as response:
        value = json.load(response)
    if value.get('kind') != 'generate' or value['status'] != 'succeeded':
        raise ValueError('generation_not_complete:' + job)
    folder = state_root / 'jobs/motion-intake-v1' / job
    result = value['result']
    raw = (folder / 'source.npz').read_bytes()
    if sha256(raw).hexdigest() != value['source_sha256']:
        raise ValueError('generation_source_changed')
    environment = (folder / 'generation-environment.json').read_bytes()
    request = (folder / 'generation-request.json').read_bytes()
    for content, field in ((environment, 'environment_sha256'), (request, 'request_sha256')):
        if sha256(content).hexdigest() != result['generation'][field]:
            raise ValueError('generation_provenance_changed:' + field)
    with urlopen(base + '/preview', timeout=30) as response:
        preview = response.read()
    if sha256(preview).hexdigest() != result['preview_sha256']:
        raise ValueError('generation_preview_changed')
    with ZipFile(BytesIO(raw)) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError('duplicate_npz_members')
        members = {name: sha256(archive.read(name)).hexdigest() for name in archive.namelist()}
    return dict(job_id=job, source_sha256=value['source_sha256'], result=result,
                members=members, environment=json.loads(environment))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('old_job'); parser.add_argument('new_job')
    parser.add_argument('output', type=Path)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    args = parser.parse_args()
    if args.old_job == args.new_job:
        raise ValueError('replay_requires_distinct_jobs')
    old, new = [inspect(job, args.state_root) for job in (args.old_job, args.new_job)]
    same_parameters = old['result']['generation']['parameters'] == new['result']['generation']['parameters']
    if not same_parameters:
        raise ValueError('replay_parameters_differ')
    report = dict(schema='autospine.m4-generation-replay/v1',
                  checked_at=datetime.now(timezone.utc).isoformat(), old=old, new=new,
                  parameters_equal=same_parameters,
                  environment_equal=old['environment'] == new['environment'],
                  npz_bytes_equal=old['source_sha256'] == new['source_sha256'],
                  npz_members_equal=old['members'] == new['members'],
                  scope='two_observed_runs_not_general_determinism_or_visual_acceptance')
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2); handle.write('\n')
    print(json.dumps({key: report[key] for key in (
        'parameters_equal', 'environment_equal', 'npz_bytes_equal', 'npz_members_equal')}))


if __name__ == '__main__':
    main()
