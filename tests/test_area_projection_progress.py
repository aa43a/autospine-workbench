import math
import unittest
from unittest.mock import patch
from autospine_workbench.targets.character43.area_projection import project
from autospine_workbench.targets.character43.affine_area_repair import repair
from autospine_workbench.targets.character43.projected_area_sampling import inspect
from autospine_workbench.targets.spine43.continuous_pose import area
from test_character_area_projection import context
from test_character_affine_repair import fixture


class AreaProgressTests(unittest.TestCase):
    def test_stationary_pose_avoids_repeated_noop_sweeps(self):
        points = [[0, 0], [1, 0], [0, 1]]
        with patch('autospine_workbench.targets.character43.area_projection.area', wraps=area) as counted:
            result, evidence = project(context([True]*3, .1), points)
        self.assertEqual(result, points)
        self.assertEqual(evidence, dict(iterations=48, converged=True, lower_target=.55))
        self.assertEqual(counted.call_count, 1)

    def test_initial_transport_is_clamped_before_stationary_test(self):
        points = [[0, 0], [1, 0], [0, 1]]
        result, evidence = project(context([False]*3, .1), points,
                                   initial=[[3, 0], [4, 0], [3, 1]])
        self.assertEqual(result, points)
        self.assertTrue(evidence['converged'])

    def test_invalid_edge_length_does_not_shortcut(self):
        points = [[0, 0], [1, 0], [0, 1]]
        ctx = context([False]*3, .1); ctx['lengths'] = [.1]*3
        _, evidence = project(ctx, points)
        self.assertFalse(evidence['converged'])
        self.assertEqual(evidence['iterations'], 1536)

    def test_sample_and_interpolation_progress_preserve_results(self):
        doc = fixture(); events = []
        result, evidence = repair(doc, 'walk', samples=17, progress=events.append)
        self.assertEqual((result, evidence), repair(doc, 'walk', samples=17))
        sampled = [r for r in events if r['stage']=='sample_geometry' and 'frame_index' in r]
        self.assertEqual([r['frame_index'] for r in sampled], [0, 16])
        events.clear()
        checked = inspect(result, 'walk', ['mesh'], progress=events.append)
        self.assertEqual(checked, inspect(result, 'walk', ['mesh']))
        self.assertGreater(len(events), 1)
        self.assertEqual(events[0]['sample_count'], checked['sampled_frames'])


if __name__ == '__main__': unittest.main()
