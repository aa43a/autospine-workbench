"""Attach an independently checked diagnostic without changing stage acceptance."""
import argparse
import json
import re
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.automation.motion_related_candidates import load
from autospine_workbench.automation.motion_depth_supplement import publish
from autospine_workbench.safe_input_files import read_real_file
from m4_motion_cohort import api


def run(job, registration, source):
    if not re.fullmatch('motion-[a-f0-9]{32}',job):raise ValueError('motion_job_invalid')
    if not re.fullmatch('[a-f0-9]{64}',registration):raise ValueError('motion_registration_invalid')
    root=Path('workspace');folder=root/'jobs/motion-intake-v1'/job
    manager=SimpleNamespace(state_root=root,folder=lambda _:folder,
        get=lambda key:api('http://127.0.0.1:8918','/api/motions/'+key))
    value,files=load(manager,job,registration)
    report=json.loads(read_real_file(source,64<<20,'depth supplement'))
    if report.get('job_id')!=job:raise ValueError('motion_depth_supplement_job')
    print(publish(root,folder,registration,value,files,report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('job');p.add_argument('registration');p.add_argument('source',type=Path)
    a=p.parse_args();run(a.job,a.registration,a.source)
