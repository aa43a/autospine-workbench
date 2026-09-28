import unittest
from test_limb_region_order import fixture
from m4_neck_order_evidence import convert


class NeckOrderEvidenceTests(unittest.TestCase):
    def data(self):
        diagnosis,partition,source=fixture()
        report=dict(profile='neck-axis-thickness-sensitivity-v1',tested_radii=[0,.02,.05,.1],rows=[])
        for row in diagnosis['rows']:
            report['rows'].append(dict(row,body='neck',hypotheses=[
                dict(radius=r,status='uniform_front_proxy',pair=[row['region'],'neck'],time=row['time'])
                for r in report['tested_radii']]))
        return report,partition,source

    def test_agreement_has_explicit_hypothetical_provenance(self):
        pair=convert(*self.data())[0]
        self.assertEqual(pair['torso_slot'],'neck')
        self.assertEqual(pair['evidence_source'],'declared_neck_thickness_hypothesis_only')
        self.assertFalse(pair['samples'][0]['ambiguous'])

    def test_radius_disagreement_keeps_uncertainty(self):
        args=self.data();args[0]['rows'][1]['hypotheses'][-1]['status']='uniform_back_proxy'
        self.assertTrue(convert(*args)[0]['samples'][0]['interval_sample']['ambiguous'])

    def test_missing_radius_and_missing_midpoint_reject(self):
        args=self.data();args[0]['rows'][0]['hypotheses'].pop()
        with self.assertRaisesRegex(ValueError,'radius_inventory'):convert(*args)
        args=self.data();args[0]['rows'].pop(1)
        with self.assertRaisesRegex(ValueError,'same_time'):convert(*args)

    def test_different_hypothesis_frame_rejected(self):
        args=self.data();args[0]['rows'][0]['hypotheses'][0]['time']=.25
        with self.assertRaisesRegex(ValueError,'sample_identity'):convert(*args)
