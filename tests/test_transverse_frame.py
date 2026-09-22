import math
import unittest
from autospine_workbench.targets.character43.transverse_frame import without_inherited_shear, weighted_points


class TransverseFrameTests(unittest.TestCase):
    def test_preserves_axis_width_and_determinant(self):
        frame, shear = without_inherited_shear((1,0,0,1,0,0),(.4,1.2,0,1,4,5))
        self.assertEqual(frame, (.4,0.,0,1.,4,5))
        self.assertEqual(shear, 1.2)
        self.assertEqual(frame[0]*frame[3]-frame[1]*frame[2], .4)

    def test_setup_is_identity_including_existing_shear(self):
        m=(.8,.3,.2,1.1,2,3)
        actual, removed=without_inherited_shear(m,m)
        for a,b in zip(m,actual): self.assertAlmostEqual(a,b)
        self.assertAlmostEqual(removed,0)

    def test_covariant_under_world_rotation(self):
        def rotate(m):
            a,b,c,d,x,y=m
            return (-c,-d,a,b,-y,x)
        rest=(1,0,0,1,0,0); current=(.4,1.2,0,1,4,5)
        expected,_=without_inherited_shear(rest,current)
        actual,_=without_inherited_shear(rotate(rest),rotate(current))
        self.assertEqual(actual,rotate(expected))

    def test_weighted_selection_preserves_other_influences(self):
        rest={'a':(1,0,0,1,0,0),'b':(1,0,0,1,0,0)}
        current={'a':(.4,1.2,0,1,0,0),'b':(1,0,0,1,10,0)}
        points,_=weighted_points({'vertices':[2,0,0,2,.25,1,0,2,.75]},
            [{'name':'a'},{'name':'b'}],rest,current,['a'])
        self.assertEqual(points,[[7.5,2.]])

    def test_rejects_invalid_transforms(self):
        for m in [(0,0,0,1,0,0),(1,0,0,-1,0,0),(1,0,0,1,math.nan,0)]:
            with self.assertRaises(ValueError):without_inherited_shear((1,0,0,1,0,0),m)
