import unittest
from m4_surface_target_compare import bend


class BendComparisonTests(unittest.TestCase):
    def test_camera_translation_and_uniform_scale_do_not_change_bend(self):
        points=[[1,1],[3,2],[1,4]]
        self.assertAlmostEqual(bend(points),bend([[100+7*x,-20+7*y] for x,y in points]))
        self.assertAlmostEqual(bend(points),bend([[-y,x] for x,y in points]))
        self.assertAlmostEqual(bend(points),-bend([[-x,y] for x,y in points]))

    def test_collapsed_endpoint_is_not_evidence_of_direction(self):
        with self.assertRaises(ValueError):bend([[0,0],[1,0],[0,0]])
