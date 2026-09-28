import math
import unittest
from test_mixamo_map import source
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion2d.mixamo_map import build_map
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler


def sampler(angle=90,yaw=0):
    raw=source(); bvh=parse_bvh(raw); offset=0
    for joint in bvh.joints:
        if joint.name=='LeftArm':break
        offset+=len(joint.channels)
    last=list(bvh.frames[-1]); last[offset]=angle
    lines=raw.decode().splitlines(); lines[-1]=' '.join(str(v) for v in last)
    bvh=parse_bvh(('\n'.join(lines)+'\n').encode())
    mapping=build_map(bvh,clip_id='test',reference_length=10,screen_x='+X',screen_y='-Y',depth='+Z')
    return SegmentDepthSampler(bvh,mapping,yaw)


class SourceDepthSamplerTests(unittest.TestCase):
    def test_continuous_camera_is_evaluated_at_midpoint_not_endpoint_average(self):
        base=sampler(angle=0)
        dynamic=SegmentDepthSampler(base.bvh,base.mapping,camera_keys=[dict(time=0,yaw=0),dict(time=.5,yaw=360)])
        for name,value in base.joint_depths(250000,include_end_sites=True).items():
            self.assertAlmostEqual(dynamic.joint_depths(250000,include_end_sites=True)[name],-value)
        self.assertEqual(dynamic.joint_depths(0),base.joint_depths(0))
        for name,value in base.joint_depths(500000).items():
            self.assertAlmostEqual(dynamic.joint_depths(500000)[name],value)

    def test_declared_segment_reuses_fk_without_surface_assumption(self):
        probe=sampler()
        for tick in (0,250000,500000):
            self.assertEqual(probe.mapped_segment('humanoid.arm.upper.left',tick),
                             probe(tick)['upperarm_l'])
        with self.assertRaisesRegex(ValueError,'mapped_segment_unavailable'):
            probe.mapped_segment('not-declared',0)
        probe.roles['humanoid.arm.upper.left']['aim']={'kind':'end_site'}
        with self.assertRaisesRegex(ValueError,'mapped_segment_unavailable'):
            probe.mapped_segment('humanoid.arm.upper.left',0)

    def test_end_site_depth_uses_actual_declared_offset(self):
        probe=sampler(angle=0)
        depths=probe.joint_depths(0,include_end_sites=True)
        self.assertAlmostEqual(depths['LeftHand','end_site']-depths['LeftHand'],.3)
        self.assertNotIn(('LeftHand','end_site'),probe.joint_depths(0))

    def test_midpoint_runs_fk_instead_of_averaging_endpoint_depths(self):
        probe=sampler()
        delta=lambda tick:probe(tick)['upperarm_l'][1]-probe(tick)['upperarm_l'][0]
        self.assertAlmostEqual(delta(0),.3)
        self.assertAlmostEqual(delta(500000),.2)
        self.assertAlmostEqual(delta(250000),5/math.sqrt(2)/10)
        self.assertNotAlmostEqual(delta(250000),(delta(0)+delta(500000))/2)
        side=sampler(yaw=90)(250000)['upperarm_l']
        self.assertAlmostEqual(side[1]-side[0],.1)

    def test_undersampled_rotation_and_out_of_range_do_not_get_clamped(self):
        probe=sampler(angle=360)
        with self.assertRaisesRegex(ValueError,'rotation_interval_ambiguous'):probe(250000)
        self.assertIn('upperarm_l',probe(500000))
        for tick in (-1,500001,float('nan')):
            with self.assertRaisesRegex(ValueError,'time_invalid'):probe(tick)


if __name__=='__main__':unittest.main()
