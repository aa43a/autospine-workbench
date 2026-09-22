import unittest
from autospine_workbench.targets.character43.knee_projection import compare,measure

class KneeTests(unittest.TestCase):
    def test_depth_bend_is_not_reported_as_backward(self):
        row=compare((0,1,1),(0,1,-1),(.2,1,0),(-.2,1,0))
        self.assertEqual(row['status'],'source_bend_hidden_in_depth')
        self.assertAlmostEqual(row['source']['bend_degrees'],90)
    def test_reversed_projection_and_scale_invariance(self):
        a=compare((1,1,0),(-1,1,0),(-2,2,0),(2,2,0))
        self.assertEqual(a['status'],'projected_bend_reversed')
        b=compare((10,10,0),(-10,10,0),(-20,20,0),(20,20,0))
        self.assertEqual(a,b)
    def test_degenerate_and_straight(self):
        with self.assertRaises(ValueError):measure((0,0,0),(0,1,0))
        self.assertEqual(measure((0,1,0),(0,-1,0))['status'],'folded_chord_unobservable')
        self.assertEqual(compare((0,1,0),(0,1,0),(0,2,0),(0,2,0))['status'],'source_nearly_straight')

    def test_bend_plane_separates_depth_and_screen_bending(self):
        depth=measure((0,1,1),(0,1,-1));screen=measure((1,1,0),(-1,1,0))
        self.assertEqual(depth['screen_plane_alignment'],0)
        self.assertEqual(screen['screen_plane_alignment'],1)
        self.assertIsNone(measure((0,1,0),(0,2,0))['bend_plane_normal'])
    def test_plane_measurement_does_not_depend_on_bone_lengths(self):
        a=measure((0,1,1),(1,1,-1));b=measure((0,10,10),(2,2,-2))
        self.assertEqual(a['bend_plane_normal'],b['bend_plane_normal'])

if __name__=='__main__':unittest.main()
