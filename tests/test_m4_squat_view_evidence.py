import unittest
from m4_squat_view_evidence import compare


class ViewEvidenceTests(unittest.TestCase):
    def test_side_view_reveals_depth_bend_without_changing_3d_angle(self):
        vectors={}
        for side in ('left','right'):
            vectors['humanoid.leg.upper.'+side]=[(0,1,1)]*3
            vectors['humanoid.leg.lower.'+side]=[(0,1,-1)]*3
        result=compare(vectors,[(0,0,0),(0,1,0),(0,0,0)],[0,1,2],(0,45))
        front,side=[r['samples'][0] for r in result['views']]
        self.assertEqual(front['screen_plane_alignment'],0)
        self.assertGreater(side['screen_plane_alignment'],.5)
        self.assertAlmostEqual(front['bend_degrees'],side['bend_degrees'])
        self.assertEqual(result['key_times'],[0,1,2])
        self.assertFalse(result['selected'])
