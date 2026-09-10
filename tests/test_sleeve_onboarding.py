"""Project sleeve editor source closure, explicit save, and stale-state guards."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_sleeve_onboarding_source import inputs as fixture
from autospine_workbench.automation.sleeve_onboarding import SleeveOnboarding, KIND
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.benchmark.mesh_storage import read_mesh_report


class SleeveOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sha = 'c'*64
        self.input = fixture()
        self.input.assert_current = lambda: None
        self.projects = SimpleNamespace(state_root=self.root,
            get_project=lambda project: {'resolved': {'sha256': self.sha}})
        self.service = SleeveOnboarding(self.projects)

        @contextmanager
        def current(*args):
            yield self.input
        self.mock = patch('autospine_workbench.automation.sleeve_onboarding.load_inputs', current)
        self.mock.start(); self.addCleanup(self.mock.stop)

    def prepare(self):
        return self.service.prepare('fresh', self.sha)

    def save_body(self):
        value, _, _, draft = self.service.read_current('fresh')
        return dict(expected_resolved_sha256=self.sha, expected_revision=value['revision'], draft=deepcopy(draft))

    def test_prepare_roundtrip_is_idempotent_and_initial_draft_cannot_build(self):
        self.assertEqual(self.service.status('fresh')['status'], 'needs_preparation')
        status = self.prepare()
        self.assertEqual(status['status'], 'ready')
        self.assertFalse(status['can_build'])
        self.assertEqual(self.prepare(), status)
        value, source, candidate, draft = self.service.read_current('fresh')
        self.assertEqual(source['schema'], 'autospine.component-mesh-candidates/v1')
        self.assertEqual(candidate['schema'], 'autospine.sleeve-regions/v2')
        self.assertTrue(all(a['origin'] == 'pending' for r in draft['records'] for a in r['assignments']))
        with self.assertRaises(PipelineRunError):
            self.service.read_current('fresh', require_saved=True)
        closure = read_mesh_report(self.root, KIND, value['closure_sha256'])
        self.assertEqual(closure['documents']['plan']['profile'], 'sleeve-onboarding-v1')
        restarted = SleeveOnboarding(self.projects)
        self.assertEqual(restarted.read_current('fresh'), (value, source, candidate, draft))

    def test_explicit_save_cas_and_draft_tamper(self):
        self.prepare()
        body = self.save_body()
        original = deepcopy(body)
        body['draft']['records'][0]['assignments'][0].update(role='sleeve', origin='manual_edit')
        result = self.service.save('fresh', body)
        self.assertTrue(result['can_build'])
        self.assertEqual(result['revision'], 2)
        with self.assertRaises(PipelineRunError):
            self.service.save('fresh', original)
        bad = self.save_body(); bad['draft']['candidate_sha256'] = 'f'*64
        with self.assertRaises(ValueError):
            self.service.save('fresh', bad)
        self.assertEqual(self.service.status('fresh')['revision'], 2)
        self.assertEqual(self.service.read_current('fresh', require_saved=True)[3], body['draft'])

    def test_project_revision_change_blocks_old_editor_and_read(self):
        self.prepare(); self.sha = 'd'*64
        self.assertEqual(self.service.status('fresh')['status'], 'stale')
        with self.assertRaises(PipelineRunError):
            self.service.prepare('fresh', 'c'*64)
        with self.assertRaises(PipelineRunError):
            self.service.page('fresh')

    def test_registration_change_blocks_save_and_saved_source_read(self):
        self.prepare(); self.service.save('fresh', self.save_body())
        body = self.save_body()
        self.input.source_addresses['input_identity_sha256'] = 'e'*64
        status = self.service.status('fresh')
        self.assertEqual(status['status'], 'stale')
        self.assertFalse(status['can_build'])
        self.assertIsNone(status['review_url'])
        with self.assertRaises(PipelineRunError):
            self.service.save('fresh', body)
        with self.assertRaises(PipelineRunError):
            self.service.read_current('fresh', require_saved=True)
        # Preparing again must replace the stale mesh source, not return the old page.
        prepared = self.prepare()
        self.assertEqual(prepared['revision'], 3)
        self.assertFalse(prepared['can_build'])
        self.assertEqual(self.service.read_current('fresh')[0]['input_addresses'], self.input.source_addresses)

    def test_missing_closure_is_not_accepted_as_valid_current_source(self):
        self.prepare()
        value = self.service.read_current('fresh')[0]
        files = list(self.root.rglob(value['closure_sha256']+'.json'))
        self.assertEqual(len(files), 1)
        files[0].unlink()
        with self.assertRaises((PipelineRunError, ValueError)):
            self.service.read_current('fresh')

    def test_page_has_optional_explicit_save_bridge_and_current_revision(self):
        self.prepare()
        page = self.service.page('fresh').decode('utf-8')
        self.assertIn('onSave: async draft', page)
        self.assertIn('/api/projects/fresh/automation/sleeves/annotation/save', page)
        self.assertIn('expected_revision:projectSave.revision', page)
        self.assertIn('projectSave.revision=result.revision', page)
        self.assertIn('动画时间轴', page)
        self.assertEqual(page.count('const projectSave ='), 1)


if __name__ == '__main__':
    unittest.main()
