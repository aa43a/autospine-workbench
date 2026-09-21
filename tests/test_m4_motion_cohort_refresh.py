import copy
import unittest
from m4_motion_cohort import digest
from m4_motion_cohort_refresh import refresh


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.plan = dict(motions=[dict(id='wave', sha256='source')], characters=[dict(id='alice')])
        self.state = dict(plan_sha256=digest(self.plan), sources={'wave': dict(status='succeeded', job_id='source')},
            cells={'wave/alice': dict(status='succeeded', job_id='target', result=dict(artifact_sha256='artifact'))},
            diagnostics={'wave/alice': dict(job_id='target', geometry={'preserved': True})})
        self.calls = []

    def request(self, path):
        self.calls.append(path)
        if path.endswith('/source'):
            return dict(job_id='source', status='succeeded', source_sha256='source')
        if path.endswith('/target'):
            return copy.deepcopy(self.state['cells']['wave/alice'])
        return dict(artifact_sha256='artifact', has_incomplete_checks=True)

    def test_new_snapshot_preserves_history(self):
        before = copy.deepcopy(self.state)
        result = refresh(self.plan, self.state, self.request)
        self.assertEqual(self.state, before)
        row = result['diagnostics']['wave/alice']
        self.assertTrue(row['depth_status']['has_incomplete_checks'])
        self.assertEqual(row['geometry'], {'preserved': True})
        self.assertEqual(self.calls.count('/api/motions/target'), 2)

    def test_diagnostic_identity_rejected(self):
        def request(path):
            row = self.request(path)
            if '/view/' in path: row['artifact_sha256'] = 'changed'
            return row
        with self.assertRaisesRegex(ValueError, 'diagnostic_artifact'):
            refresh(self.plan, self.state, request)

    def test_changed_candidate_after_reads_rejected(self):
        def request(path):
            row = self.request(path)
            if self.calls.count('/api/motions/target') == 2: row['status'] = 'failed'
            return row
        with self.assertRaisesRegex(ValueError, 'candidate_changed'):
            refresh(self.plan, self.state, request)

    def test_plan_rejected_before_reads(self):
        self.state['plan_sha256'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'plan_identity'):
            refresh(self.plan, self.state, self.request)
        self.assertEqual(self.calls, [])

    def test_source_identity_rejected(self):
        def request(path):
            row = self.request(path)
            if path.endswith('/source'): row['source_sha256'] = 'different'
            return row
        with self.assertRaisesRegex(ValueError, 'source_changed'):
            refresh(self.plan, self.state, request)
        self.assertEqual(self.calls, ['/api/motions/source'])

    def test_nonterminal_candidate_not_read_or_changed(self):
        self.state['cells']['wave/alice']['status'] = 'running'
        result = refresh(self.plan, self.state, self.request)
        self.assertEqual(result['cells'], self.state['cells'])
        self.assertEqual(self.calls, ['/api/motions/source'])
