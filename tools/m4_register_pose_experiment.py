"""Register an exact post-contact experiment for read-only workbench playback."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_experiments import publish
from autospine_workbench.automation.storage_io import read_document
from autospine_workbench.safe_input_files import read_real_file
from m4_motion_cohort import api


def run(parent_folder, folder):
    parent = read_document(parent_folder/'report.json')
    report = read_document(folder/'report.json')
    runtime = json.loads(read_real_file(folder/'runtime/report.json',64 << 20,'experiment runtime'))
    root = Path('workspace'); job = parent['job_id']
    # Validate identifier before using it as a path.
    import re
    if not re.fullmatch('motion-[a-f0-9]{32}', job): raise ValueError('motion_job_invalid')
    job_folder = root/'jobs/motion-intake-v1'/job
    request = read_document(job_folder/'request.json')
    current = api('http://127.0.0.1:8918', '/api/motions/'+job)
    if current['status'] != 'succeeded': raise ValueError('motion_baseline_unavailable')
    AnimatedStore(parent_folder/'isolated-store').read(parent['candidate_bundle_sha256'])
    files = AnimatedStore(folder/'isolated-store').read(report['candidate_bundle_sha256'])
    digest = publish(root, job_folder, request, current['result']['artifact_sha256'], parent, report, runtime, files)
    print(json.dumps(dict(job_id=job,evidence_sha256=digest,authority='none')))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('folder',type=Path)
    a=p.parse_args();run(a.parent,a.folder)
