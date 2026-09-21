import unittest
from autospine_workbench.targets.character43.depth_model_evidence import index, lookup


class DepthModelEvidenceTests(unittest.TestCase):
    def test_uncertainty_is_not_opposing_support(self):
        for front, back, ambiguous, unknown, expected in [
            (0, 0, 12, 0, 'interval_margin_uncertain'),
            (5, 7, 0, 0, 'opposing_model_support'),
            (5, 0, 0, 1, 'missing_depth_support'),
            (12, 0, 0, 0, 'uniform_model_support')]:
            check=dict(time=.5, counts=dict(front=front, back=back, ambiguous=ambiguous, unknown=unknown))
            depth=dict(regional=dict(refinement=dict(rows=[dict(pair=['a', 'b'], checks=[check])])))
            evidence=index(depth)
            row=lookup(evidence, dict(pair=['b', 'a'], time=0, overlap=dict(time=.5)))
            self.assertEqual(row['kind'], expected)
            self.assertIsNone(lookup(evidence, dict(pair=['a', 'b'], time=0)))

    def test_missing_counts_are_not_invented(self):
        depth=dict(regional=dict(refinement=dict(rows=[dict(pair=['a', 'b'],checks=[dict(time=0,status='unmeasured')])])) )
        self.assertEqual(index(depth), {})
        self.assertIsNone(lookup({}, dict(time=0)))
