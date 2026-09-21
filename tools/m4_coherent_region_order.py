"""Build a source-bound coherent region/order experiment, retaining abstentions."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.depth_coherent_frame import infer,PROFILE
from autospine_workbench.targets.character43.depth_region_partition import build as partition_build
from autospine_workbench.targets.character43.depth_partition_compact import compact
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.motion_depth_order import build as order_build
from autospine_workbench.targets.character43.affine_pose import sample


def run(parent,output):
    if output.exists() and any(output.iterdir()):raise ValueError('coherent_output_exists')
    receipt=json.loads((parent/'report.json').read_bytes());raw=(parent/'observations.json').read_bytes()
    if sha256(raw).hexdigest()!=receipt.get('observations_sha256'):raise ValueError('coherent_observations_identity')
    observations=json.loads(raw);files=AnimatedStore(Path('workspace')).read(receipt['source_artifact_sha256'])
    source=json.loads(files['skeleton.json']);rank={s['name']:i for i,s in enumerate(source['slots'])}
    models={};labels={};counts=Counter();times=set()
    for arm,rows in observations.items():
        mesh=source['skins'][0]['attachments'][arm][arm];models[arm]={}
        for body in sorted({r['body'] for r in rows}):
            selected=[r for r in rows if r['body']==body]
            setup_front=rank[arm]>rank[body];previous=[int(setup_front)]*(len(mesh['triangles'])//3)
            frames=[]
            if any(b['time']<=a['time'] for a,b in zip(selected,selected[1:])):raise ValueError('coherent_sample_order')
            for row in selected:
                result=infer(mesh,row,previous,setup_front);previous=result['labels'];times.add(row['time'])
                frames.append(dict(result,time=row['time'],source_tick=row['source_tick']))
                counts.update(result['state_counts'])
            models[arm][body]=frames
            print(json.dumps(dict(arm=arm,body=body,frames=len(frames),inferred=sum(len(f['inferred_triangles']) for f in frames))),flush=True)
        signatures=[''.join(str(frame['labels'][i]) for frames in models[arm].values() for frame in frames)
                    for i in range(len(mesh['triangles'])//3)]
        labels[arm]=['model-'+sha256(signature.encode()).hexdigest() for signature in signatures]
    partitioned,partition=partition_build(source,sorted(labels),triangle_labels=labels,part_limit=512)
    partitioned,partition=compact(partitioned,partition)
    for time in sorted(times):
        before=sample(source,'external-motion',time)[0];after=sample(partitioned,'external-motion',time)[0]
        for region in partition['regions']:
            if [before[region['source_slot']][i] for i in region['source_vertex_indices']]!=after[region['slot']]:
                raise ValueError('coherent_partition_geometry_changed')
    pairs=[]
    for region in partition['regions']:
        arm=region['source_slot']
        for body,frames in models[arm].items():
            samples=[]
            for frame in frames:
                values={frame['labels'][t] for t in region['triangles']}
                if len(values)!=1:raise ValueError('coherent_partition_signature_changed')
                unresolved=any(frame['observed_states'][t] in 'UM' for t in region['triangles'])
                samples.append(dict(tick=frame['time']*1e6,source_tick=frame['source_tick'],ambiguous=unresolved,
                    current_front_slot=region['slot'] if values.pop() else body))
            pairs.append(dict(arm_slot=region['slot'],torso_slot=body,evidence_source='regularized_proxy_inference',samples=samples))
    probe=Probe(partitioned,files,'external-motion',tiled=True,sparse=True,rendered_bounds=True)
    candidate,order=order_build(partitioned,'external-motion',dict(pairs=pairs),probe,refine_cycles=True)
    output.mkdir(parents=True,exist_ok=True);partition_raw=canonical_bytes(partitioned)
    (output/'partition.json').write_bytes(partition_raw)
    (output/'inference.json').write_bytes(canonical_bytes(models))
    report=dict(profile=PROFILE,source_artifact_sha256=receipt['source_artifact_sha256'],
        observations_sha256=receipt['observations_sha256'],partition_skeleton_sha256=sha256(partition_raw).hexdigest(),
        partition=partition,observed_state_counts=dict(counts),sampled_frames=len(times),max_vertex_error=0,order=order,
        failure_counts=dict(Counter(f['reason_code'] for f in order['failures'])),
        pixel_budget_used=64_000_000-probe.remaining,authority='none',selected=False,
        scope='regularized_inference_with_held_unresolved_regions_not_depth_truth_or_visual_acceptance')
    if candidate is not None:
        encoded=canonical_bytes(candidate);(output/'skeleton.json').write_bytes(encoded)
        report['skeleton_sha256']=sha256(encoded).hexdigest()
    (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(regions=len(partition['regions']),order_status=order['status'],failures=report['failure_counts'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('parent',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();run(args.parent,args.output)
