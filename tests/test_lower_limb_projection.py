import unittest
from autospine_workbench.targets.character43.lower_limb_projection import measure


class LowerLimbProjectionTests(unittest.TestCase):
    def test_front_bend_is_hidden_but_depth_retains_direction(self):
        r=measure((0,1,1),(0,1,-1))
        self.assertAlmostEqual(r['bend_3d_deg'],90)
        self.assertAlmostEqual(r['bend_projected_deg'],0)
        self.assertAlmostEqual(r['knee_depth_from_chord'],1)
        back=measure((0,1,-1),(0,1,1))
        self.assertLess(back['knee_depth_ratio'],0)

    def test_side_view_recovers_bend_and_uniform_scale_preserves_ratios(self):
        r=measure((0,1,1),(0,1,-1),yaw=90)
        self.assertAlmostEqual(r['bend_projected_deg'],90)
        self.assertAlmostEqual(r['hidden_bend_deg'],0)
        self.assertAlmostEqual(r['knee_depth_from_chord'],0)
        a=measure((0,1,1),(0,1,-1));b=measure((0,5,5),(0,5,-5))
        self.assertEqual(a['projected_length_ratios'],b['projected_length_ratios'])
        self.assertAlmostEqual(a['knee_depth_ratio'],b['knee_depth_ratio'])

    def test_camera_parallel_segment_is_unknown_not_zero_bend(self):
        r=measure((0,0,1),(0,1,0))
        self.assertIsNone(r['bend_projected_deg']);self.assertIsNone(r['hidden_bend_deg'])
        self.assertIsNone(measure((0,1,0),(0,-1,0))['knee_chord_parameter'])

    def test_invalid_vectors_rejected(self):
        for u in ((0,0,0),(0,float('nan'),1),(1,2)):
            with self.assertRaises(ValueError):measure(u,(0,1,0))
