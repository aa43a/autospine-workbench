"""Cohort orchestration must not retry failed work or erase unknown QA."""
import importlib.util
from pathlib import Path
import unittest
import sys
import json
from tempfile import TemporaryDirectory
from unittest.mock import patch


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / 'tools' / (name+'.py'))
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


runner = module('m4_motion_cohort')
reviews = module('m4_motion_cohort_reviews')
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

    def test_maintenance_checkpoint_exits_without_contacting_server(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); plan = root/'plan.json'; state = root/'state.json'
            plan.write_text(json.dumps(self.plan), encoding='utf-8')
            state.with_suffix('.stop').write_text('maintenance', encoding='utf-8')
            with patch.object(sys, 'argv', ['runner', str(plan), str(state)]), \
                    patch.object(runner, 'api', side_effect=AssertionError('must not submit')):
                runner.main()
            self.assertFalse(state.with_suffix('.lock').exists())
            self.assertFalse(state.exists())

    def test_uncertain_post_requires_reconciliation(self):
        self.state['submitting'] = {'cell': 'walk/a'}
        with self.assertRaisesRegex(ValueError, 'uncertain_submission'):
            runner.step(self.plan, self.state, lambda _: None, lambda *_: self.fail())

    def test_target_projection_is_submitted_and_verified(self):
        projection=dict(profile='constant-yaw-source-motion-v1',yaw_degrees=-45)
        self.plan['motions'][0]['projection']=projection
        calls=[]
        def request(path,body=None):
            if body is not None:
                calls.append(body); return dict(job_id='target',status='pending')
            if path.endswith('source'): return self.source
            return dict(artifact_sha256='rig')
        self.assertEqual(runner.step(self.plan,self.state,lambda _:None,request),'target_submitted')
        self.assertEqual(calls[0]['projection'],projection)
        target=dict(job_id='target',status='succeeded',result={'projection':dict(projection,yaw_degrees=45)})
        with self.assertRaisesRegex(ValueError,'target_projection_mismatch'):
            runner.step(self.plan,self.state,lambda _:None,
                        lambda path: self.source if path.endswith('source') else target)

    def test_changed_source_blocks_new_targets(self):
        with self.assertRaisesRegex(ValueError, 'identity_changed'):
            runner.step(self.plan, self.state, lambda _: None,
                        lambda *_: dict(self.source, source_sha256='changed'))

    def test_explicit_depth_strategy_requires_matching_expectation(self):
        self.plan['target_depth_profile'] = 'external-regional-depth-order-v1'
        with self.assertRaisesRegex(ValueError, 'expectation_missing'):
            runner.step(self.plan, self.state, lambda _: None, lambda *_: self.fail())
        self.plan['expected_profiles'] = dict(depth_review_profile=self.plan['target_depth_profile'])
        bodies = []
        def request(path, body=None):
            if body is not None:
                bodies.append(body); return dict(job_id='target', status='pending')
            return self.source if path.endswith('source') else dict(artifact_sha256='rig')
        self.assertEqual(runner.step(self.plan, self.state, lambda _: None, request), 'target_submitted')
        self.assertEqual(bodies[0]['depth_review_profile'], self.plan['target_depth_profile'])

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

    def test_visual_snapshot_preserves_exceptions_and_revocation(self):
        readiness = dict(artifact_sha256='asset', status='needs_changes', stages=[])
        evidence = runner.digest(readiness)
        self.state['plan_sha256'] = runner.digest(self.plan)
        self.state['cells']['walk/a'] = dict(job_id='target', status='succeeded', result={
            'artifact_sha256': 'asset', 'geometry_passed': False})
        self.state['diagnostics'] = {'walk/a': dict(job_id='target', readiness=readiness)}
        row = dict(job_id='target', artifact_sha256='asset', evidence_sha256=evidence,
                   readiness=readiness, revision=1, current_applies=True, current=dict(
                       artifact_sha256='asset', evidence_sha256=evidence,
                       decision='accepted_with_exceptions', notes='限定动作，保留异常'))
        calls = []
        def request(path):
            calls.append(path); return row
        snapshot = reviews.collect(self.plan, self.state, request)
        self.assertEqual(calls, ['/api/motions/target/stage-review'])
        counts = report.summary(report.rows(self.plan, self.state, snapshot))
        self.assertEqual(counts['visual_accepted'], 0)
        self.assertEqual(counts['visual_accepted_with_exceptions'], 1)
        self.assertEqual(counts['candidate_exceptions'], 1)
        self.assertEqual(counts['geometry_passed'], 0)
        row['current']['decision'] = 'revoked'
        self.assertEqual(report.rows(self.plan, self.state, snapshot)[0]['visual'], 'revoked')
        readiness['status'] = 'changed'
        self.assertEqual(report.rows(self.plan, self.state, snapshot)[0]['visual'], 'evidence_changed')
        snapshot['cells']['walk/a']['job_id'] = 'other'
        with self.assertRaisesRegex(ValueError, 'candidate_mismatch'):
            report.rows(self.plan, self.state, snapshot)


if __name__ == '__main__':
    unittest.main()
