import unittest
from m4_transverse_sampling_probe import inventory


class SamplingProbeTests(unittest.TestCase):
    def test_dense_grid_is_preserved_not_clipped_to_reader_limit(self):
        doc = {'animations':{'motion':{'bones':{'leg':{'rotate':[{'time':i/2048} for i in range(2049)]}}}}}
        report = inventory(doc, 'motion', [.123456789])
        self.assertEqual(report['quarter_sample_count'], 8193)
        self.assertEqual(report['final_sample_count'], 8194)
        self.assertTrue(report['exceeds_reader_limit'])
        self.assertIn(.123456789, report['times'])
        self.assertEqual(report['times'], sorted(set(report['times'])))

    def test_nearby_attachment_keys_are_reported_without_merging(self):
        doc = {'animations':{'motion':{'bones':{'leg':{'rotate':[{'time':0},{'time':1}]}},
            'attachments':{'default':{'leg':{'leg':{'deform':[{'time':1e-12}]}}}}}}}
        report = inventory(doc, 'motion', [0, 1])
        self.assertEqual(report['key_count'], 3)
        self.assertEqual(report['subnanosecond_key_intervals'], 1)
        self.assertIn(1e-12, report['times'])
        self.assertFalse(report['exceeds_reader_limit'])
