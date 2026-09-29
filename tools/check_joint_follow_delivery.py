"""Download selected follow candidates, verify bundle identity and emit Core fixtures."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import urlopen

from check_joint_delivery import unpack, check_bundle, runtime_check, fixture
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_joint_source import frozen_context
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('jobs', nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:8918')
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    rows=[];store=AnimatedStore('workspace')
    for job_id in args.jobs:
        with urlopen(args.base_url+'/api/motions/'+job_id,timeout=60) as response:job=json.load(response)
        if job['status']!='succeeded':raise ValueError('candidate_not_ready:'+job_id)
        folder=Path('workspace/jobs/motion-intake-v1')/job_id
        request=json.loads((folder/'request.json').read_bytes())
        source=frozen_context('workspace',request)['files']
        with urlopen(args.base_url+'/api/motions/'+job_id+'/download',timeout=60) as response:raw=response.read()
        files=unpack(raw);artifact=job['result']['artifact_sha256']
        if files!=store.read(artifact) or canonical_sha256({n:sha256(v).hexdigest() for n,v in files.items()})!=artifact:
            raise ValueError('download_identity_mismatch')
        joint=json.loads(files['joint-animation.json'])
        row=dict(job_id=job_id,artifact_sha256=artifact,bundle=check_bundle(files,source),
            runtime=runtime_check(folder,files,artifact),secondary=joint['secondary']['status'],
            root_error_px=joint['secondary']['root_error_px'],
            regions=[{k:r[k] for k in ('slot','region_kind','root_error_px','effective_gain','peak_response_deg')}
                     for r in joint['secondary']['regions']],visual_acceptance='not_evaluated')
        (args.output/(job_id+'.fixture.json')).write_bytes(canonical_bytes(fixture(files,source,joint)))
        rows.append(row);print(json.dumps(row),flush=True)
    (args.output/'delivery-report.json').write_bytes(canonical_bytes(dict(profile='m5-follow-delivery-v1',results=rows)))


if __name__=='__main__':main()
