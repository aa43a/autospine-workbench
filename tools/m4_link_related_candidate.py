"""Produce a verified related-candidate record; do not register or replace a job."""
import argparse
import json
from pathlib import Path
import re
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_related_evidence import inspect
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.safe_input_files import read_real_file


def document(path):
    return json.loads(read_real_file(path,64<<20,'related candidate evidence'))


def run(state,job,source,visual,output):
    if not re.fullmatch('motion-[a-f0-9]{32}',job):raise ValueError('motion_job_invalid')
    if output.exists():raise ValueError('related_evidence_output_exists')
    request=document(state/'jobs/motion-intake-v1'/job/'request.json')
    receipt=document(source/'report.json')
    files=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    report=inspect(request,AnimatedStore(state).read(request['character_sha256']),files,
        receipt,document(source/'runtime/report.json'),document(visual) if visual else None)
    report['baseline_job_id']=job
    output.write_bytes(canonical_bytes(report))
    print(json.dumps({k:report[k] for k in ('baseline_job_id','candidate_sha256','sampled_frames',
        'runtime_version','target_version','relationship')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('state',type=Path);p.add_argument('job');p.add_argument('source',type=Path)
    p.add_argument('output',type=Path);p.add_argument('--visual',type=Path)
    a=p.parse_args();run(a.state,a.job,a.source,a.visual,a.output)
