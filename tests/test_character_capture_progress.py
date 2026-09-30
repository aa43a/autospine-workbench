"""Preparation failures must not be presented as official Runtime execution."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.motion_intake_process import progress, read_progress


class CaptureProgressTests(unittest.TestCase):
    def run_failure(self, failure_stage):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stages = []

            def record(stage):
                progress(root, stage)
                self.assertEqual(read_progress(root), stage)
                stages.append(stage)

            store = Mock(root=root)
            store.read.return_value = {'skeleton.json': b'{}'}
            with (patch('autospine_workbench.automation.character_capture.discover',
                        return_value=('node', 'deps', None, 'browser')),
                  patch('autospine_workbench.automation.character_capture.identity', return_value={}),
                  patch('autospine_workbench.targets.character43.static_region_review.build',
                        return_value=({}, {})),
                  patch('autospine_workbench.targets.character43.deformation_qa.inspect',
                        side_effect=ValueError('geometry_failed') if failure_stage == 'geometry' else None,
                        return_value={'passed': False}),
                  patch('autospine_workbench.targets.character43.numeric_reference.read',
                        return_value={'animations': {'test': [{}, {}]}}),
                  patch('autospine_workbench.targets.character43.runtime_storage_reference.build',
                        side_effect=ValueError('reference_failed')),
                  patch('autospine_workbench.automation.character_capture.subprocess.run') as launch):
                with self.assertRaisesRegex(ValueError, failure_stage + '_failed'):
                    capture(SimpleNamespace(workspace_root=root), store, 'digest', root,
                            progress=record, cancel_requested=lambda: False, storage_reference=True)
                launch.assert_not_called()
            return stages

    def test_geometry_failure_never_claims_capture_started(self):
        self.assertEqual(self.run_failure('geometry'), ['runtime_prepare', 'runtime_geometry'])

    def test_reference_failure_never_claims_capture_started(self):
        self.assertEqual(self.run_failure('reference'),
                         ['runtime_prepare', 'runtime_geometry', 'runtime_reference'])
