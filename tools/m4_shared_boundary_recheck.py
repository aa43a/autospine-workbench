"""Recheck frozen coherent ordering with opt-in common-boundary refinement."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.depth_shared_boundary import BoundaryProbe
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.motion_depth_order import build


def run(parent,observations_path,output):
    if output.exists() and any(output.iterdir()):raise ValueError('boundary_output_exists')
    raw=(parent/'report.json').read_bytes();receipt=json.loads(raw)
    frozen=json.loads(Path('docs/benchmark/m4-coherent-inference-evidence-v1.json').read_bytes())
    matches=[e for e in frozen['experiments'] if e['report_sha256']==sha256(raw).hexdigest()]
    if len(matches)!=1:raise ValueError('boundary_unregistered_parent')
    inference_raw=(parent/'inference.json').read_bytes()
    if sha256(inference_raw).hexdigest()!=matches[0]['inference_sha256']:raise ValueError('boundary_inference_identity')
    observations_raw=observations_path.read_bytes()
    if sha256(observations_raw).hexdigest()!=receipt['observations_sha256']:raise ValueError('boundary_observations_identity')
    observations=json.loads(observations_raw);models=json.loads(inference_raw)
    partition_raw=(parent/'partition.json').read_bytes()
    if sha256(partition_raw).hexdigest()!=receipt['partition_skeleton_sha256']:raise ValueError('boundary_partition_identity')
    document=json.loads(partition_raw);pairs=[]
    for region in receipt['partition']['regions']:
        arm=region['source_slot'];groups=models[arm]
        if isinstance(groups,list):
            bodies={r['body'] for r in observations[arm]}
            if len(bodies)!=1:raise ValueError('boundary_legacy_body_ambiguous')
            groups={next(iter(bodies)):groups}
        for body,frames in groups.items():
            samples=[]
            for frame in frames:
                values={frame['labels'][t] for t in region['triangles']}
                if len(values)!=1:raise ValueError('boundary_signature_changed')
                samples.append(dict(tick=frame['time']*1e6,source_tick=frame['source_tick'],
                    ambiguous=any(frame['observed_states'][t] in 'UM' for t in region['triangles']),
                    current_front_slot=region['slot'] if values.pop() else body))
            pairs.append(dict(arm_slot=region['slot'],torso_slot=body,evidence_source='regularized_proxy_inference',samples=samples))
    files=AnimatedStore(Path('workspace')).read(receipt['source_artifact_sha256'])
    probe=BoundaryProbe(Probe(document,files,'external-motion',tiled=True,sparse=True,rendered_bounds=True),receipt['partition'])
    candidate,order=build(document,'external-motion',dict(pairs=pairs),probe,refine_cycles=True)
    report=dict(profile='common-source-boundary-order-recheck-v1-experiment',
        source_artifact_sha256=receipt['source_artifact_sha256'],parent_report_sha256=sha256(raw).hexdigest(),
        inference_sha256=sha256(inference_raw).hexdigest(),observations_sha256=receipt['observations_sha256'],
        partition_skeleton_sha256=receipt['partition_skeleton_sha256'],original_failure_counts=receipt['failure_counts'],
        failure_counts=dict(Counter(f['reason_code'] for f in order['failures'])),order=order,
        boundary_refinements=probe.records,triangle_pairs_checked=probe.checked,triangle_pair_limit=probe.limit,
        triangle_pair_limit_reached=probe.limit_reached,pixel_budget_used=64_000_000-probe.remaining,
        authority='none',selected=False,runtime_recaptured=False,
        scope='sampled_common_boundary_refinement_not_visual_acceptance')
    output.mkdir(parents=True,exist_ok=True)
    if candidate is not None:
        data=canonical_bytes(candidate);(output/'skeleton.json').write_bytes(data)
        report['skeleton_sha256']=sha256(data).hexdigest()
    (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(failures=report['failure_counts'],refinements=len(probe.records),checked=probe.checked,
                         limit_reached=probe.limit_reached,candidate_emitted=candidate is not None)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('parent','observations','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();run(args.parent,args.observations,args.output)
