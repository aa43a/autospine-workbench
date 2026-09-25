from hashlib import sha256
import json
import unittest
from unittest.mock import patch
from test_motion_readiness import fixture
from autospine_workbench.targets.character43.motion_readiness import build


class InheritedReadinessTests(unittest.TestCase):
    def fixture(self):
        files, runtime = fixture()
        issues = [dict(stage='geometry', reason_code='old_geometry_failure'),
                  dict(stage='contact', reason_code='unresolved_contact')]
        parent = json.dumps(dict(issues=issues)).encode()
        files['parent-motion-review.json'] = parent
        review = json.loads(files['motion-review.json'])
        review.update(issues=issues, inherited_issue_context=dict(issue_count=2,
            source_review_sha256=sha256(parent).hexdigest(), source_skeleton_sha256='b'*64))
        files['motion-review.json'] = json.dumps(review).encode()
        return files, runtime

    def test_current_pass_does_not_clear_inherited_issues_or_reuse_locations(self):
        files, runtime = self.fixture()
        report = build(files, 'a'*64, runtime)
        self.assertEqual(report['status'], 'needs_changes')
        inherited = report['stages'][0]
        self.assertEqual(inherited['stage'], '原候选未解决项')
        self.assertEqual(inherited['failures'], [])
        self.assertEqual(inherited['href'], 'parent-motion-review.json')
        self.assertEqual(inherited['source_skeleton_sha256'], 'b'*64)
        self.assertTrue(all(s['status']=='sampled_pass' for s in report['stages'][1:]))

    def test_tampered_or_missing_parent_cannot_produce_readiness(self):
        for change in ('missing', 'digest', 'inventory', 'count'):
            files, runtime = self.fixture()
            if change=='missing': del files['parent-motion-review.json']
            elif change=='digest': files['parent-motion-review.json'] += b' '
            else:
                review = json.loads(files['motion-review.json'])
                if change=='count': review['inherited_issue_context']['issue_count']=True
                else: review['issues'].pop()
                files['motion-review.json'] = json.dumps(review).encode()
            with self.assertRaisesRegex(ValueError, 'parent_issue'):
                build(files, 'a'*64, runtime)

    def test_parent_report_endpoint_uses_immutable_bundle(self):
        from autospine_workbench.automation.motion_target_jobs import review_file
        files, _ = self.fixture()
        with patch('autospine_workbench.automation.motion_target_jobs.context', return_value=(dict(artifact_sha256='a'*64),files)):
            raw, kind = review_file(None, 'test', ['parent-motion-review.json'])
        self.assertEqual(raw, files['parent-motion-review.json'])
        self.assertEqual(kind, 'application/json')


if __name__=='__main__': unittest.main()
