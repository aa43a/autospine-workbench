import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from threading import RLock
from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs
from autospine_workbench.automation.motion_intake_process import progress, read_progress, read_progress_detail
from autospine_workbench.automation.motion_job_budget import limit, timeout_reason


class MotionProgressTests(unittest.TestCase):
    def test_real_solver_counts_and_timestamp(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            with patch('autospine_workbench.automation.motion_intake_process.time.time', return_value=1234):
                progress(folder, 'retarget', dict(stage='solve_attachment', slot='layer-002',
                    frame_index=16, sample_count=200, arbitrary='private path'))
            value = read_progress_detail(folder)
            self.assertEqual((value['completed'], value['total'], value['updated_at']), (16, 200, 1234))
            self.assertNotIn('arbitrary', value)
            self.assertEqual(read_progress(folder), 'retarget')
            progress(folder, 'runtime')
            self.assertNotIn('completed', read_progress_detail(folder))

    def test_legacy_and_missing_progress(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            self.assertEqual(read_progress_detail(folder), {})
            (folder/'progress.json').write_text('{"step":"retarget"}')
            self.assertEqual(read_progress(folder), 'retarget')

    def test_active_long_build_is_bounded_separately_from_stall(self):
        self.assertIsNone(timeout_reason('adapt', 901, 10))
        self.assertEqual(timeout_reason('adapt', 901, 901), 'motion_target_stalled')
        self.assertEqual(timeout_reason('adapt', 3601, 0), 'motion_target_timeout')
        self.assertEqual(timeout_reason(None, 241, 0), 'motion_decode_timeout')
        self.assertEqual(limit('generate'), 3600)

    def test_running_api_exposes_counts_and_elapsed_without_mutating_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            progress(folder, 'retarget', dict(frame_index=32, sample_count=100))
            manager = MotionIntakeJobs.__new__(MotionIntakeJobs)
            manager._lock = RLock()
            manager.folder = lambda job: folder
            manager._jobs = {'job': dict(status='running', step='queued', started_at=100,
                                        timeout_seconds=3600, kind='adapt')}
            with patch('autospine_workbench.automation.motion_intake_jobs.time.time', return_value=112):
                value = manager.get('job')
            self.assertEqual(value['elapsed_seconds'], 12)
            self.assertEqual(value['progress']['completed'], 32)
            self.assertEqual(value['step'], 'retarget')
            self.assertNotIn('elapsed_seconds', manager._jobs['job'])


if __name__ == '__main__':
    unittest.main()
