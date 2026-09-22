import unittest
from m4_support_capture_grid import build


class CaptureGridTests(unittest.TestCase):
    def values(self):
        doc={'animations':{'move':{'bones':{'root':{'rotate':[{'time':0},{'time':1}]}},
            'attachments':{'default':{'slot':{'mesh':{'deform':[{'time':.3}]}}}}}}}
        return doc, {'candidate_rows':[{'time':0},{'time':1}]}

    def test_feedback_and_new_mesh_midpoints_survive_without_recursive_growth(self):
        doc, seq=self.values();seq['verification_time_grid']=[0,.123,1]
        self.assertEqual(build(doc,'move',seq),[0,.123,.15,.3,.65,1])

    def test_legacy_feedback_is_retained(self):
        doc,seq=self.values();seq['check_times']=[.123]
        self.assertIn(.123,build(doc,'move',seq))

    def test_invalid_feedback_rejected(self):
        for t in (-.01,1.01,float('nan')):
            doc,seq=self.values();seq['verification_time_grid']=[t]
            with self.assertRaisesRegex(ValueError,'feedback_time_invalid'):build(doc,'move',seq)

    def test_over_budget_grid_is_never_truncated(self):
        doc,seq=self.values();seq['verification_time_grid']=[i/5000 for i in range(5001)]
        with self.assertRaisesRegex(ValueError,'sample_limit'):build(doc,'move',seq)
