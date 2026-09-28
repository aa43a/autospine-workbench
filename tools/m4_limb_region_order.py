"""Try distal-region order constraints; preserve unknown visible attachments."""
import argparse
from collections import Counter,defaultdict
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.motion_depth_order import build


DISTAL={'forearm','hand','transition:forearm,hand'}


def constraints(diagnosis, partition, source_depth):
    groups={r['slot']:r for r in partition['regions']};indexed=defaultdict(list)
    for row in diagnosis['rows']:
        region=groups.get(row['region'])
        if not region or row['source_slot']!=region['source_slot'] or row['group']!=region['group']:
            raise ValueError('region_order_group_identity')
        if row['group'] in DISTAL:indexed[row['region'],row['body']].append(row)
    pairs=[]
    for region in partition['regions']:
        if region['group'] not in DISTAL:continue
        slot=region['slot']
        for parent in source_depth['pairs']:
            if parent['arm_slot']!=region['source_slot']:continue
            rows=sorted(indexed.pop((slot,parent['torso_slot']),[]),key=lambda r:r['time'])
            original=parent['samples'];expected=[(r['tick']/1e6,r['source_tick']) for r in original]
            expected += [((a['tick']+b['tick'])/2e6,(a['source_tick']+b['source_tick'])/2)
                         for a,b in zip(original,original[1:])]
            if len(rows)!=len(expected) or any(abs(r['time']-t)>1e-12 or r['source_tick']!=s
                                              for r,(t,s) in zip(rows,sorted(expected))):
                raise ValueError('region_order_missing_same_time_evidence')
            samples=[]
            for row in rows:
                status=row['status']
                samples.append(dict(tick=row['time']*1e6,source_tick=row['source_tick'],
                    ambiguous=status not in ('no_overlap','uniform_front_proxy','uniform_back_proxy'),
                    support='no_overlap' if status=='no_overlap' else 'sampled',
                    current_front_slot=parent['torso_slot'] if status=='uniform_back_proxy' else slot))
            for i in range(0,len(samples)-1,2):samples[i]['interval_sample']=samples[i+1]
            pairs.append(dict(arm_slot=slot,torso_slot=parent['torso_slot'],samples=samples[::2],
                              evidence_source='same_frame_distal_region_proxy'))
    if indexed or not pairs:raise ValueError('region_order_pair_inventory')
    return dict(pairs=pairs,strict_interval_evidence=True)


def run(source, partition, diagnostic, output, refine_cycles=False, neck_hypothesis=None, skirt_hypothesis=None):
    if output.exists():raise ValueError('output_exists')
    digest=json.loads((source/'report.json').read_bytes())['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(digest)
    proof=json.loads((partition/'report.json').read_bytes());raw=(partition/'skeleton.json').read_bytes()
    diagnosis=json.loads(diagnostic.read_bytes())
    if (proof['source_artifact_sha256']!=digest or diagnosis['source_artifact_sha256']!=digest
            or proof['skeleton_sha256']!=sha256(raw).hexdigest()
            or diagnosis['skeleton_sha256']!=sha256(raw).hexdigest()):raise ValueError('region_order_identity')
    document=json.loads(raw);depth=constraints(diagnosis,proof['partition'],json.loads(files['motion-depth.json']))
    hypotheses={k:p for k,p in (('neck',neck_hypothesis),('skirt',skirt_hypothesis)) if p is not None}
    for kind,path in hypotheses.items():
        from m4_neck_order_evidence import convert
        neck=json.loads(path.read_bytes())
        if neck['source_artifact_sha256']!=digest or neck['skeleton_sha256']!=sha256(raw).hexdigest():
            raise ValueError('neck_hypothesis_identity')
        depth['pairs'].extend(convert(neck,proof['partition'],json.loads(files['motion-depth.json']),kind=kind))
    probe=Probe(document,files,'external-motion',rendered_bounds=True,tiled=True,sparse=True)
    candidate,order=build(document,'external-motion',depth,probe,refine_cycles=refine_cycles)
    result=dict(source_artifact_sha256=digest,input_skeleton_sha256=sha256(raw).hexdigest(),
        diagnostic_sha256=sha256(diagnostic.read_bytes()).hexdigest(),order=order,
        selected_groups=sorted(DISTAL),candidate_available=candidate is not None,
        authority='none',selected=False,scope='partial_distal_order_trial_not_full_depth_or_visual_acceptance')
    if hypotheses:
        result.update(hypothesis_sha256={k:sha256(p.read_bytes()).hexdigest() for k,p in hypotheses.items()},
                      scope='hypothetical_surface_depth_order_trial_not_admissible_without_surface_validation')
    output.mkdir(parents=True,exist_ok=False)
    (output/'report.json').write_bytes(canonical_bytes(result))
    if candidate is not None:(output/'skeleton.json').write_bytes(canonical_bytes(candidate))
    print(json.dumps(dict(candidate_available=candidate is not None,failures=dict(Counter(
        r['reason_code'] for r in order['failures'])))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','partition','diagnostic','output'):p.add_argument(key,type=Path)
    p.add_argument('--refine-cycles',action='store_true')
    p.add_argument('--neck-hypothesis',type=Path)
    p.add_argument('--skirt-hypothesis',type=Path)
    a=p.parse_args();run(a.source,a.partition,a.diagnostic,a.output,a.refine_cycles,a.neck_hypothesis,a.skirt_hypothesis)
