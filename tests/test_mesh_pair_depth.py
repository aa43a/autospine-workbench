import unittest
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.mesh_pair_depth import compare
from test_source_depth_sampler import sampler


class MeshPairDepthTests(unittest.TestCase):
    def check(self,a,b):
        doc,files=fixture()
        return compare(Probe(doc,files,'test'),'a','b',0,a,b)

    def test_separated_intervals_and_reverse_order(self):
        a=[[.2,.3]]*4; b=[[0,.1]]*4
        self.assertEqual(self.check(a,b)['status'],'uniform_front_proxy')
        self.assertEqual(self.check(b,a)['status'],'uniform_back_proxy')

    def test_unknown_triangle_cannot_be_hidden_by_known_triangle(self):
        result=self.check([[.2,.3],None,[.2,.3],[.2,.3]],[[0,.1]]*4)
        self.assertGreater(result['counts']['unknown'],0)
        self.assertEqual(result['unknown_support']['a'],result['counts']['unknown'])
        self.assertEqual(result['unknown_support']['b'],0)
        self.assertEqual(result['status'],'requires_partition_or_more_depth')

    def test_entire_envelope_must_clear_margin(self):
        result=self.check([[.01,.3]]*4,[[0,.1]]*4)
        self.assertEqual(result['counts']['ambiguous'],4)
        with self.assertRaisesRegex(ValueError,'intervals_invalid'):
            self.check([[.3,.2]]*4,[[0,.1]]*4)

    def test_budget_failure_is_explicit(self):
        doc,files=fixture(); probe=Probe(doc,files,'test',pixel_budget=8)
        with self.assertRaisesRegex(ValueError,'pixel_budget'):
            compare(probe,'a','b',0,[[.2,.3]]*4,[[0,.1]]*4)

    def test_leg_axes_use_declared_source_endpoints(self):
        source=sampler(); depths=source.joint_depths(250000)
        segments=source.leg_segments(250000)
        self.assertEqual(set(segments),{'thigh_l','calf_l','thigh_r','calf_r'})
        for side,suffix in [('left','l'),('right','r')]:
            role=source.roles['humanoid.leg.upper.'+side]
            self.assertEqual(segments['thigh_'+suffix],tuple(depths[n] for n in
                (role['joint_name'],role['aim']['joint_name'])))
        self.assertNotIn('thigh_l',source(250000))


if __name__=='__main__': unittest.main()
