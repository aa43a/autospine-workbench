import unittest
from copy import deepcopy
from autospine_workbench.automation.sleeve_final_status import finalize


class SleeveFinalStatusTests(unittest.TestCase):
    def report(self):
        return dict(records=[dict(status='candidate_exported', download='candidate.zip',
            reason_code='runtime_and_alpha_contact_required', runtime_status='core_passed',
            official_framebuffer=dict(failed_samples=0))])

    def test_completed_measurements_still_require_review_without_mutating_history(self):
        source=self.report(); original=deepcopy(source); result=finalize(source)
        self.assertEqual(source, original)
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(result['alpha_contact_status'], 'sampled_contacts_passed')
        self.assertEqual(result['records'][0]['reason_code'], 'sleeve_occlusion_review_required')
        self.assertFalse(result['production_authorized'])

    def test_any_explicit_failure_blocks_its_download(self):
        for field, value in [('runtime_status','core_failed'), ('official_framebuffer',dict(failed_samples=1))]:
            source=self.report(); source['records'][0][field]=value
            result=finalize(source)
            self.assertEqual(result['status'], 'blocked')
            self.assertIsNone(result['records'][0]['download'])

    def test_partial_capture_cannot_claim_all_region_contacts_passed(self):
        source=self.report(); source['records'].append(dict(status='blocked', download='stale.zip',reason_code='mesh_failed'))
        result=finalize(source)
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(result['alpha_contact_status'], 'partially_evaluated')
        self.assertEqual(result['records'][1]['reason_code'], 'mesh_failed')
        self.assertIsNone(result['records'][1]['download'])

    def test_missing_stage_remains_explicit_and_empty_is_blocked(self):
        source=self.report(); del source['records'][0]['official_framebuffer']
        result=finalize(source)
        self.assertEqual(result['alpha_contact_status'], 'not_evaluated')
        self.assertEqual(result['records'][0]['reason_code'], 'official_framebuffer_required')
        source=self.report(); del source['records'][0]['runtime_status']
        self.assertEqual(finalize(source)['records'][0]['reason_code'], 'official_core_required')
        self.assertEqual(finalize(dict(records=[]))['status'], 'blocked')
