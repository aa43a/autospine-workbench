import unittest
from autospine_workbench.targets.character43.depth_region_bounds import SampledRegionBounds


class BoundsTests(unittest.TestCase):
    def test_swept_intersection_is_not_same_time_intersection(self):
        bounds=SampledRegionBounds(['a','b'])
        bounds.record(0,{'a':[(0,0),(1,1)],'b':[(10,0),(11,1)]})
        bounds.record(1,{'a':[(10,0),(11,1)],'b':[(0,0),(1,1)]})
        self.assertFalse(bounds.possible('a','b',[{'time':0},{'time':1}]))
        with self.assertRaisesRegex(ValueError,'missing_time'):
            bounds.possible('a','b',[{'time':.5}])

    def test_one_touching_sample_retains_relation_with_pixel_margin(self):
        bounds=SampledRegionBounds(['a','b'])
        bounds.record(0,{'a':[(0,0),(1,1)],'b':[(3,0),(4,1)]})
        self.assertTrue(bounds.possible('a','b',[{'time':0}]))

    def test_invalid_or_duplicate_positions_fail(self):
        bounds=SampledRegionBounds(['a'])
        with self.assertRaisesRegex(ValueError,'positions'):bounds.record(0,{'a':[(float('nan'),0)]})
        bounds.record(0,{'a':[(0,0)]})
        with self.assertRaisesRegex(ValueError,'duplicate_time'):bounds.record(0,{'a':[(0,0)]})
