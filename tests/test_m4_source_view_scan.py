import math
import unittest

from m4_source_view_scan import scan


class SourceViewScanTests(unittest.TestCase):
    def test_depth_segment_has_no_front_direction_but_side_is_visible(self):
        result = scan({'humanoid.leg.upper.left': [(0, 0, 1), (0, 0, 2)]}, [0, 90])
        front, side = [row['records'][0] for row in result]
        self.assertEqual(front['undefined_direction_samples'], 2)
        self.assertIsNone(front['max_adjacent_angle_degrees'])
        self.assertAlmostEqual(side['minimum_visibility'], 1)
        self.assertEqual(side['max_adjacent_angle_degrees'], 0)

    def test_angle_wrap_does_not_create_false_full_turn(self):
        points = [(math.cos(math.radians(a)), math.sin(math.radians(a)), 0) for a in (179, -179)]
        row = scan({'humanoid.arm.upper.right': points}, [0])[0]['records'][0]
        self.assertAlmostEqual(row['max_adjacent_angle_degrees'], 2)

    def test_invalid_source_is_rejected(self):
        for points in ([], [(0, 0, 0)], [(math.nan, 1, 2)]):
            with self.assertRaises(ValueError):
                scan({'humanoid.leg.upper.left': points}, [0])


if __name__ == '__main__':
    unittest.main()
