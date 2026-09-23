import unittest

from autospine_workbench.targets.character43.group_bend_evidence import evidence, summarize
from autospine_workbench.targets.character43.group_projection_constraints import circle_joint


class BendEvidenceTests(unittest.TestCase):
    def test_matches_geometric_branch_and_scale(self):
        for sign in (-1, 1):
            knee = circle_joint([0, 0], [0, -1], 1, 1, sign)
            upper = [*knee, 0]
            lower = [-knee[0], -1-knee[1], 0]
            for scale in (.001, 1, 1000):
                self.assertEqual(evidence([v*scale for v in upper], [v*scale for v in lower], 0)['branch'], sign)

    def test_depth_bend_requires_declared_view(self):
        a, b = [0, -1, 1], [0, -1, -1]
        self.assertIsNone(evidence(a, b, 0)['branch'])
        self.assertEqual(evidence(a, b, 90)['branch'], -evidence(a, b, -90)['branch'])

    def test_straight_and_collapsed_are_unknown(self):
        self.assertIsNone(evidence([0, -1, 0], [0, -1, 0], 0)['branch'])
        self.assertEqual(evidence([1, 0, 0], [-1, 0, 0], 0)['reason'], 'endpoint_projection_collapsed')

    def test_invalid(self):
        for upper in ([0, 0, 0], [float('nan'), 1, 0]):
            with self.assertRaises(ValueError):
                evidence(upper, [0, -1, 0], 0)

    def test_report_rejects_disconnected_or_misaligned_source(self):
        segments = {}
        for side in ('left', 'right'):
            segments[f'humanoid.leg.upper.{side}'] = [([0, 0, 0], [0, -1, 1])]
            segments[f'humanoid.leg.lower.{side}'] = [([0, -1, 1], [0, -1, -1])]
        report = summarize(segments, [0], -90)
        self.assertEqual(report['records'][0]['counts']['1'], 1)
        with self.assertRaises(ValueError):
            summarize(segments, [0, 1], -90)
        segments['humanoid.leg.lower.left'][0] = ([1, -1, 1], [0, -1, -1])
        with self.assertRaises(ValueError):
            summarize(segments, [0], -90)
