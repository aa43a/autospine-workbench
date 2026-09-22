import math
import unittest
from autospine_workbench.targets.character43.group_projection_constraints import circle_joint, preserve_ankles


class EndpointConstraintTests(unittest.TestCase):
    def test_both_branches_preserve_lengths(self):
        for sign in (-1, 1):
            joint = circle_joint([1, 2], [1, 4], 2, 2, sign)
            self.assertAlmostEqual(math.dist([1, 2], joint), 2)
            self.assertAlmostEqual(math.dist([1, 4], joint), 2)
            self.assertEqual(math.copysign(1, joint[0]-1), -sign)

    def test_impossible_geometry_not_clamped(self):
        for endpoint in ([0, 0], [0, 5], [0, .5]):
            self.assertIsNone(circle_joint([0, 0], endpoint, 2, 1, 1))

    def test_ankles_preserved_without_mutation(self):
        original, projected = {}, {}
        for side in ('left', 'right'):
            for part, start, end in [('upper', [0, 0], [1, 1]), ('lower', [1, 1], [0, 2])]:
                role = f'humanoid.leg.{part}.{side}'
                original[role] = dict(start=start, end=end)
                projected[role] = dict(start=[x+3 for x in start], end=[x+3 for x in end])
            projected[f'humanoid.leg.upper.{side}']['start'] = [0, 0]
        result, failures = preserve_ankles(original, original, 1)
        self.assertFalse(failures)
        for side in ('left', 'right'):
            self.assertEqual(result[f'humanoid.leg.lower.{side}']['end'], [0, 2])
        self.assertEqual(original['humanoid.leg.upper.left']['end'], [1, 1])
