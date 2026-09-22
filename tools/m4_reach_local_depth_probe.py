"""Explain all measured reach straddles with a bounded local bone-depth proxy."""
import argparse
from collections import Counter
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
from autospine_workbench.targets.character43.kimodo_depth_sampler import KimodoDepthSampler
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.mesh_depth_proxy import overlap_support


def run(root,depth_root,output,*,torso_plane=False):
    output.mkdir(parents=True,exist_ok=False);summary=[]
    inventory=json.loads((root/'comparison.json').read_bytes())
    for i,item in enumerate(inventory['rows']):
        depth=json.loads((depth_root/(str(i)+'.json')).read_bytes())
        digest=depth['candidate_bundle_sha256']
        if digest!=item['views'][1]['artifact'] or depth['yaw_degrees']!=item['views'][1]['yaw']:
            raise ValueError('local_depth_candidate_view_mismatch')
        files=AnimatedStore(root/str(i)/'isolated-store').read(digest)
        doc=json.loads(files['skeleton.json']);identity=depth['source_identity']
        bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
        if bundle.source_kind=='kimodo_npz':
            sampler=KimodoDepthSampler(bundle.raw_npz,bundle.kimodo_source,bundle.kimodo_map,depth['yaw_degrees'])
        else:sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map,depth['yaw_degrees'])
        records=[]
        for pair in depth['pairs']:
            samples=[s for s in pair['samples'] if s['ambiguous'] and s['overlap'].get('overlap_pixels',0)>0]
            # Independent explicit budget per pair, no silent sampling truncation.
            probe=Probe(doc,files,'external-motion',pixel_budget=64_000_000,
                        rendered_bounds=True,tiled=True,sparse='priority_depth_points')
            if torso_plane:
                from autospine_workbench.targets.character43.torso_depth_refinement import Checker
                checker=Checker(probe,sampler,pixelwise=True)
            for s in samples:
                try:
                    if torso_plane:
                        value=checker.check(pair['arm_slot'],pair['torso_slot'],s['tick']/1e6,s['source_tick'])
                    else:
                        value=overlap_support(probe,pair['arm_slot'],pair['torso_slot'],s['tick']/1e6,
                                              sampler(s['source_tick']),endpoint_caps=False)
                    if value['overlap_pixels']!=s['overlap']['overlap_pixels']:
                        raise RuntimeError('local_depth_overlap_disagrees')
                except ValueError as error:
                    value=dict(status='unmeasured',reason=str(error),time=s['tick']/1e6,
                               pair=[pair['arm_slot'],pair['torso_slot']])
                records.append(value)
            print(json.dumps(dict(character=item['label'],pair=pair['arm_slot'],samples=len(samples),
                                  budget_used=64_000_000-probe.remaining)),flush=True)
        result=dict(authority='none',selected=False,candidate=digest,yaw=depth['yaw_degrees'],records=records,
                    scope='source_sample_local_proxy_not_surface_truth_or_order_acceptance',
                    endpoint_caps=torso_plane,torso_plane=torso_plane,budget_per_pair=64_000_000)
        (output/(str(i)+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        counts=Counter(r['status'] for r in records)
        summary.append(dict(character=item['label'],candidate=digest,samples=len(records),statuses=dict(counts),
                            pixels={k:sum(r.get('counts',{}).get(k,0) for r in records)
                                    for k in ('front','back','ambiguous','unknown')}))
        (output/'summary.json').write_text(json.dumps(dict(authority='none',selected=False,torso_plane=torso_plane,
            scope='source_sample_local_proxy_not_surface_truth_or_order_acceptance',rows=summary),ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(summary[-1],ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','depth_root','output'):p.add_argument(name,type=Path)
    p.add_argument('--torso-plane',action='store_true')
    a=p.parse_args();run(a.root,a.depth_root,a.output,torso_plane=a.torso_plane)
