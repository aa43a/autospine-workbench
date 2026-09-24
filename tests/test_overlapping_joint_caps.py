import math
import unittest
import numpy as np
from autospine_workbench.targets.character43.overlapping_joint_caps import split
from m4_pose_material_review import transfer


class OverlappingJointCapsTests(unittest.TestCase):
    def test_union_preserves_source_and_overlap_is_bounded(self):
        p = [[-3, -2], [3, -2], [3, 2], [-3, 2]]
        uv = [[0, 0], [1, 0], [1, 1], [0, 1]]
        parts = split(p, uv, [[0, 1, 2], [0, 2, 3]], [0, 0], [1, 0], 1)
        grid = np.array([[x, y] for x in np.linspace(-3, 3, 31) for y in np.linspace(-2, 2, 21)])
        hits = []
        for sign, part in zip((1, -1), parts):
            mapped, covered = transfer(part['points'], part['uvs'], part['triangles'], grid)
            self.assertTrue(np.allclose(mapped[covered], (grid[covered]+[3, 2])/[6, 4]))
            for point in part['points']:
                if sign*point[0] > 1e-8:
                    self.assertLessEqual(math.hypot(*point), 1+1e-8)
            hits.append(covered)
        self.assertTrue(np.all(hits[0] | hits[1]))
        self.assertGreater(np.count_nonzero(hits[0] & hits[1]), 1)

    def test_reversed_axis_swaps_surfaces(self):
        p = [[-2, -2], [2, -2], [0, 3]]
        a = split(p, p, [[0, 1, 2]], [0, 0], [1, 0], 1)
        b = split(p, p, [[0, 1, 2]], [0, 0], [-1, 0], 1)
        self.assertEqual(a, b[::-1])
