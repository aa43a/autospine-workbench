import unittest
from autospine_workbench.targets.character43.group_projection_pose import pose


class AnchoredPoseTests(unittest.TestCase):
    def test_anchor_connection_and_original_depth(self):
        source = {'humanoid.arm.upper.right': [([1, 2, 3], [0, 0, 2])],
                  'humanoid.arm.lower.right': [([1, 2, 5], [0, 1, 1])]}
        result = pose(source, 0, {'arm.right': -90})
        upper, lower = result.values()
        self.assertEqual(upper['start'], [1, 2])
        self.assertEqual(upper['end'], lower['start'])
        self.assertEqual(lower['source_depth'], [5, 6])
        self.assertAlmostEqual(lower['end'][0], 4)

    def test_disconnected_chain_rejected(self):
        source = {'humanoid.arm.upper.right': [([0, 0, 0], [1, 0, 0])],
                  'humanoid.arm.lower.right': [([2, 0, 0], [1, 0, 0])]}
        with self.assertRaises(ValueError): pose(source, 0, {'arm.right': 90})
