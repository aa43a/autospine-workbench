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
from autospine_workbench.targets.character43.depth_region_constraints import build as constraints,PROFILE as CONSTRAINT_PROFILE


def run(parent,output,shared_boundaries=False,surface_routing=False,shared_planes=False,interval_depth=False,temporal_labels=False):
    if output.exists() and any(output.iterdir()):raise ValueError('coherent_output_exists')
    receipt_raw=(parent/'report.json').read_bytes();receipt=json.loads(receipt_raw);raw=(parent/'observations.json').read_bytes()
    if sha256(raw).hexdigest()!=receipt.get('observations_sha256'):raise ValueError('coherent_observations_identity')
    observations=json.loads(raw);files=AnimatedStore(Path('workspace')).read(receipt['source_artifact_sha256'])
    source=json.loads(files['skeleton.json']);rank={s['name']:i for i,s in enumerate(source['slots'])}
    held=[]
    if surface_routing:
        from autospine_workbench.targets.character43.depth_surface_inventory import build as inventory_build,route
        if receipt.get('inventory')!=inventory_build(source):raise ValueError('coherent_surface_inventory_identity')
        observations,held=route(observations,receipt['inventory'])
    checks=[];coupling=[];temporal=[]
    if shared_planes:
        check_raw=(parent/'checks.json').read_bytes()
        if sha256(check_raw).hexdigest()!=receipt.get('checks_sha256'):raise ValueError('coherent_checks_identity')
        checks=json.loads(check_raw)
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
        if shared_planes:
            from autospine_workbench.targets.character43.depth_plane_coupling import couple
            setup={body:rank[arm]>rank[body] for body in models[arm]}
            coupling.extend(dict(row,arm=arm) for row in couple(mesh,models[arm],checks,arm,setup))
        if temporal_labels:
            from autospine_workbench.targets.character43.depth_temporal_labels import stabilize
            result=stabilize(mesh,models[arm],checks,arm,{b:rank[arm]>rank[b] for b in models[arm]})
            temporal.append(dict(result,arm=arm));print(json.dumps(temporal[-1]),flush=True)
        signatures=[''.join(str(frame['labels'][i]) for frames in models[arm].values() for frame in frames)
                    for i in range(len(mesh['triangles'])//3)]
        labels[arm]=['model-'+sha256(signature.encode()).hexdigest() for signature in signatures]
    partitioned,partition=partition_build(source,sorted(labels),triangle_labels=labels,part_limit=512)
    partitioned,partition=compact(partitioned,partition)
    from autospine_workbench.targets.character43.depth_region_bounds import SampledRegionBounds
    bounds=SampledRegionBounds(r['slot'] for r in partition['regions']) if interval_depth else None
    for time in sorted(times):
        before=sample(source,'external-motion',time)[0];after=sample(partitioned,'external-motion',time)[0]
        if bounds is not None:bounds.record(time,after)
        for region in partition['regions']:
            if [before[region['source_slot']][i] for i in region['source_vertex_indices']]!=after[region['slot']]:
                raise ValueError('coherent_partition_geometry_changed')
    if interval_depth and receipt.get('source_subdivisions')!=4:raise ValueError('interval_depth_quarter_trace_required')
    pruning={};pairs=constraints(partition,models,interval_depth=interval_depth,diagnostics=pruning,
                                overlap_possible=bounds.possible if bounds is not None else None)
    probe=Probe(partitioned,files,'external-motion',tiled=True,sparse=True,rendered_bounds=True)
    if shared_boundaries:
        from autospine_workbench.targets.character43.depth_shared_boundary import BoundaryProbe
        probe=BoundaryProbe(probe,partition)
    candidate,order=order_build(partitioned,'external-motion',dict(pairs=pairs,strict_interval_evidence=interval_depth),probe,refine_cycles=True)
    output.mkdir(parents=True,exist_ok=True);partition_raw=canonical_bytes(partitioned)
    (output/'partition.json').write_bytes(partition_raw)
    (output/'inference.json').write_bytes(canonical_bytes(models))
    report=dict(profile=PROFILE,source_artifact_sha256=receipt['source_artifact_sha256'],
        parent_report_sha256=sha256(receipt_raw).hexdigest(),supplemental_models=receipt.get('supplemental_models',[]),
        observations_sha256=receipt['observations_sha256'],partition_skeleton_sha256=sha256(partition_raw).hexdigest(),
        partition=partition,observed_state_counts=dict(counts),sampled_frames=len(times),max_vertex_error=0,order=order,
        relation_pair_count=len(pairs),relation_sample_count=sum(len(p['samples']) for p in pairs),
        constraint_profile=CONSTRAINT_PROFILE,strict_interval_evidence=interval_depth,relation_pruning=pruning,
        surface_routing=surface_routing,held_setup_pairs=held,shared_plane_coupling=coupling,temporal_stabilization=temporal,
        failure_counts=dict(Counter(f['reason_code'] for f in order['failures'])),
        pixel_budget_used=64_000_000-probe.remaining,authority='none',selected=False,
        scope='regularized_inference_with_held_unresolved_regions_not_depth_truth_or_visual_acceptance')
    if shared_boundaries:
        report['shared_boundary_refinement']=dict(records=probe.records,triangle_pairs_checked=probe.checked,
                                                limit_reached=probe.limit_reached)
    if candidate is not None:
        encoded=canonical_bytes(candidate);(output/'skeleton.json').write_bytes(encoded)
        report['skeleton_sha256']=sha256(encoded).hexdigest()
    (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(regions=len(partition['regions']),order_status=order['status'],failures=report['failure_counts'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('parent',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--shared-boundaries',action='store_true')
    parser.add_argument('--surface-routing',action='store_true')
    parser.add_argument('--shared-planes',action='store_true')
    parser.add_argument('--interval-depth',action='store_true')
    parser.add_argument('--temporal-labels',action='store_true')
    args=parser.parse_args();run(args.parent,args.output,args.shared_boundaries,args.surface_routing,args.shared_planes,args.interval_depth,args.temporal_labels)
