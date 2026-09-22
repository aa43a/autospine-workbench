"""Build and verify bounded render partitions from exact reach depth traces."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.targets.character43.depth_partition_coalesce import coalesced_labels
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.depth_partition_compact import compact
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import read,write
from autospine_workbench.targets.character43.deformation_qa import inspect
from m4_experiment_player_export import export


def run(source,trace_folder,output):
    output.mkdir(parents=True,exist_ok=False)
    receipt=json.loads((source/'report.json').read_bytes());digest=receipt['candidate_bundle_sha256']
    trace_report=json.loads((trace_folder/'report.json').read_bytes())
    if trace_report['candidate']!=digest or not trace_report['baked_torso_plane']:
        raise ValueError('trace_partition_source_mismatch')
    files=AnimatedStore(source/'isolated-store').read(digest);doc=json.loads(files['skeleton.json'])
    raw=(trace_folder/'triangle-traces.json').read_bytes();traces=json.loads(raw);selected={};reports={}
    depth=json.loads((trace_folder/'depth.json').read_bytes())
    for arm,rows in traces.items():
        expected=set()
        for pair in depth['pairs']:
            if pair['arm_slot']!=arm:continue
            for row in pair['samples']:
                expected.add((pair['torso_slot'],row['tick']/1e6))
                if row.get('interval_sample'):expected.add((pair['torso_slot'],row['interval_sample']['tick']/1e6))
        if len(rows)!=len(expected) or {(r['body'],r['time']) for r in rows}!=expected:
            raise ValueError('trace_partition_sample_inventory')
        if any(r['status']=='unmeasured' for r in rows):raise ValueError('trace_partition_unmeasured')
        for row in rows:row['triangles']={int(k):v for k,v in row['triangles'].items()}
        mesh=doc['skins'][0]['attachments'][arm][arm]
        selected[arm],reports[arm]=coalesced_labels(len(mesh['triangles'])//3,rows)
    required=sum(1+sum(a!=b for a,b in zip(v,v[1:])) for v in selected.values())
    report=dict(authority='none',selected=False,source_candidate_sha256=digest,
                trace_sha256=sha256(raw).hexdigest(),groups=reports,required_regions=required,part_limit=128,
                scope='lossless_render_partition_not_depth_order_or_visual_acceptance')
    (output/'trace-groups.json').write_bytes(canonical_bytes(report))
    if required>report['part_limit']:
        report.update(status='requires_representation_review',candidate_available=False,
                      reason='depth_partition_part_limit',runtime_status='not_evaluated')
        (output/'report.json').write_bytes(canonical_bytes(report))
        print(json.dumps(dict(status=report['status'],required_regions=required,
                              part_limit=report['part_limit'],candidate_available=False)),flush=True)
        return
    candidate,partition=compact(*build(doc,sorted(selected),triangle_labels=selected,part_limit=128))
    original_reference=read(files)
    if original_reference['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest():
        raise ValueError('trace_partition_reference_mismatch')
    times=[r['time'] for r in original_reference['animations']['external-motion']]
    regions={r['slot']:r for r in partition['regions']};frames=[]
    for t in times:
        before=sample(doc,'external-motion',t)[0];after=sample(candidate,'external-motion',t)[0]
        for slot,points in after.items():
            region=regions.get(slot)
            expected=[before[region['source_slot']][v] for v in region['source_vertex_indices']] if region else before[slot]
            if points!=expected:raise ValueError('trace_partition_deformation_changed')
        frames.append(dict(time=t,vertices=after))
    raw=canonical_bytes(candidate);isolated={n:v for n,v in files.items() if n.endswith('.png') or n in ('skeleton.atlas','character-manifest.json')}
    isolated['skeleton.json']=raw;isolated['render-partition.json']=canonical_bytes(partition)
    isolated=write(isolated,dict(skeleton_sha256=sha256(raw).hexdigest(),animations={'external-motion':frames}))
    setup=sample(dict(candidate,animations={'setup':{}}),'setup',0)[0]
    qa=inspect(isolated,setup_vertices=setup)
    isolated['rig-setup-reference.json']=canonical_bytes(dict(time=0,vertices=setup,skeleton_sha256=sha256(raw).hexdigest()))
    store=AnimatedStore(output/'isolated-store');address=store.publish(isolated)
    report.update(candidate_bundle_sha256=address,geometry_passed=qa['passed'],sampled_frames=len(times),
                  maximum_vertex_error_px=0,draw_order_status='unchanged',runtime_status='not_evaluated')
    (output/'report.json').write_bytes(canonical_bytes(report));(output/'deformation.json').write_bytes(canonical_bytes(qa))
    print(json.dumps(dict(regions=required,frames=len(times),geometry=qa['passed'])),flush=True)
    result=capture(SimpleNamespace(workspace_root=Path.cwd().parent),store,address,output,
        progress=lambda s:print(s,flush=True),cancel_requested=lambda:False,storage_reference=True)
    report['runtime_status']=result['status'];(output/'report.json').write_bytes(canonical_bytes(report));export(output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','trace_folder','output'):p.add_argument(name,type=Path)
    a=p.parse_args();run(a.source,a.trace_folder,a.output)
