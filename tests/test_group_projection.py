import math
import unittest

from autospine_workbench.targets.character43.group_projection import compare


def vectors(points):
    return {f'humanoid.{limb}.{part}.{side}': list(points)
            for limb in ('arm', 'leg') for part in ('upper', 'lower') for side in ('left', 'right')}


class GroupProjectionTests(unittest.TestCase):
    def test_depth_motion_has_two_side_candidates_not_automatic_sign(self):
        data = vectors([(0, 0, 1), (0, .1, 1)])
        report = compare(data, [0, 1])
        self.assertFalse(report['selected'])
        self.assertEqual(report['records'][0]['best_visibility_yaws'], [-90, 90])
        self.assertEqual(data, vectors([(0, 0, 1), (0, .1, 1)]))

    def test_wrap_is_continuous_but_collapse_breaks_branch(self):
        points = [(math.cos(math.radians(a)), math.sin(math.radians(a)), 0) for a in (179, -179)]
        points += [(0, 0, 1), (1, 0, 0)]
        angles = compare(vectors(points), [0, 1, 2, 3])['records'][0]['alternatives'][0]['angles'][0]['angles']
        self.assertAlmostEqual(angles[1]-angles[0], 2)
        self.assertIsNone(angles[2])
        self.assertEqual(angles[3], 0)

    def test_missing_and_invalid_source_fail(self):
        with self.assertRaises(ValueError): compare({}, [0, 1])
        with self.assertRaises(ValueError): compare(vectors([(0, 0, 0)]*2), [0, 1])
        with self.assertRaises(ValueError): compare(vectors([(1, 0, 0)]*2), [1, 0])
