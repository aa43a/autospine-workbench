import math
import unittest
from autospine_workbench.targets.character43.rotation_diagnostics import summarize, bvh_vectors
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion2d.mixamo_map import build_map
from test_mixamo_map import source


def vectors(angles):
    return [(math.cos(math.radians(a)), math.sin(math.radians(a)), 1) for a in angles]


class RotationDiagnosticsTests(unittest.TestCase):
    def test_branch_crossing_is_small_continuous_step(self):
        row = summarize({'arm': vectors([179, -179, -177])}, [0, .1, .2])['records'][0]
        self.assertAlmostEqual(row['continuous_angles'][1], 181)
        self.assertEqual(row['events'][0]['reason'], 'angle_branch_crossing')

    def test_real_multiple_turns_are_not_clamped(self):
        angles = list(range(0, 721, 30))
        row = summarize({'arm': vectors(angles)}, list(range(len(angles))))['records'][0]
        self.assertAlmostEqual(row['runs'][0]['net_turns'], 2)

    def test_degenerate_interval_does_not_invent_winding(self):
        data = vectors([170])+[(0, 0, 1)]+vectors([-170, -160])
        row = summarize({'arm': data}, [0, 1, 2, 3])['records'][0]
        self.assertIsNone(row['continuous_angles'][1])
        self.assertAlmostEqual(row['continuous_angles'][2], -170)
        self.assertEqual(len(row['runs']), 2)

    def test_exact_half_turn_is_ambiguous(self):
        row = summarize({'arm': vectors([0, 180])}, [0, 1])['records'][0]
        self.assertIsNone(row['continuous_angles'][1])
        self.assertEqual(row['events'][0]['reason'], 'half_turn_direction_ambiguous')

    def test_invalid_times_and_vectors_fail(self):
        for times, data in [([0, 0], vectors([0, 1])), ([0, 1], [(2, 0, 1)]*2)]:
            with self.assertRaises(ValueError): summarize({'arm': data}, times)

    def test_real_bvh_adapter(self):
        bvh = parse_bvh(source())
        mapping = build_map(bvh, clip_id='rotation', reference_length=10,
                            screen_x='+X', screen_y='-Y', depth='+Z')
        report = summarize(*bvh_vectors(bvh, mapping))
        self.assertEqual(len(report['records']), 8)
        self.assertEqual(report['authority'], 'none')


if __name__ == '__main__': unittest.main()
