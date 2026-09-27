"""Recheck Runtime-normalized curves without rerunning or hiding solver changes."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.joint_boundary_animation import inspect
from autospine_workbench.targets.character43.limb_transverse_repair import build
from m4_transverse_batch_validation import normalized_diagnostic


def represent(parent,compensation,result,slot,representation):
    if representation not in ('source-origin','normalized-origin','runtime-storage'):
        raise ValueError('boundary_audit_representation')
    origin_normalization=None
    if representation!='source-origin':
        from autospine_workbench.targets.character43.deform_time_aliases import normalize
        compensation,origin_normalization=normalize(compensation,parent,'external-motion',slot)
    if representation=='runtime-storage':
        from autospine_workbench.targets.character43.runtime_storage_reference import stored_document
        parent=stored_document(parent);compensation=stored_document(compensation);result=stored_document(result)
    return parent,compensation,result,origin_normalization


def run(state,probe,output,representation='source-origin'):
    receipt_raw=(probe/'report.json').read_bytes();receipt=json.loads(receipt_raw)
    source_raw=(probe/'solved-diagnostic.json').read_bytes()
    original=AnimatedStore(state).read(receipt['parent_artifact_sha256'])
    times=json.loads((probe/'validation-times.json').read_bytes())
    raw,times,normalization=normalized_diagnostic(original,source_raw,receipt,times)
    parent=json.loads(original['skeleton.json']);source=json.loads(source_raw);slot=receipt['slot']
    keys=source['animations']['external-motion']['attachments']['default'][slot][slot]['deform']
    compensation,evidence=build(parent,'external-motion',[slot],correction_frame='transverse',
        anchor_terminal=True,required_times=[k['time'] for k in keys])
    parent,compensation,result,origin_normalization=represent(parent,compensation,json.loads(raw),slot,representation)
    output.mkdir(parents=True,exist_ok=False)
    def progress(row):
        (output/'progress.json').write_bytes(canonical_bytes(row));print(json.dumps(row),flush=True)
    report=inspect(parent,compensation,result,'external-motion',slot,times,progress=progress)
    report.update(parent_artifact_sha256=receipt['parent_artifact_sha256'],slot=slot,
        skeleton_sha256=sha256(raw).hexdigest(),source_skeleton_sha256=sha256(source_raw).hexdigest(),
        probe_sha256=sha256(receipt_raw).hexdigest(),normalization=normalization,
        compensation_sha256=sha256(canonical_bytes(compensation)).hexdigest(),compensation=evidence)
    report.update(representation=representation,origin_normalization=origin_normalization,
        evaluated_skeleton_sha256=sha256(canonical_bytes(result)).hexdigest(),
        evaluated_parent_sha256=sha256(canonical_bytes(parent)).hexdigest())
    (output/'report.json').write_bytes(canonical_bytes(report))
    (output/'skeleton.json').write_bytes(raw)
    print(json.dumps(dict(passed=report['local_constraints_passed'],failures=len(report['failures']),samples=len(report['times']))),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('state','probe','output'):parser.add_argument(name,type=Path)
    parser.add_argument('--representation',choices=['source-origin','normalized-origin','runtime-storage'],default='source-origin')
    args=parser.parse_args();run(args.state,args.probe,args.output,args.representation)
