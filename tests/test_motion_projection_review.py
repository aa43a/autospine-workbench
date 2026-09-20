from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from autospine_workbench.automation.motion_projection_review import inspect, render
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.targets.character43.projection_diagnostics import summarize


class MotionProjectionReviewTests(unittest.TestCase):
    def test_changed_original_bytes_are_rejected_before_bundle_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'source.bvh').write_bytes(b'changed original motion')
            job = dict(status='succeeded', result={'motion_status': 'compiled'}, format='bvh', source_sha256='0'*64)
            manager = SimpleNamespace(get=lambda _: job, folder=lambda _: root)
            with self.assertRaisesRegex(PipelineRunError, 'motion_source_changed'):
                inspect(manager, 'motion-test')

    def test_target_jobs_are_not_treated_as_source_observations(self):
        manager = SimpleNamespace(get=lambda _: dict(kind='adapt', status='succeeded'))
        with self.assertRaisesRegex(PipelineRunError, 'projection_source_unavailable'):
            inspect(manager, 'motion-test')

    def test_source_name_is_escaped(self):
        report = summarize({'arm': [1, .1]}, [0, 1])
        report['source_name'] = '<script>test()</script>'
        page = render(report).decode()
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)


if __name__ == '__main__':
    unittest.main()
