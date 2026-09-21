"""Verified SOMA77 depth observations with explicitly optional linear sampling."""
from bisect import bisect_right
import math

from ...kimodo_npz_reader import decode_kimodo_npz
from ...kimodo_npz_consistency import validate_kimodo_consistency
from ...kimodo_npz_map_validation import require_kimodo_npz_map
from ...kimodo_npz_projection import kimodo_frame_ticks
from ...kimodo_soma77 import SOMA77_INDEX_BY_NAME

PROFILE='soma77-declared-depth-samples-v1-experiment'


class KimodoDepthSampler:
    def __init__(self,raw,source,mapping,yaw_degrees=0,*,interpolation='source_samples_only'):
        require_kimodo_npz_map(mapping,source=source)
        if not math.isfinite(yaw_degrees) or not -90<=yaw_degrees<=90:
            raise ValueError('depth_sampler_yaw_invalid')
        if interpolation not in ('source_samples_only','linear_observed_positions'):
            raise ValueError('kimodo_depth_interpolation_unsupported')
        motion=validate_kimodo_consistency(decode_kimodo_npz(raw,source),source)
        self.mapping=mapping;self.roles={r['role']:r for r in mapping['bones']}
        self.ticks=kimodo_frame_ticks(source);self.interpolation=interpolation
        self.indices=SOMA77_INDEX_BY_NAME
        self.identity=dict(raw_npz_sha256=motion.raw_npz_sha256,source_sha256=motion.source_sha256,
                           array_inventory_sha256=motion.array_inventory_sha256)
        angle=math.radians(yaw_degrees);basis=mapping['basis']
        def component(p,axis):return (-1 if axis[0]=='-' else 1)*p['XYZ'.index(axis[1])]
        self.depths=[{name:math.sin(angle)*component(frame[i],basis['screen_x'])+
                     math.cos(angle)*component(frame[i],basis['depth'])
                     for name,i in self.indices.items()} for frame in motion.positions]

    def joint_depths(self,tick,*,include_end_sites=False):
        if not math.isfinite(tick) or not self.ticks[0]<=tick<=self.ticks[-1]:
            raise ValueError('depth_sampler_time_invalid')
        i=min(bisect_right(self.ticks,tick)-1,len(self.ticks)-1)
        depths=self.depths[i]
        if tick!=self.ticks[i]:
            if self.interpolation=='source_samples_only':
                raise ValueError('kimodo_depth_between_source_samples_unobserved')
            t=(tick-self.ticks[i])/(self.ticks[i+1]-self.ticks[i])
            depths={n:z+(self.depths[i+1][n]-z)*t for n,z in depths.items()}
        reference=depths[self.roles['humanoid.spine.upper']['joint_name']]
        length=self.mapping['root']['reference_length_meters']
        return {n:(z-reference)/length for n,z in depths.items()}

    def torso_anchors(self,tick):
        depths=self.joint_depths(tick)
        return {bone:depths[name] for bone,name in (
            ('upperarm_l',self.roles['humanoid.arm.upper.left']['joint_name']),
            ('upperarm_r',self.roles['humanoid.arm.upper.right']['joint_name']),
            ('pelvis',self.mapping['root']['joint_name']))}

    def _segments(self,tick,limb,parts):
        depths=self.joint_depths(tick);result={}
        for side,suffix in [('left','l'),('right','r')]:
            for part,bone in parts:
                role=self.roles.get('humanoid.'+limb+'.'+part+'.'+side)
                if role and role.get('aim_joint_name'):
                    result[bone+'_'+suffix]=(depths[role['joint_name']],depths[role['aim_joint_name']])
        return result

    def __call__(self,tick):return self._segments(tick,'arm',[('upper','upperarm'),('lower','forearm')])
    def leg_segments(self,tick):return self._segments(tick,'leg',[('upper','thigh'),('lower','calf')])

    def hand_observations(self,tick,*,full_hand=False):
        depths=self.joint_depths(tick);segments={};joints={}
        for side,suffix,title in [('left','l','Left'),('right','r','Right')]:
            wrist=title+'Hand';role=self.roles.get('humanoid.arm.lower.'+side,{})
            if role.get('aim_joint_name')!=wrist:continue
            chain=[wrist,wrist+'Middle1']
            if full_hand:chain += [wrist+'Middle2',wrist+'Middle3',wrist+'Middle4',wrist+'MiddleEnd']
            segments['hand_'+suffix]=(depths[wrist],depths[chain[-1]])
            joints['hand_'+suffix]=chain
        return dict(profile='soma77-observed-hand-depth-v1-experiment',segments=segments,joints=joints,
            interpolation=self.interpolation,identity=self.identity,authority='none',selected=False,
            assumption='target_hand_axis_matches_observed_wrist_to_middle_finger_chord_not_surface_depth')
