import json
from hashlib import sha256
import unittest
from unittest.mock import patch

from autospine_workbench.targets.character43.motion_readiness import build


def fixture():
    digest = sha256(b'{}').hexdigest()
    files = {'skeleton.json': b'{}'}
    for name, value in {
        'motion-review.json': dict(projected_lengths={'profile': 'test'}, issues=[]),
        'deformation.json': dict(skeleton_sha256=digest, passed=True, records=[]),
        'motion-contact.json': dict(status='ankle_proxy_passed'),
        'motion-depth.json': dict(skeleton_sha256=digest, order={'status': 'no_visible_order_change'},
                                  target_overlap={'unmeasured_pair_samples': 0}),
    }.items(): files[name] = json.dumps(value).encode()
    return files, dict(bundle_sha256='a'*64, passed=True, results=[{}])


class ReadinessTests(unittest.TestCase):
    def test_sampled_pass_never_means_accepted(self):
        files, runtime = fixture()
        report = build(files, 'a'*64, runtime)
        self.assertEqual(report['status'], 'stage_review')
        self.assertFalse(report['production_authorized'])
        self.assertEqual(report['human_visual_acceptance'], 'not_recorded_here')

    def test_depth_conflict_overrides_successful_runtime(self):
        files, runtime = fixture()
        depth = json.loads(files['motion-depth.json'])
        depth['order'] = dict(status='blocked', failures=[dict(time=.25, reason_code='visible_unmapped_order_conflict')])
        files['motion-depth.json'] = json.dumps(depth).encode()
        report = build(files, 'a'*64, runtime)
        self.assertEqual(report['status'], 'needs_changes')
        self.assertEqual(report['stages'][3]['failures'][0]['time'], .25)

    def test_missing_evidence_stays_incomplete(self):
        files, _ = fixture(); del files['motion-depth.json']
        report = build(files, 'a'*64)
        self.assertEqual(report['status'], 'evidence_incomplete')
        self.assertEqual(report['stages'][-1]['status'], 'unmeasured')

    def test_partial_contact_is_not_full_contact_pass(self):
        files, runtime = fixture()
        files['motion-contact.json'] = b'{"status":"inferred_partial_corrected","selected":true}'
        report = build(files, 'a'*64, runtime)
        self.assertEqual(report['status'], 'evidence_incomplete')
        self.assertEqual(report['stages'][2]['status'], 'unmeasured')

    def test_wrong_runtime_or_geometry_identity_rejected(self):
        files, runtime = fixture()
        with self.assertRaisesRegex(ValueError, 'runtime_mismatch'):
            build(files, 'b'*64, runtime)
        files['deformation.json'] = b'{"skeleton_sha256":"wrong"}'
        with self.assertRaisesRegex(ValueError, 'skeleton_mismatch'):
            build(files, 'a'*64, runtime)

    def test_endpoint_without_runtime_directory(self):
        from autospine_workbench.automation.motion_target_jobs import review_file
        files, _ = fixture()
        with patch('autospine_workbench.automation.motion_target_jobs.context',
                   return_value=(dict(artifact_sha256='a'*64, runtime={'status': 'unavailable'}), files)):
            raw, kind = review_file(None, 'test', ['readiness.json'])
        self.assertEqual(kind, 'application/json')
        self.assertEqual(json.loads(raw)['status'], 'evidence_incomplete')
