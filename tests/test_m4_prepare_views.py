"""Source selection cannot bypass identity or duplicate uncertain submissions."""
from copy import deepcopy
from io import BytesIO
import unittest
from urllib.error import HTTPError
from unittest.mock import Mock

from test_m4_motion_cohort import module

views = module('m4_prepare_views')
plans = module('m4_view_cohort_plan')
oblique_plans = module('m4_oblique_cohort_plan')


class PrepareViewsTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'motions': [dict(id='walk', job_id='old', sha256='raw', view='front')]}
        self.state = {'sources': {}}
        self.comparison = dict(profile=views.PROFILE, source_sha256='raw', source_job_id='old',
                               recommended_view='side', comparison_sha256='receipt', records=[])
        self.saved = []

    def run_step(self, request):
        return views.step(self.plan, self.state, lambda s: self.saved.append(deepcopy(s)), request)

    def test_preserve_receipt_and_resume_exact_job(self):
        request = Mock(side_effect=[self.comparison, {'jobs': []}, {'job_id': 'new', 'status': 'pending'}])
        self.assertEqual(self.run_step(request), 'view_submitted')
        self.assertIn('submitting', self.saved[0])
        self.assertNotIn('submitting', self.state)
        request.assert_called_with('/api/motions/old/reproject', {'view': 'side', 'comparison_sha256': 'receipt'})
        request = Mock(return_value=dict(status='succeeded', source_sha256='raw', view='side',
                                        result={'motion_status': 'compiled', 'motion': {'clip': 'verified'}}))
        self.assertEqual(self.run_step(request), 'terminal')
        request.assert_called_once_with('/api/motions/new')

    def test_no_supported_view_does_not_submit(self):
        self.comparison['recommended_view'] = None
        request = Mock(return_value=self.comparison)
        self.assertEqual(self.run_step(request), 'unsupported_projection')
        self.assertEqual(self.run_step(request), 'terminal')
        self.assertEqual(request.call_count, 1)

    def test_retain_current_and_verify_identity(self):
        self.comparison['recommended_view'] = 'front'
        self.assertEqual(self.run_step(Mock(return_value=self.comparison)), 'current_view_retained')
        with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
            self.run_step(Mock(return_value=dict(status='succeeded', source_sha256='changed', view='front')))

    def test_explicit_queue_race_rejection_can_retry(self):
        error = HTTPError('url', 400, 'full', {}, BytesIO(b'{"reason_code":"motion_queue_full"}'))
        self.assertEqual(self.run_step(Mock(side_effect=[self.comparison, {'jobs': []}, error])), 'waiting_capacity')
        self.assertNotIn('submitting', self.state)

    def test_unknown_submission_failure_cannot_retry(self):
        with self.assertRaises(TimeoutError):
            self.run_step(Mock(side_effect=[self.comparison, {'jobs': []}, TimeoutError()]))
        request = Mock()
        with self.assertRaisesRegex(ValueError, 'reconcile'):
            self.run_step(request)
        request.assert_not_called()

    def test_comparison_identity_checked_before_submission(self):
        self.comparison['source_sha256'] = 'changed'
        request = Mock(return_value=self.comparison)
        with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
            self.run_step(request)
        self.assertEqual(request.call_count, 1)

    def test_alternative_plan_keeps_baseline_and_rejects_incomplete_sources(self):
        self.state['plan_sha256'] = views.digest(self.plan)
        row = dict(source_sha256='raw', parent_job_id='old', profile=views.PROFILE,
                   status='running', view='side', job_id='new', comparison_sha256='receipt',
                   motion_identity={'clip': 'verified'}, views=[dict(view='side', passed=True)])
        self.state['sources']['walk'] = row
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            plans.build(self.plan, self.state)
        row['status'] = 'succeeded'
        result = plans.build(self.plan, self.state)
        self.assertEqual(result['motions'][0]['job_id'], 'new')
        self.assertEqual(result['motions'][0]['comparison_sha256'], 'receipt')
        self.assertEqual(self.plan['motions'][0]['job_id'], 'old')
        row['status'] = 'unsupported_projection'
        row['view'] = None
        result = plans.build(self.plan, self.state)
        self.assertEqual(result['motions'], [])
        self.assertEqual(len(result['unchanged_or_unsupported_sources']), 1)

    def test_oblique_plan_requires_exact_qualified_angle(self):
        summary=dict(plan_sha256=views.digest(self.plan),records=[dict(source='walk',source_qualified_yaw=-45,
            records=[dict(yaw=-45,status='compiled',projection_passed=True,motion_sha256='compiled')])])
        result=oblique_plans.build(self.plan,summary)
        self.assertEqual(result['motions'][0]['projection']['yaw_degrees'],-45)
        self.assertNotIn('projection',self.plan['motions'][0])
        summary['records'][0]['records'][0]['projection_passed']=False
        with self.assertRaisesRegex(ValueError,'not_qualified'):
            oblique_plans.build(self.plan,summary)


if __name__ == '__main__':
    unittest.main()
