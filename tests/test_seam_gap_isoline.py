import unittest
import numpy as np
from autospine_workbench.targets.spine43.seam_gap_isoline import contours, probe


class IsolineTests(unittest.TestCase):
    def test_linear_field_subpixel_position_and_outward_normal(self):
        boundary=contours(np.array([[0,20],[0,20]]),[100,200,2,2])
        self.assertTrue(boundary['segments'])
        for edge in boundary['segments']:
            self.assertAlmostEqual(edge['a'][0],100.9)
            self.assertEqual(edge['normal'],[-1.,0.])
        self.assertEqual(boundary['unresolved_boxes'],[])

    def test_saddle_and_exact_threshold_stay_unresolved(self):
        b=contours([[0,16],[16,0]],[0,0,2,2])
        self.assertTrue(b['unresolved_boxes'])
        self.assertEqual(probe([1,-1],[b,b])['evidence'],'unresolved_isoline_neighborhood')

    def test_linear_refinement_keeps_distance(self):
        a=np.array([[0,20],[0,20]])
        coarse=probe([.5,-1],[contours(a,[0,0,2,2],4)]*2)
        fine=probe([.5,-1],[contours(a,[0,0,2,2],8)]*2)
        self.assertAlmostEqual(coarse['driver_nearest'][0]['distance'],fine['driver_nearest'][0]['distance'])

    def test_constant_field_no_invented_roi_edges(self):
        self.assertEqual(contours([[255,255],[255,255]],[0,0,2,2])['segments'],[])
        with self.assertRaises(ValueError): contours([[float('nan')]], [0,0,1,1])
