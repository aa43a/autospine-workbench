"""Cohort orchestration must not retry failed work or erase unknown QA."""
import importlib.util
from pathlib import Path
import unittest
import sys


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / 'tools' / (name+'.py'))
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


runner = module('m4_motion_cohort')
report = module('m4_motion_cohort_report')


class CohortTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'motions': [{'id': 'walk', 'sha256': 'raw', 'view': 'front'}],
                     'characters': [{'id': 'a', 'project_id': 'a', 'job_id': 'c', 'sha256': 'rig'}]}
        self.source = dict(job_id='source', status='succeeded', source_sha256='raw', view='front')
        self.state = dict(sources={'walk': self.source}, cells={})

    def test_failed_target_is_not_resubmitted(self):
        failure = dict(job_id='target', status='failed', reason_code='geometry_failure')
        self.state['cells']['walk/a'] = failure
        calls = []
        def request(path, *args):
            calls.append(path)
            return self.source if path.endswith('source') else failure
        self.assertEqual(runner.step(self.plan, self.state, lambda _: None, request), 'terminal')
        self.assertFalse(any('/adapt' in p for p in calls))

    def test_uncertain_post_requires_reconciliation(self):
        self.state['submitting'] = {'cell': 'walk/a'}
        with self.assertRaisesRegex(ValueError, 'uncertain_submission'):
            runner.step(self.plan, self.state, lambda _: None, lambda *_: self.fail())

    def test_changed_source_blocks_new_targets(self):
        with self.assertRaisesRegex(ValueError, 'identity_changed'):
            runner.step(self.plan, self.state, lambda _: None,
                        lambda *_: dict(self.source, source_sha256='changed'))

    def test_changed_execution_policy_stops_matrix_without_replacing_job(self):
        self.plan['expected_profiles'] = {'inferred_contact_profile': 'new'}
        target = dict(job_id='target', status='succeeded', result={'inferred_contact_profile': 'old'})
        self.state['cells']['walk/a'] = target
        def request(path, *args):
            if path.endswith('source'): return self.source
            if path.endswith('motion-depth.json'): return {'profile': 'depth'}
            return target
        with self.assertRaisesRegex(ValueError, 'execution_profile_mismatch'):
            runner.step(self.plan, self.state, lambda _: None, request)
        self.assertEqual(self.state['cells']['walk/a']['job_id'], 'target')

    def test_runtime_completion_does_not_hide_quality_failure(self):
        self.state['cells']['walk/a'] = dict(job_id='target', status='succeeded', result={
            'geometry_passed': False, 'character_animation_status': 'needs_changes',
            'issues': [{'stage': 'projection', 'reason_code': 'collapse'}]})
        row = report.rows(self.plan, self.state)[0]
        self.assertFalse(row['geometry'])
        self.assertEqual(row['candidate'], 'needs_changes')
        self.assertEqual(row['visual'], 'not_evaluated')
        self.assertEqual(row['contact'], 'not_evaluated')
        self.assertEqual(row['depth'], 'not_evaluated')
        counts = report.summary([row])
        self.assertEqual(counts['candidate_exceptions'], 1)
        self.assertEqual(counts['geometry_passed'], 0)
        self.assertEqual(counts['visual_accepted'], 0)
        self.assertEqual(counts['contact_unmeasured'], 1)

    def test_first_geometry_failure_is_linked_to_time(self):
        self.state['cells']['walk/a'] = dict(job_id='target', status='succeeded')
        self.state['diagnostics'] = {'walk/a': dict(job_id='target', geometry={'records': [
            {'slot': 'arm-left', 'passed': False, 'first_failure': {'time': 1.25}}]})}
        self.assertIn('player.html?time=1.25', report.render(self.plan, self.state))
        self.state['diagnostics']['walk/a']['job_id'] = 'other'
        with self.assertRaisesRegex(ValueError, 'diagnostic_job_mismatch'):
            report.rows(self.plan, self.state)

    def test_partial_support_and_runtime_do_not_become_stage_acceptance(self):
        self.state['cells']['walk/a'] = dict(job_id='target', status='succeeded', result={
            'artifact_sha256': 'asset', 'geometry_passed': True,
            'contact_status': 'inferred_partial_corrected', 'runtime': {'frames': 123}})
        self.state['diagnostics'] = {'walk/a': dict(job_id='target', readiness={
            'artifact_sha256': 'asset', 'status': 'needs_changes', 'stages': []})}
        counts = report.summary(report.rows(self.plan, self.state))
        self.assertEqual(counts['captured'], 1)
        self.assertEqual(counts['contact_partial'], 1)
        self.assertEqual(counts['stage_review_ready'], 0)
        self.assertEqual(counts['candidate_exceptions'], 1)
        self.assertEqual(counts['visual_accepted'], 0)
        self.assertIn('depth.html', report.render(self.plan, self.state))
        self.state['diagnostics']['walk/a']['readiness']['artifact_sha256'] = 'old'
        with self.assertRaisesRegex(ValueError, 'readiness_artifact_mismatch'):
            report.rows(self.plan, self.state)


if __name__ == '__main__':
    unittest.main()
