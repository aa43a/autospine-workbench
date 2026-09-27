"""Bridge a locally checked boundary curve into the existing bounded Runtime audit."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.numeric_reference import read
from m4_transverse_sampling_probe import inventory

PROFILE='joint-boundary-runtime-input-v1'


def validate(original,raw,report,times):
    source=report['boundary_report']
    if (source.get('profile')!='joint-boundary-animation-v1-experiment' or
            source.get('local_constraints_passed') is not True or source.get('failures')!=[] or
            source.get('solver_failures')!=[] or source.get('authority')!='none' or
            source.get('selected') is not False or source.get('production_authorized') is not False or
            source['slot']!=report['slot'] or source['parent_artifact_sha256']!=report['parent_artifact_sha256'] or
            source['skeleton_sha256']!=sha256(raw).hexdigest() or
            sha256(canonical_bytes(source)).hexdigest()!=report['boundary_report_sha256']):
        raise ValueError('boundary_runtime_local_evidence')
    expected=inventory(json.loads(raw),'external-motion',
        [r['time'] for r in read(original)['animations']['external-motion']])['times']
    if times!=sorted(set(source['times'])|set(expected)):
        raise ValueError('boundary_runtime_missing_times')


def run(state,source,output):
    raw=(source/'skeleton.json').read_bytes();source_raw=(source/'report.json').read_bytes()
    evidence=json.loads(source_raw);original=AnimatedStore(state).read(evidence['parent_artifact_sha256'])
    times=sorted(set(evidence['times'])|set(inventory(json.loads(raw),'external-motion',
        [r['time'] for r in read(original)['animations']['external-motion']])['times']))
    report=dict(profile=PROFILE,boundary_report=evidence,boundary_report_sha256=sha256(canonical_bytes(evidence)).hexdigest(),
        original_report_sha256=sha256(source_raw).hexdigest(),slot=evidence['slot'],
        parent_artifact_sha256=evidence['parent_artifact_sha256'],skeleton_sha256=sha256(raw).hexdigest(),
        times_sha256=sha256(canonical_bytes(times)).hexdigest(),authority='none',selected=False,production_authorized=False)
    from m4_transverse_batch_validation import verify_diagnostic
    verify_diagnostic(original,raw,report,times)
    output.mkdir(parents=True,exist_ok=False)
    for name,value in [('report.json',canonical_bytes(report)),('solved-diagnostic.json',raw),
                       ('validation-times.json',canonical_bytes(times))]:
        (output/name).write_bytes(value)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('state','source','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();run(args.state,args.source,args.output)
