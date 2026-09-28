"""Compile verified surface observations together with existing distal constraints."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.depth_surface_inventory import build as inventory_build
from autospine_workbench.targets.character43.surface_order_evidence import build as evidence,merge
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.motion_depth_order import build
from m4_limb_region_order import constraints
from m4_region_surface_audit import verify


def run(source,partition,diagnostic,surfaces,output):
    if output.exists():raise ValueError('output_exists')
    digest=json.loads((source/'report.json').read_bytes())['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(digest)
    raw=(partition/'skeleton.json').read_bytes();doc=json.loads(raw)
    proof=json.loads((partition/'report.json').read_bytes());old=json.loads(diagnostic.read_bytes())
    surface_raw=(surfaces/'report.json').read_bytes();report=json.loads(surface_raw)
    audit=json.loads((surfaces/'coverage-audit.json').read_bytes())
    if (any(r['source_artifact_sha256']!=digest for r in (proof,old,report,audit))
            or any(r['skeleton_sha256']!=sha256(raw).hexdigest() for r in (proof,old,report))
            or proof['source_skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest()
            or audit['report_sha256']!=sha256(surface_raw).hexdigest()
            or report['inventory']!=inventory_build(doc)):
        raise ValueError('surface_order_identity')
    depth=json.loads(files['motion-depth.json']);schedule=None
    for pair in depth['pairs']:
        current=[(r['tick'],r['source_tick']) for r in pair['samples']]
        if schedule is not None and current!=schedule:raise ValueError('surface_order_source_times')
        schedule=current
    if not schedule:raise ValueError('surface_order_source_times')
    times=sorted([(t/1e6,s) for t,s in schedule]+[((a[0]+b[0])/2e6,(a[1]+b[1])/2)
        for a,b in zip(schedule,schedule[1:])])
    groups={r['slot'] for r in proof['partition']['regions']};checks=[]
    if not set(report['regions'])<=groups:raise ValueError('surface_order_region_identity')
    for region in report['regions']:
        data=(surfaces/(region+'.json')).read_bytes()
        if sha256(data).hexdigest()!=audit['checkpoint_sha256'][region]:raise ValueError('surface_order_checkpoint_identity')
        checks.extend(json.loads(data))
    verified=verify(report,checks,times)
    supplement=evidence(report['inventory'],checks,times)
    combined=merge(constraints(old,proof['partition'],depth),supplement)
    probe=Probe(doc,files,'external-motion',rendered_bounds=True,tiled=True,sparse=True)
    candidate,order=build(doc,'external-motion',combined,probe,refine_cycles=True)
    result=dict(source_artifact_sha256=digest,input_skeleton_sha256=sha256(raw).hexdigest(),
        surface_report_sha256=sha256(surface_raw).hexdigest(),coverage=verified,
        added_evidence=supplement,order=order,candidate_available=candidate is not None,
        scope='known_surface_constraints_with_unknown_setup_holds_not_full_depth_or_visual_acceptance',
        authority='none',selected=False)
    output.mkdir(parents=True,exist_ok=False)
    (output/'report.json').write_bytes(canonical_bytes(result))
    if candidate is not None:(output/'skeleton.json').write_bytes(canonical_bytes(candidate))
    print(json.dumps(dict(pairs=len(combined['pairs']),supplement_pairs=len(supplement['pairs']),
        held=len(supplement['held']),candidate_available=candidate is not None,
        failures=dict(Counter(r['reason_code'] for r in order['failures'])))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','partition','diagnostic','surfaces','output'):p.add_argument(key,type=Path)
    a=p.parse_args();run(a.source,a.partition,a.diagnostic,a.surfaces,a.output)
