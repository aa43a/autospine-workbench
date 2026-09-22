import unittest
import math
from unittest.mock import patch

from autospine_workbench.targets.character43.motion_direction_audit import audit


class DirectionAuditTests(unittest.TestCase):
    def run_audit(self, vectors, poses):
        with patch('autospine_workbench.targets.character43.motion_direction_audit.matrices', side_effect=poses):
            return audit({}, 'motion', {'humanoid.arm.upper.right': vectors}, [0, 1])['records'][0]

    def test_final_axis_mismatch_is_visible(self):
        pose = {'upperarm_r': (0, -1, 1, 0, 0, 0)}
        row = self.run_audit([(1, 0, 0)]*2, [pose]*2)
        self.assertEqual(row['worst_direction']['error_deg'], 90)

    def test_camera_axis_is_unmeasured_not_correct(self):
        pose = {'upperarm_r': (1, 0, 0, 1, 0, 0)}
        row = self.run_audit([(0, 0, 1)]*2, [pose]*2)
        self.assertIsNone(row['worst_direction'])
        self.assertEqual(row['unreliable_times'], [0, 1])

    def test_screen_down_source_is_converted(self):
        pose = {'upperarm_r': (0, 1, -1, 0, 0, 0)}
        row = self.run_audit([(0, 1, 0)]*2, [pose]*2)
        self.assertEqual(row['worst_direction']['error_deg'], 0)

    def test_invalid_sample_grid_rejected(self):
        with self.assertRaisesRegex(ValueError, 'times_invalid'):
            audit({}, 'motion', {}, [1, 0])

    def test_angle_wrap_is_not_a_half_turn(self):
        angles = [179, -179]
        vectors = [(math.cos(math.radians(a)), -math.sin(math.radians(a)), 0) for a in angles]
        poses = [{'upperarm_r': (x, 0, -y, 1, 0, 0)} for x, y, _ in vectors]
        row = self.run_audit(vectors, poses)
        self.assertAlmostEqual(row['worst_step']['excess_step_deg'], 0)
        self.assertAlmostEqual(row['worst_step']['target_step_deg'], 2)
