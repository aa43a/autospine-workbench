"""Virtual anchor offsets sampled like the compensated Spine deform timeline."""
import math

from .affine_pose import matrices
from .cloth_depth_plane import fit
from .torso_projection_candidate import inverse, multiply, point, transformed
from .torso_warp_depth_plane import WarpedPlane
from ..spine43.continuous_pose import interpolate


class BakedWarpPlane(WarpedPlane):
    def __init__(self, document, animation, receipt, expected_source):
        super().__init__(receipt, expected_source)
        tracks = document['animations'][animation].get('attachments', {}).get('default', {})
        schedules = []
        for slot in receipt['changed_slots']:
            keys = tracks.get(slot, {}).get(slot, {}).get('deform', [])
            if not keys or any('curve' in k for k in keys):
                raise ValueError('depth_torso_bake_schedule_unsupported')
            schedules.append([k['time'] for k in keys])
        if not schedules or any(s != schedules[0] for s in schedules):
            raise ValueError('depth_torso_bake_schedule_mismatch')
        times = schedules[0]
        if (len(times) != receipt['sample_count'] or not set(self.rows) <= set(times)
                or any(not math.isfinite(t) for t in times)
                or any(b <= a for a,b in zip(times,times[1:]))):
            raise ValueError('depth_torso_bake_schedule_invalid')
        shape_keys = [dict(time=t,vertices=[r['longitudinal'],r['shear'],r['transverse']])
                      for t,r in self.rows.items()]
        self.keys = {n: [] for n in ('upperarm_l','upperarm_r','pelvis')}
        for t in times:
            old = matrices(document, animation, t)
            new = transformed(document, old, interpolate(shape_keys,t,'vertices'))
            for name,keys in self.keys.items():
                if name not in old: raise ValueError('cloth_plane_anchors_missing')
                offset = point(multiply(inverse(old[name]),new[name]),0,0)
                keys.append(dict(time=t,vertices=list(offset)))
        self.document,self.animation = document,animation
        self.bounds = times[0],times[-1]

    def __call__(self, document, animation, time, sampler, source_tick):
        if document is not self.document or animation != self.animation:
            raise ValueError('depth_torso_candidate_mismatch')
        if not math.isfinite(time) or not self.bounds[0] <= time <= self.bounds[1]:
            raise ValueError('depth_torso_time_invalid')
        pose = matrices(document,animation,time)
        points = {n:list(point(pose[n],*interpolate(keys,time,'vertices')))
                  for n,keys in self.keys.items()}
        result = fit(points,sampler.torso_anchors(source_tick))
        return dict(result,anchor_profile='compensated-torso-baked-local-offsets-v1',
                    time=time,source_tick=source_tick,
                    anchor_scope='virtual_markers_interpolated_like_baked_deform_not_observed_surface')
