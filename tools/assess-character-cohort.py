"""Read current workbench candidates for the fixed cohort; never submit approvals."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import quote,urlsplit
from urllib.request import urlopen
from autospine_workbench.automation.character_cohort import summarize,validate_cohort
from autospine_workbench.automation.storage_io import canonical_bytes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort',type=Path,default=Path('docs/benchmark/character-milestone-cohort-v1.json'))
    parser.add_argument('--base-url',default='http://127.0.0.1:8918')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    url=urlsplit(args.base_url)
    if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost') or url.path or url.query or url.fragment or url.username:
        parser.error('base URL must be a local workbench origin')
    def raw(path):
        with urlopen(args.base_url+path,timeout=120) as response:return response.read(32<<20)
    def get(path):return json.loads(raw(path))
    cohort=json.loads(args.cohort.read_bytes());observations={}
    validate_cohort(cohort)
    for character in cohort['characters']:
        project=character['project_id'];base='/api/projects/'+quote(project,safe='')+'/automation/character'
        overview=get(base);job=overview.get('job');item=dict(job=job,reason_code=overview.get('reason_code'))
        if overview['project_id']!=project or overview['authority']!='none':raise ValueError('cohort_project_mismatch')
        if job and job['status']=='needs_review':
            path=base+'/jobs/'+job['job_id']
            report_sha=job.get('runtime',{}).get('files',{}).get('report.json')
            if report_sha:
                report=raw(path+'/view/report.json')
                if sha256(report).hexdigest()!=report_sha:raise ValueError('cohort_runtime_digest')
                decoded=json.loads(report)
                if (decoded['bundle_sha256']!=job['artifact_sha256'] or decoded.get('schema')!='autospine.character-framebuffer/v1'
                        or decoded.get('runtime_package')!='@esotericsoftware/spine-webgl' or decoded.get('runtime_version')!='4.3.13'
                        or decoded.get('authority')!='none' or not decoded.get('results')):raise ValueError('cohort_runtime_source')
                item['verified_runtime']=decoded
                visual=get(path+'/visual-review')
                if visual['project_id']!=project or visual['job_id']!=job['job_id'] or visual['artifact_sha256']!=job['artifact_sha256']:
                    raise ValueError('cohort_review_source')
                item['visual_review']=visual['review']
        observations[project]=item
    result=summarize(cohort,observations);result['cohort_sha256']=sha256(args.cohort.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result['metrics'],ensure_ascii=False))


if __name__=='__main__':main()
