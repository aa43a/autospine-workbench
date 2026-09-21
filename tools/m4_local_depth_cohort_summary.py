"""Freeze exact local-depth evidence and causes across candidate reports."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.local_depth_summary import summarize


def run(paths,output):
    rows=[]
    for path in paths:
        raw=path.read_bytes();report=json.loads(raw)
        files=AnimatedStore(Path('workspace')).read(report['artifact_sha256'])
        rows.append(dict(job_id=report['job_id'],artifact_sha256=report['artifact_sha256'],
            skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
            report_sha256=sha256(raw).hexdigest(),source_identity=report['source_identity'],
            interpolation=report['interpolation'],spatial_sampling=report['spatial_sampling'],
            pixel_budget_used=report['pixel_budget_used'],causes=summarize(report['records'])))
    result=dict(profile='local-depth-cohort-evidence-v1',rows=rows,authority='none',selected=False,
                scope='exact_report_cause_inventory_not_full_motion_acceptance')
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([dict(job_id=r['job_id'],pairs=r['causes']['pairs']) for r in rows]))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path);parser.add_argument('reports',nargs='+',type=Path)
    args=parser.parse_args();run(args.reports,args.output)
