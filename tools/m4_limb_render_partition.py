"""Lossless limb render regions on an exact isolated motion candidate."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.limb_influence_regions import classify
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.depth_partition_compact import compact
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import read


def run(source, output, slots):
    if output.exists():raise ValueError('output_exists')
    digest=json.loads((source/'report.json').read_bytes())['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(digest)
    document=json.loads(files['skeleton.json']);reference=read(files)
    if reference['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest():
        raise ValueError('partition_reference_identity')
    labels={};classification={}
    for name,side in slots.items():
        slot=next(s for s in document['slots'] if s['name']==name)
        mesh=document['skins'][0]['attachments'][name][slot['attachment']]
        labels[name],classification[name]=classify(document,mesh,side)
    candidate,partition=compact(*build(document,sorted(slots),triangle_labels=labels,
                                       preserve_draw_order=True))
    regions={r['slot']:r for r in partition['regions']};checked=0
    for animation,frames in reference['animations'].items():
        for frame in frames:
            before=sample(document,animation,frame['time'])[0]
            after=sample(candidate,animation,frame['time'])[0]
            for slot,points in after.items():
                region=regions.get(slot)
                expected=([before[region['source_slot']][i] for i in region['source_vertex_indices']]
                          if region else before[slot])
                if points!=expected:raise ValueError('partition_deformation_changed')
            checked+=1
    raw=canonical_bytes(candidate)
    report=dict(profile='limb-influence-render-partition-probe-v1',source_artifact_sha256=digest,
        source_skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
        skeleton_sha256=sha256(raw).hexdigest(),classification=classification,partition=partition,
        sampled_frames=checked,maximum_vertex_error_px=0,authority='none',selected=False,
        depth_order_status='unchanged',runtime_status='not_evaluated',
        scope='triangle_and_vertex_identity_not_depth_or_visual_acceptance')
    output.mkdir(parents=True,exist_ok=False)
    (output/'skeleton.json').write_bytes(raw)
    (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(regions=len(regions),frames=checked,classification=classification)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--slot',action='append',required=True,help='slot:l or slot:r')
    a=p.parse_args();pairs=[v.rsplit(':',1) for v in a.slot]
    if any(len(v)!=2 for v in pairs) or len({v[0] for v in pairs})!=len(pairs):
        raise ValueError('partition_slot_arguments')
    run(a.source,a.output,dict(pairs))
