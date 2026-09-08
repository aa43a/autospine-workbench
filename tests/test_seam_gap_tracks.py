import unittest
import numpy as np
from autospine_workbench.targets.spine43.seam_gap_tracks import components, associate


def frame(tick, positions, rect=(0, 0, 16, 16)):
    labels = np.zeros((16, 16), dtype=np.uint8)
    for y, x in positions: labels[y, x] = 1
    return components(labels, rect, tick)


class GapTrackTests(unittest.TestCase):
    def test_diagonal_components_and_world_coordinates(self):
        result = frame(0, [(1, 1), (2, 2), (8, 8)], (100, 200, 16, 16))
        self.assertEqual([c['area_px'] for c in result], [2, 1])
        self.assertEqual(result[0]['pixels_world'][0], [101.5, -201.5])
        self.assertEqual(result[0]['support_counts'], [2, 0, 0])

    def test_moving_roi_preserves_identity(self):
        report = associate([frame(0, [(4, 4)]), frame(1, [(4, 2)], (2, 0, 16, 16))])
        self.assertEqual(len(report['tracks']), 1)
        self.assertEqual(report['tracks'][0]['observed_frames'], 2)

    def test_gap_and_large_motion_break_tracks(self):
        self.assertEqual(len(associate([frame(0, [(4, 4)]), [], frame(2, [(4, 4)])])['tracks']), 2)
        self.assertEqual(len(associate([frame(0, [(4, 4)]), frame(1, [(4, 8)])])['tracks']), 2)

    def test_split_merge_are_ambiguous_not_greedy(self):
        frames = [frame(0, [(4, 4)]), frame(1, [(4, 2), (4, 6)]), frame(2, [(4, 4)])]
        result = associate(frames)
        self.assertEqual(len(result['tracks']), 4)
        self.assertEqual([e['kind'] for e in result['association_events']], ['split_candidate', 'merge_candidate'])
        self.assertEqual(result['pixel_samples'], 4)
        self.assertEqual(result, associate(frames))

    def test_empty_and_invalid_sequence(self):
        self.assertEqual(associate([[], []])['tracks'], [])
        with self.assertRaises(ValueError): associate([frame(1, [(0, 0)])])
