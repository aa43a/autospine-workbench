import copy
import unittest
from m4_skirt_model_review import disagreements


class ModelReviewTests(unittest.TestCase):
    def reports(self):
        a = dict(artifact_sha256='a', experiment_sha256='b', times=[0, 1], rows=[
            dict(time=0, pair=['leg', 'skirt'], status='uniform_front_proxy'),
            dict(time=1, pair=['leg', 'skirt'], status='requires_partition_or_more_depth')])
        b = copy.deepcopy(a)
        b['rows'][0]['status'] = 'uniform_back_proxy'
        return a, b

    def test_only_opposite_observable_verdicts(self):
        a, b = self.reports()
        self.assertEqual(len(disagreements(a, b)), 1)
        b['rows'][0]['status'] = 'requires_partition_or_more_depth'
        self.assertEqual(disagreements(a, b), [])

    def test_reject_mismatched_evidence(self):
        for field in ('artifact_sha256', 'experiment_sha256', 'times'):
            a, b = self.reports()
            b[field] = 'different'
            with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
                disagreements(a, b)

    def test_missing_and_duplicate_rows_are_not_silent(self):
        a, b = self.reports()
        b['rows'].pop()
        with self.assertRaisesRegex(ValueError, 'missing_pair'):
            disagreements(a, b)
        a, b = self.reports()
        b['rows'].append(b['rows'][0])
        with self.assertRaisesRegex(ValueError, 'duplicate_row'):
            disagreements(a, b)
