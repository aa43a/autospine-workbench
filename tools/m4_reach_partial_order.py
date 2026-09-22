"""Guard local render-region order experiments while preserving unresolved samples."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.motion_depth_order import build


def pair_samples(region, signature, original):
    if len(signature)!=2*len(original)-1:raise ValueError('partial_signature_schedule')
    samples=[]; unresolved=[]
    for i,row in enumerate(original):
        chars=signature[2*i:2*i+2]
        if any(c not in 'FBN' for c in chars) or ('F' in chars and 'B' in chars):
            unresolved.append(dict(slot=region['slot'],tick=row['tick'],states=chars));continue
        def evidence(char,tick):
            return dict(tick=tick,ambiguous=False,support={'F':'uniform_front_proxy','B':'uniform_back_proxy','N':'no_overlap'}[char],
                        current_front_slot=region['slot'] if char=='F' else original_body)
        original_body=region['body'];entry=evidence(chars[0],row['tick'])
        if i+1<len(original):entry['interval_sample']=evidence(chars[1],(row['tick']+original[i+1]['tick'])/2)
        samples.append(entry)
    return samples,unresolved


def run(source,traces,output):
    receipt=json.loads((source/'report.json').read_bytes());digest=receipt['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(digest);document=json.loads(files['skeleton.json'])
    partition=json.loads(files['render-partition.json']);depth=json.loads((traces/'depth.json').read_bytes())
    trace_raw=(traces/'triangle-traces.json').read_bytes()
    if (depth['candidate_bundle_sha256']!=receipt['source_candidate_sha256'] or
            sha256(trace_raw).hexdigest()!=receipt['trace_sha256']):
        raise ValueError('partial_order_parent_mismatch')
    pairs=[];unresolved=[];ticks=None
    for region in partition['regions']:
        source_slot=region['source_slot'];original=[p for p in depth['pairs'] if p['arm_slot']==source_slot]
        if len(original)!=1:raise ValueError('partial_order_unique_pair')
        original=original[0];schedule=[s['tick'] for s in original['samples']]
        if ticks is not None and ticks!=schedule:raise ValueError('partial_order_schedule_mismatch')
        ticks=schedule;signature=receipt['groups'][source_slot]['groups'][region['group']]
        samples,missing=pair_samples(dict(region,body=original['torso_slot']),signature,original['samples'])
        pairs.append(dict(arm_slot=region['slot'],torso_slot=original['torso_slot'],samples=samples,
                          evidence_source='consecutive_compatible_source_triangle_trace'))
        unresolved.extend(missing)
    probe=Probe(document,files,'external-motion',tiled=True,rendered_bounds=True,sparse='priority_depth_points')
    candidate,report=build(document,'external-motion',dict(pairs=pairs,strict_interval_evidence=True),probe,
                           refine_cycles=True,evaluation_ticks=ticks)
    report.update(parent=digest,authority='none',selected=False,unresolved=unresolved,
                  candidate_available=candidate is not None,untouched_source_slots=receipt['untouched_source_slots'])
    output.mkdir(parents=True,exist_ok=False);(output/'report.json').write_bytes(canonical_bytes(report))
    if candidate is not None:(output/'skeleton-candidate.json').write_bytes(canonical_bytes(candidate))
    print(json.dumps(dict(candidate=candidate is not None,keys=len(report['frames']),unresolved=len(unresolved),
                          failures=dict(Counter(f['reason_code'] for f in report['failures'])))),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','traces','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();run(args.source,args.traces,args.output)
