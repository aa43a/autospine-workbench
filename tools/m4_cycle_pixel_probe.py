"""Source-bound same-frame localization of frozen ordering-cycle witnesses."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.depth_cycle_pixels import analyze
from m4_cycle_pixel_review import image,write


def run(parent,recheck,output):
    if output.exists() and any(output.iterdir()):raise ValueError('cycle_pixels_output_exists')
    raw=(recheck/'report.json').read_bytes();report=json.loads(raw)
    frozen=json.loads(Path('docs/benchmark/m4-shared-boundary-evidence-v1.json').read_bytes())
    if not any(r['report_sha256']==sha256(raw).hexdigest() for r in frozen['experiments']):
        raise ValueError('cycle_pixels_unregistered_report')
    parent_raw=(parent/'report.json').read_bytes()
    if sha256(parent_raw).hexdigest()!=report['parent_report_sha256']:raise ValueError('cycle_pixels_parent_identity')
    partition_raw=(parent/'partition.json').read_bytes()
    if sha256(partition_raw).hexdigest()!=report['partition_skeleton_sha256']:raise ValueError('cycle_pixels_partition_identity')
    document=json.loads(partition_raw);files=AnimatedStore(Path('workspace')).read(report['source_artifact_sha256'])
    rows=[];skipped=Counter();output.mkdir(parents=True,exist_ok=True)
    for failure in report['order']['failures']:
        if failure['reason_code']!='visible_unmapped_order_conflict':
            skipped[failure['reason_code']]+=1;continue
        cycle=failure['conflict']
        times=sorted({failure['time']}|{e['overlap']['time'] for e in cycle['edges'] if e.get('overlap')})
        for time in times:
            try:row,visual=analyze(document,files,'external-motion',cycle,time)
            except ValueError as error:
                row=dict(time=time,status='unmeasured',reason_code=str(error),slots=cycle['slots'][:-1],edges=cycle['edges']);visual=None
            row['order_failure_time']=failure['time']
            if visual is not None:image(output,len(rows),row,visual)
            rows.append(row)
    result=dict(profile='source-bound-cycle-pixels-v1',source_artifact_sha256=report['source_artifact_sha256'],
        order_report_sha256=sha256(raw).hexdigest(),partition_skeleton_sha256=report['partition_skeleton_sha256'],
        rows=rows,status_counts=dict(Counter(r['status'] for r in rows)),skipped_failures=dict(skipped),
        authority='none',selected=False,runtime_recaptured=False,candidate_emitted=False,
        scope='reported_simple_cycles_at_failure_and_edge_witness_times_only')
    (output/'report.json').write_bytes(canonical_bytes(result));write(output,rows)
    print(json.dumps(dict(rows=len(rows),status_counts=result['status_counts'],skipped=dict(skipped))),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('parent','recheck','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();run(args.parent,args.recheck,args.output)
