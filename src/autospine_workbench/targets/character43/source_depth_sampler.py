"""BVH FK depth at source ticks, with an explicit linear-channel midpoint model."""
from bisect import bisect_right
import math

from ...bvh_fk import bvh_frame_ticks, _world_matrices, _origin, _multiply, _translate
from ...bvh_map_validation import require_bvh_map

PROFILE = 'bvh-linear-channel-depth-sampling-v1'


class SegmentDepthSampler:
    def __init__(self,bvh,mapping,yaw_degrees=0):
        require_bvh_map(mapping,bvh=bvh)
        if not math.isfinite(yaw_degrees) or not -90 <= yaw_degrees <= 90:
            raise ValueError('depth_sampler_yaw_invalid')
        self.bvh,self.mapping=bvh,mapping
        self.ticks=bvh_frame_ticks(bvh)
        self.indices={j.name:i for i,j in enumerate(bvh.joints)}
        self.roles={r['role']:r for r in mapping['bones']}
        self.channels=[c for j in bvh.joints for c in j.channels]
        self.angle=math.radians(yaw_degrees)

    def joint_depths(self,tick,*,include_end_sites=False):
        if not math.isfinite(tick) or not self.ticks[0] <= tick <= self.ticks[-1]:
            raise ValueError('depth_sampler_time_invalid')
        index=min(bisect_right(self.ticks,tick)-1,len(self.ticks)-1)
        frame=self.bvh.frames[index]
        if tick!=self.ticks[index]:
            next_frame=self.bvh.frames[index+1]
            if any(c.endswith('rotation') and abs(b-a)>=180
                   for c,a,b in zip(self.channels,frame,next_frame)):
                raise ValueError('depth_sampler_rotation_interval_ambiguous')
            fraction=(tick-self.ticks[index])/(self.ticks[index+1]-self.ticks[index])
            frame=tuple(a+(b-a)*fraction for a,b in zip(frame,next_frame))
        matrices=_world_matrices(self.bvh,frame)
        basis=self.mapping['basis']
        def z(name,offset=None):
            matrix=matrices[self.indices[name]]
            point=_origin(matrix if offset is None else _multiply(matrix,_translate(offset)))
            values=[(-1 if basis[k][0]=='-' else 1)*point['XYZ'.index(basis[k][1])]
                    for k in ('screen_x','depth')]
            return math.sin(self.angle)*values[0]+math.cos(self.angle)*values[1]
        reference=z(self.roles['humanoid.spine.upper']['joint_name'])
        length=self.mapping['root']['reference_length_source_units']
        result={name:(z(name)-reference)/length for name in self.indices}
        if include_end_sites:
            result.update({(j.name,'end_site'):(z(j.name,j.end_site_offset)-reference)/length
                           for j in self.bvh.joints if j.end_site_offset is not None})
        return result

    def torso_anchors(self,tick):
        depths=self.joint_depths(tick)
        return {bone:depths[name] for bone,name in (
            ('upperarm_l',self.roles['humanoid.arm.upper.left']['joint_name']),
            ('upperarm_r',self.roles['humanoid.arm.upper.right']['joint_name']),
            ('pelvis',self.mapping['root']['joint_name']))}

    def __call__(self,tick):
        depths=self.joint_depths(tick)
        segments={}
        for side,suffix in [('left','l'),('right','r')]:
            for part,bone in [('upper','upperarm'),('lower','forearm')]:
                role=self.roles.get('humanoid.arm.'+part+'.'+side)
                if role and role['aim']['kind']=='joint':
                    segments[bone+'_'+suffix]=tuple(depths[n]
                        for n in (role['joint_name'],role['aim']['joint_name']))
        return segments

    def leg_segments(self,tick):
        """Explicit mapped thigh/calf axes; no inferred garment or foot depth."""
        depths=self.joint_depths(tick); segments={}
        for side,suffix in [('left','l'),('right','r')]:
            for part,bone in [('upper','thigh'),('lower','calf')]:
                role=self.roles.get('humanoid.leg.'+part+'.'+side)
                if role and role['aim']['kind']=='joint':
                    segments[bone+'_'+suffix]=tuple(depths[n]
                        for n in (role['joint_name'],role['aim']['joint_name']))
        return segments
