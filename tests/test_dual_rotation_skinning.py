import math
import unittest
from autospine_workbench.targets.character43.dual_rotation_skinning import blend


def frame(angle, pivot=(0, 0)):
    c, s = math.cos(angle), math.sin(angle)
    x, y = pivot
    return [c, -s, s, c, x-c*x+s*y, y-s*x-c*y]


class DualRotationSkinningTests(unittest.TestCase):
    def test_single_affine_influence_is_exact(self):
        result = blend([3, 2], [[2, .3, .1, 1, 4, 5]], [1])
        self.assertAlmostEqual(result[0], 10.6)
        self.assertAlmostEqual(result[1], 7.3)

    def test_common_pivot_rotation_preserves_radius(self):
        pivot = (4, 7)
        point = [6, 7]
        result = blend(point, [frame(0, pivot), frame(math.radians(160), pivot)], [.5, .5])
        self.assertAlmostEqual(math.dist(result, pivot), 2)
        self.assertAlmostEqual(result[0], 4+2*math.cos(math.radians(80)))
        self.assertAlmostEqual(result[1], 7+2*math.sin(math.radians(80)))

    def test_equivalent_signed_quaternions_do_not_cancel(self):
        result = blend([1, 0], [frame(math.radians(179)), frame(math.radians(-179))], [.5, .5])
        self.assertAlmostEqual(result[0], -1)
        self.assertAlmostEqual(result[1], 0)

    def test_half_turn_and_reflections_remain_unresolved(self):
        with self.assertRaisesRegex(ValueError, 'branch_ambiguous'):
            blend([1, 0], [frame(0), frame(math.pi)], [.5, .5])
        with self.assertRaisesRegex(ValueError, 'reflection'):
            blend([1, 0], [[-1, 0, 0, 1, 0, 0]], [1])
