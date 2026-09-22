from copy import deepcopy
import unittest
from m4_reach_order_interval import select


class IntervalTests(unittest.TestCase):
    def evidence(self):
        return dict(strict_interval_evidence=True, pairs=[dict(arm_slot='arm', samples=[
            dict(tick=0, ambiguous=True, support='unknown'),
            dict(tick=1000000, ambiguous=False, support='uniform_front_proxy', interval_sample=
                 dict(ambiguous=False, support='uniform_front_proxy'))])])

    def test_preserves_original_unresolved_evidence(self):
        data = self.evidence(); old = deepcopy(data)
        result = select(data, 'arm', 1)
        self.assertEqual(data, old)
        self.assertEqual(len(result['pairs'][0]['samples']), 1)

    def test_uncertain_midpoint_is_not_dropped(self):
        data = self.evidence()
        data['pairs'][0]['samples'][1]['interval_sample']['ambiguous'] = True
        with self.assertRaises(ValueError): select(data, 'arm', 1)

    def test_start_must_be_exact_not_rounded_forward(self):
        with self.assertRaises(ValueError): select(self.evidence(), 'arm', .9)
