"""Bounded source-bound supplemental checks shared by worker and offline tools."""
from collections import Counter
from hashlib import sha256
import json
from ...bvh_parser import parse_bvh
from .motion_rotation_status import build as verify_source
from .kimodo_depth_sampler import KimodoDepthSampler
from .source_depth_sampler import SegmentDepthSampler
from .motion_depth_overlap import Probe
from .torso_depth_refinement import Checker
from .torso_warp_depth_plane import WarpedPlane
from .torso_baked_depth_plane import BakedWarpPlane
from .torso_projection_profile import prepare
from .local_depth_summary import summarize

PROFILE='source-bound-local-depth-supplement-v1'


def analyze(files,artifact,bundle,request,*,midpoints=False,pixelwise=True,on_pair=None):
    verify_source(files,artifact,bundle,request)
    mapping=json.loads((bundle.path/'map.json').read_bytes())
    yaw=request.get('projection',{}).get('yaw_degrees',0)
    if bundle.source_kind=='kimodo_npz':
        sampler=KimodoDepthSampler(bundle.raw_npz,bundle.kimodo_source,mapping,yaw,
            interpolation='linear_observed_positions' if midpoints else 'source_samples_only')
        identity=sampler.identity;interpolation=sampler.interpolation
    else:
        sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),mapping,yaw)
        identity=dict(raw_bvh_sha256=sha256(bundle.raw_bvh).hexdigest())
        interpolation='linear_bvh_channels' if midpoints else 'source_samples_only'
    document=json.loads(files['skeleton.json']);depth=json.loads(files['motion-depth.json'])
    receipt=json.loads(files.get('motion-torso-projection.json',b'{}'))
    probe=Probe(document,files,'external-motion',tiled=True,sparse=True,rendered_bounds=True)
    options={}
    if receipt.get('applied'):
        expected=prepare(bundle,request)
        options['plane_provider']=(BakedWarpPlane(document,'external-motion',receipt,expected)
                                   if midpoints else WarpedPlane(receipt,expected))
    checker=Checker(probe,sampler,pixelwise=pixelwise,**options);rows=[]
    for pair in depth['pairs']:
        samples=pair['samples']
        if midpoints:
            samples=[dict(tick=(a['tick']+b['tick'])/2,source_tick=(a['source_tick']+b['source_tick'])/2)
                     for a,b in zip(samples,samples[1:])]
        for sample in samples:
            time=sample['tick']/1e6
            try:check=checker.check(pair['arm_slot'],pair['torso_slot'],time,sample['source_tick'])
            except ValueError as error:check=dict(status='unmeasured',reason_code=str(error),time=time)
            rows.append(dict(pair=[pair['arm_slot'],pair['torso_slot']],source_tick=sample['source_tick'],check=check))
        if on_pair:on_pair()
    return dict(profile=PROFILE,job_id=request['job_id'],artifact_sha256=artifact,
        source_identity=identity,interpolation=interpolation,
        spatial_sampling='barycentric_pixel_intervals' if pixelwise else 'whole_triangle_intervals',
        counts=dict(Counter(r['check']['status'] for r in rows)),records=rows,causes=summarize(rows),
        hand_mesh_axes=checker.axes,pixel_budget_used=64_000_000-probe.remaining,
        scope='sampled_proxy_diagnostics_not_readiness_or_visual_acceptance',
        authority='none',selected=False,production_authorized=False)
