"""Fixed constraints remain acceptance evidence but need no solver updates."""
import unittest
from unittest.mock import patch

from autospine_workbench.targets.character43.area_projection import project
from autospine_workbench.targets.spine43.continuous_pose import area
from test_character_area_projection import context


class ActiveProjectionTests(unittest.TestCase):
    def test_fixed_failure_is_checked_at_every_historical_checkpoint(self):
        points = [[0, 0], [1, 0], [0, .4]]
        with patch('autospine_workbench.targets.character43.area_projection.area', wraps=area) as counted:
            actual, evidence = project(context([False]*3, 1), points)
        self.assertEqual(actual, points)
        self.assertEqual(evidence, dict(iterations=1536, converged=False, lower_target=.50625))
        self.assertEqual(counted.call_count, 33)

    def test_fixed_failure_does_not_prevent_free_triangle_repair(self):
        points = [[0, 0], [1, 0], [0, .4], [2, 0], [3, 0], [2, .4]]
        ctx = context([False]*5+[True], .2)
        ctx.update(row={'triangles': [[0, 1, 2], [3, 4, 5]]}, areas=[.5, .5])
        actual, evidence = project(ctx, points)
        self.assertEqual(actual[:5], points[:5])
        self.assertGreater(area(actual, [3, 4, 5])/.5, .5)
        self.assertFalse(evidence['converged'])


if __name__ == '__main__': unittest.main()
