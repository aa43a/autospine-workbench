"""Register verified experimental playback without replacing a terminal motion job."""
import argparse
from pathlib import Path
import re
from threading import RLock
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_related_candidates import register, read
from m4_link_related_candidate import document
from m4_motion_cohort import api


def run(state,job,source,visual):
    if not re.fullmatch('motion-[a-f0-9]{32}',job):raise ValueError('motion_job_invalid')
    manager=SimpleNamespace(state_root=state,_lock=RLock(),projects=SimpleNamespace(workspace_root=Path.cwd().parent),
        folder=lambda _:state/'jobs/motion-intake-v1'/job,
        get=lambda _:api('http://127.0.0.1:8918','/api/motions/'+job))
    receipt=document(source/'report.json')
    files=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    digest=register(manager,job,files,receipt,document(source/'runtime/report.json'),document(visual) if visual else None)
    # Exercise current application route code offline; not proof of live deployment.
    import json
    report=json.loads(read(manager,job,['related-candidates',digest,'report.json'])[0])
    print(json.dumps(dict(registration_sha256=digest,candidate=report['candidate_sha256'],
        baseline_job=job,scope='offline_current_code_registry_not_live_route_validation')),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('state',type=Path);p.add_argument('job');p.add_argument('source',type=Path)
    p.add_argument('--visual',type=Path)
    a=p.parse_args();run(a.state,a.job,a.source,a.visual)
