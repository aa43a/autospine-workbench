import math
import unittest
from autospine_workbench.targets.character43.source_pose_fidelity import chain,inspect


class FidelityTests(unittest.TestCase):
    def test_raised_source_lowered_target_is_detected(self):
        row=chain([(0,-1,0),(0,-1,0)],[(0,10),(0,10)],[10,10])
        self.assertEqual(row['direction_error_degrees'],[180,180])
        self.assertEqual(row['source_endpoint_height_ratio'],1)
        self.assertEqual(row['target_endpoint_height_ratio'],-1)
        self.assertEqual(row['endpoint_error_ratio'],2)

    def test_depth_shortening_is_not_extra_error(self):
        row=chain([(0,-1,1),(0,-1,-1)],[(0,-10/math.sqrt(2))]*2,[10,10])
        self.assertAlmostEqual(row['endpoint_error_ratio'],0)
        self.assertEqual(row['direction_error_degrees'],[0,0])

    def test_camera_axis_is_unobservable_not_zero_error(self):
        row=chain([(0,0,1),(0,1,0)],[(1,0),(0,10)],[10,10])
        self.assertIsNone(row['direction_error_degrees'][0])
        self.assertEqual(row['projection_visibility'][0],0)

    def test_direction_wrap_and_scale(self):
        a=lambda d:(math.cos(math.radians(d)),math.sin(math.radians(d)))
        row=chain([(*a(179),0)]*2,[a(-179)]*2,[1,1])
        self.assertAlmostEqual(row['direction_error_degrees'][0],2)
        for args in [([],[],[]), ([(0,0,0)]*2,[(0,1)]*2,[1,1])]:
            with self.assertRaises(ValueError):chain(*args)

    def test_incomplete_source_inventory_fails(self):
        with self.assertRaisesRegex(ValueError,'source_inventory'):inspect({},'motion',{},[0,1])


if __name__=='__main__':unittest.main()
