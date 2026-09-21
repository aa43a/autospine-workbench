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

if __name__=='__main__':unittest.main()
