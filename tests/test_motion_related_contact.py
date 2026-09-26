from hashlib import sha256
import unittest
from autospine_workbench.resolved_project import canonical_sha256
import test_motion_related_evidence as fixtures


class RelatedContactTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.RelatedEvidenceTests();self.f.setUp()
        candidate=self.f.receipt['candidate_bundle_sha256'];skeleton=sha256(b'{}').hexdigest()
        self.audit=dict(profile='corrective-contact-audit-v1',artifact_sha256=candidate,
            runtime_report_sha256=canonical_sha256(self.f.runtime),authority='none',selected=False,
            production_authorized=False,moving_ankles=dict(skeleton_sha256=skeleton,samples=2,
                worst={'error_px':.1},limit_px=1,passed=True),
            contact=dict(artifact_sha256=candidate,runtime_numeric_passed=True,hypothesis={},
                after=dict(max_drift_px=.2,drift_limit_px=1,passed=True),
                final_timeline_check=dict(skeleton_sha256=skeleton,samples=2,
                    animation='external-motion',times_sha256=canonical_sha256([0,1]))))
        self.f.receipt['contact_audit']=self.audit

    def test_checks_are_supplemental_not_admission(self):
        result=self.f.check()
        self.assertTrue(result['additional_checks']['moving_ankles']['passed'])
        self.assertEqual(result['additional_checks']['remaining_checks'],['mesh_sole_contact','depth','visual'])
        self.assertFalse(result['selected']);self.assertFalse(result['production_authorized'])
        del self.f.receipt['contact_audit']
        self.assertNotIn('additional_checks',self.f.check())

    def test_wrong_asset_runtime_or_grid_rejected(self):
        for target,key in ((self.audit,'artifact_sha256'),(self.audit,'runtime_report_sha256'),
                           (self.audit['contact']['final_timeline_check'],'times_sha256')):
            old=target[key];target[key]='e'*64
            with self.assertRaisesRegex(ValueError,'contact_identity'):self.f.check()
            target[key]=old

    def test_failures_retained_and_mislabelled_pass_rejected(self):
        self.audit['moving_ankles']['worst']['error_px']=2
        with self.assertRaisesRegex(ValueError,'contact_measurement'):self.f.check()
        self.audit['moving_ankles']['passed']=False
        self.assertFalse(self.f.check()['additional_checks']['moving_ankles']['passed'])
        self.audit['contact']['after']['max_drift_px']=float('nan')
        with self.assertRaises(ValueError):self.f.check()
