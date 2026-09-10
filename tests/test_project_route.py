import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.automation.project_route import ProjectRoute, suggest
from autospine_workbench.automation.pipeline_run import PipelineRunError


class ProjectRouteTests(unittest.TestCase):
    def test_handwear_is_not_automatically_a_sleeve(self):
        project = {'resolved': {'layers': [{'name': 'handwear-l', 'canonical_role': 'body.hand'}]}}
        self.assertEqual(suggest(project)[0], 'undecided')
        project['resolved']['layers'][0].update(name='袖子', bbox={'width': 100, 'height': 200})
        self.assertEqual(suggest(project)[0], 'sleeves')

    def test_choice_is_source_bound_and_does_not_approve_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = {'resolved': {'sha256': 'a' * 64, 'layers': []}}
            store = SimpleNamespace(state_root=Path(tmp), get_project=lambda _: project)
            service = ProjectRoute(store)
            request = dict(choice='sleeves', expected_revision=0, expected_resolved_sha256='a' * 64)
            chosen = service.save('sample', request)
            self.assertEqual(chosen['choice'], 'sleeves')
            self.assertEqual(chosen['authority'], 'none')
            self.assertEqual(ProjectRoute(store).get('sample')['revision'], 1)
            with self.assertRaises(PipelineRunError):
                service.save('sample', request)
            project['resolved']['sha256'] = 'b' * 64
            stale = service.get('sample')
            self.assertTrue(stale['stale'])
            self.assertEqual(stale['choice'], 'undecided')
            self.assertEqual(stale['source_sha256'], 'b' * 64)
