"""Capture an isolated ordering candidate after checking its only edit is order."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from m4_depth_region_capture import prepare
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.sleeve_capture_environment import discover


def verify(partition,ordering):
    partition_report=json.loads((partition/'report.json').read_bytes())
    base_raw=(partition/'skeleton.json').read_bytes(); base=json.loads(base_raw)
    report=json.loads(ordering.read_bytes()); raw=ordering.with_suffix('.skeleton.json').read_bytes()
    candidate=json.loads(raw)
    if (sha256(base_raw).hexdigest()!=partition_report['skeleton_sha256'] or
            report['artifact_sha256']!=partition_report['source_artifact_sha256'] or
            not report['candidate_available'] or report['order']['failures']):
        raise ValueError('order_capture_identity')
    expected=deepcopy(base); slots=[s['name'] for s in base['slots']]; keys=[]
    for row in report['order']['frames']:
        order=row['order']
        if sorted(order)!=sorted(slots): raise ValueError('order_capture_slot_inventory')
        keys.append(dict(time=row['time'],offsets=[dict(slot=s,offset=order.index(s)-i) for i,s in enumerate(slots)]))
    if keys: expected['animations']['external-motion']['drawOrder']=keys
    if candidate!=expected: raise ValueError('order_capture_unexpected_edit')
    for name in ('cloth_constraints','limb_constraints'):
        if (report.get(name) or {}).get('unmeasured_samples',0): raise ValueError('order_capture_unmeasured')
    return raw,report


def run(partition,ordering,output):
    raw,report=verify(partition,ordering)
    output.mkdir(parents=True,exist_ok=True); staging=output/'candidate-input'; staging.mkdir(exist_ok=True)
    (staging/'skeleton.json').write_bytes(raw)
    (staging/'report.json').write_bytes(canonical_bytes(dict(source_artifact_sha256=report['artifact_sha256'],
        skeleton_sha256=sha256(raw).hexdigest())))
    captures=prepare(staging,output); options=discover(Path.cwd().parent)
    if not options: raise ValueError('official_capture_environment_missing')
    (output/'capture-inputs.json').write_bytes(canonical_bytes(captures))
    for row in captures:
        command=['node','tools/capture-character-runtime.mjs',row['bundle'],str(output/row['name']),
                 options[1],options[3],'1','{}',row['storage']]
        with (output/(row['name']+'.log')).open('wb') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=300,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode: raise ValueError('order_capture_failed_'+row['name'])
        print(json.dumps(dict(captured=row['name'],bundle=row['bundle_sha256'])),flush=True)
    (output/'provenance.json').write_bytes(canonical_bytes(dict(authority='none',selected=False,
        ordering_sha256=sha256(ordering.read_bytes()).hexdigest(),candidate_sha256=sha256(raw).hexdigest(),
        source_artifact_sha256=report['artifact_sha256'],scope='sampled_official_capture_not_visual_acceptance')))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('partition',type=Path); parser.add_argument('ordering',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args(); run(args.partition,args.ordering,args.output)
