"""Verify live candidate delivery against its immutable artifact, not visual quality."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.request import urlopen
from zipfile import ZipFile
from autospine_workbench.automation.animated_store import AnimatedStore


def verify_archive(raw, files):
    with ZipFile(BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(files):
            raise ValueError('delivery_archive_inventory_mismatch')
        for name, expected in files.items():
            if archive.read(name) != expected:
                raise ValueError('delivery_archive_bytes_mismatch:'+name)
    return len(files)


def run(job, archive_raw=None):
    if not re.fullmatch(r'motion-[a-f0-9]{32}',job):
        raise ValueError('invalid_motion_job')
    base='http://127.0.0.1:8918/api/motions/'+job
    def get(suffix):
        with urlopen(base+suffix,timeout=60) as response:
            return response.read()
    before=json.loads(get(''))
    if before['status'] != 'succeeded':
        raise ValueError('delivery_job_not_succeeded')
    artifact=before['result']['artifact_sha256']
    files=AnimatedStore(Path('workspace')).read(artifact)
    archive=get('/download') if archive_raw is None else archive_raw
    count=verify_archive(archive,files)
    readiness=json.loads(get('/view/readiness.json'))
    if readiness.get('artifact_sha256') != artifact:
        raise ValueError('delivery_readiness_identity_mismatch')
    pages={}
    for name in ('player.html','contact.html','depth.html'):
        raw=get('/view/'+name)
        if b'<html' not in raw.lower() and b'<!doctype html' not in raw.lower():
            raise ValueError('delivery_html_missing:'+name)
        pages[name]=sha256(raw).hexdigest()
    after=json.loads(get(''))
    if after['status'] != 'succeeded' or after['result']['artifact_sha256'] != artifact:
        raise ValueError('delivery_job_changed')
    return dict(job_id=job,artifact_sha256=artifact,archive_sha256=sha256(archive).hexdigest(),
        archive_files=count,page_sha256=pages,readiness=readiness['status'],
        runtime=before['result']['runtime'],authority='none',production_authorized=False,
        archive_source='live_http' if archive_raw is None else 'provided_download_bytes',
        scope='live_http_and_exact_download_bytes_not_browser_render_or_visual_acceptance')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job');parser.add_argument('output',type=Path)
    parser.add_argument('--archive',type=Path,help='Verify an already downloaded browser ZIP against the exact candidate')
    args=parser.parse_args()
    report=run(args.job,args.archive.read_bytes() if args.archive else None)
    with args.output.open('x',encoding='utf-8') as handle:
        json.dump(report,handle,ensure_ascii=False,indent=2)
    print(json.dumps(dict(job_id=report['job_id'],archive_files=report['archive_files'],
                         readiness=report['readiness'])))
