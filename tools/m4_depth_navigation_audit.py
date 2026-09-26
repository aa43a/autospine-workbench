"""Read exact fixed-cohort diagnostics; do not rebuild, capture or accept anything."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import http.client
import json
from pathlib import Path
import re

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.depth_failure_navigation import build


def verify(row,state,host,port):
    cell,job=row['cell'],row['job_id']
    if not re.fullmatch('[a-z0-9_-]+/[a-z0-9_-]+',cell) or not re.fullmatch('motion-[a-f0-9]{32}',job):
        raise ValueError('cohort_address_invalid')
    def current():
        connection=http.client.HTTPConnection(host,port,timeout=60)
        try:
            connection.request('GET','/api/motions/'+job)
            response=connection.getresponse();value=json.loads(response.read())
            if response.status!=200:raise ValueError('cohort_job_unavailable')
            return value
        finally:connection.close()
    before=current()
    if before.get('status')!='succeeded' or before.get('result',{}).get('artifact_sha256')!=row['artifact']:
        raise ValueError('cohort_candidate_changed')
    store=AnimatedStore(state)
    files={name:store.read_file(row['artifact'],name) for name in ['skeleton.json','motion-depth.json']}
    report=build(files,row['artifact'])
    if current()!=before:raise ValueError('cohort_job_changed_during_read')
    shifted=sum(any(t!=s['time'] for t in s['order_times'])
                for g in report['groups'] for s in g['samples'])
    return dict(cell=cell,job_id=job,artifact_sha256=row['artifact'],
        order_records=report['original_order_records'],diagnostic_records=report['diagnostic_records'],
        navigable_samples=report['navigable_samples'],different_from_order_anchor=shifted),report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cohort',type=Path,required=True)
    parser.add_argument('--state',type=Path,default=Path('workspace'))
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8918)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();raw=args.cohort.read_bytes();cohort=json.loads(raw)
    if args.output.exists():raise ValueError('audit_output_exists')
    if len(cohort['rows'])!=24 or len({r['cell'] for r in cohort['rows']})!=24:
        raise ValueError('fixed_cohort_count_changed')
    cells={tuple(r['cell'].split('/')) for r in cohort['rows']}
    motions={c[0] for c in cells};characters={c[1] for c in cells if len(c)==2}
    if len(motions)!=8 or len(characters)!=3 or cells!={(m,c) for m in motions for c in characters}:
        raise ValueError('fixed_cohort_structure_changed')
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda row:verify(row,args.state,args.host,args.port),cohort['rows']))
    args.output.mkdir(parents=True)
    for row,report in results:
        path=args.output/(row['cell'].replace('/','-')+'.json')
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary=dict(profile='fixed-cohort-depth-navigation-audit-v1',source_snapshot_sha256=sha256(raw).hexdigest(),
        plan_sha256=cohort['plan_sha256'],rows=[r for r,_ in results],authority='none',
        new_runtime_capture=False,new_visual_acceptance=False,candidates_changed=False)
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(characters=3,motions=8,rows=len(results),
        additional_records=sum(r['diagnostic_records']-r['order_records'] for r,_ in results),
        different_from_order_anchor=sum(r['different_from_order_anchor'] for r,_ in results))))


if __name__=='__main__':main()
