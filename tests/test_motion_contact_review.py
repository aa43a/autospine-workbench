from hashlib import sha256
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_contact_review import inspect
from autospine_workbench.automation.motion_intake_routes import _methods
from autospine_workbench.automation.pipeline_run import PipelineRunError


class ContactReviewTests(unittest.TestCase):
    def test_rejects_target_job(self):
        manager = SimpleNamespace(get=lambda _: dict(kind='adapt', status='succeeded'))
        with self.assertRaisesRegex(PipelineRunError, 'source_unavailable'):
            inspect(manager, 'motion-test')

    def test_route_is_read_only(self):
        self.assertEqual(_methods(['motion-test', 'contacts']), 'GET, HEAD, OPTIONS')

    def test_source_labels_precede_inference_and_source_bytes_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'source.npz').write_bytes(b'original source')
            job = dict(status='succeeded', format='npz', source_sha256=sha256(b'original source').hexdigest(),
                result=dict(motion_status='compiled', motion=dict(clip_sha256='a'*64, bundle_sha256='b'*64)))
            manager = SimpleNamespace(get=lambda _: job, folder=lambda _: root, state_root=root)
            marker = dict(kind='contact', limb='leg.left', start_tick=0, end_tick=30)
            bundle = SimpleNamespace(motion=dict(markers=[marker], ticks_per_second=30, duration_ticks=60))
            with patch('autospine_workbench.automation.motion_contact_review.VerifiedMotionBundleReader') as reader:
                reader.return_value.load.return_value = bundle
                report = inspect(manager, 'motion-test')
                self.assertEqual(report['status'], 'source_markers')
                self.assertEqual(report['duration_seconds'], 2)
                self.assertFalse(report['selected'])
                self.assertEqual(report['markers'], [marker])
                (root/'source.npz').write_bytes(b'changed')
                with self.assertRaisesRegex(PipelineRunError, 'motion_source_changed'):
                    inspect(manager, 'motion-test')
                self.assertEqual(reader.return_value.load.call_count, 1)


if __name__ == '__main__':
    unittest.main()
