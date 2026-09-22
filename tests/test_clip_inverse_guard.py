import unittest
import math
from m4_clip_inverse_guard import convex,validate


class InverseGuardTests(unittest.TestCase):
    def test_winding_and_collinear_vertices(self):
        points=[[0,0],[1,0],[2,0],[2,2],[0,2]]
        self.assertTrue(convex(points));self.assertTrue(convex(points[::-1]))

    def test_concave_not_silently_hull_clipped(self):
        points=[[0,0],[2,0],[1,1],[2,2],[0,2]]
        self.assertFalse(convex(points))
        with self.assertRaisesRegex(ValueError,'runtime_convexifies'):
            validate([dict(frames=[dict(points=points)])])

    def test_degenerate_is_not_accepted(self):
        self.assertFalse(convex([[0,0],[1,0],[2,0]]))

    def test_self_crossing_star_is_not_convex(self):
        points=[[math.cos(i*2*math.pi/5),math.sin(i*2*math.pi/5)] for i in (0,2,4,1,3)]
        self.assertFalse(convex(points))
