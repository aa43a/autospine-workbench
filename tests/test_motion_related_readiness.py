"""Supplemental evidence cannot make unknown full-motion depth pass."""
import unittest
from copy import deepcopy
import test_motion_related_contact as fixtures
from autospine_workbench.automation.motion_related_review import readiness


class RelatedReadinessTests(unittest.TestCase):
    def test_contact_pass_does_not_complete_missing_geometry_projection_depth(self):
        f = fixtures.RelatedContactTests(); f.setUp()
        value = dict(candidate_sha256=f.f.receipt['candidate_bundle_sha256'], runtime=f.f.runtime,
                     baseline_sha256='baseline', request_sha256='request', evidence=f.f.check())
        result = readiness(value, f.f.files, 'e'*64)
        states = {s['stage']:s['status'] for s in result['stages']}
        self.assertEqual(states['Runtime'], 'sampled_pass')
        self.assertEqual(states['接触'], 'sampled_pass')
        self.assertEqual(states['脚端复测'], 'sampled_pass')
        self.assertEqual(states['投影'], 'unmeasured')
        self.assertEqual(states['几何'], 'unmeasured')
        self.assertEqual(states['遮挡'], 'unmeasured')
        self.assertEqual(result['status'], 'evidence_incomplete')
        changed = deepcopy(value)
        changed['evidence']['additional_checks']['moving_ankles']['passed'] = False
        self.assertEqual(readiness(changed, f.f.files, 'e'*64)['status'], 'needs_changes')
        changed = deepcopy(value); changed['evidence']['skirt_checks'] = {'status':'requires_review'}
        self.assertEqual(readiness(changed, f.f.files, 'e'*64)['stages'][-1]['status'], 'unmeasured')
        changed['evidence']['pose_checks'] = {'samples':57, 'status':'requires_review'}
        final = readiness(changed, f.f.files, 'e'*64)
        self.assertEqual(final['stages'][-1]['stage'], '源姿态复测')
        self.assertEqual(final['stages'][-1]['status'], 'unmeasured')
        self.assertEqual(final['status'], 'evidence_incomplete')
