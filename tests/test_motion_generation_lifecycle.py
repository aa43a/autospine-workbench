"""Real Windows process lifecycle; synthetic workload, no model-quality claim."""
import ctypes
from ctypes import wintypes
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_generation_jobs import submit
from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs
from autospine_workbench.automation.motion_intake_process import terminate_tree
from autospine_workbench.automation.storage_io import read_document
from autospine_workbench.automation.motion_process_owner import launch as launch_owned
from autospine_workbench.automation.pipeline_run import PipelineRunError


BODY = dict(prompt='A person waves.', duration_seconds=4, seed=42,
            diffusion_steps=100, view='front')


@unittest.skipUnless(os.name == 'nt', 'Windows process-tree integration')
class MotionGenerationLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.projects = SimpleNamespace(state_root=self.root / 'state', workspace_root=self.root)
        self.jobs = MotionIntakeJobs(self.projects)
        self.addCleanup(self.jobs.close)
        self.real_popen = subprocess.Popen
        self.processes = []
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.WaitForSingleObject.restype = wintypes.DWORD
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL

    def await_value(self, callback):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            value = callback()
            if value:
                return value
            time.sleep(.05)
        self.fail('Real worker did not reach the required state within 15 seconds')

    def launch(self, command, **kwargs):
        # Only replace the model worker command. taskkill remains the actual OS command.
        if 'autospine_workbench.automation.motion_generation_worker' not in command:
            return self.real_popen(command, **kwargs)
        folder = Path(command[3])
        code = (
            'import subprocess,sys,time; from pathlib import Path; '
            'from autospine_workbench.automation.motion_intake_process import progress; '
            'folder=Path(sys.argv[1]); '
            'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
            '(folder/"child.pid").write_text(str(child.pid)); '
            'progress(folder,"generate_motion"); time.sleep(60)'
        )
        process = self.real_popen([sys.executable, '-c', code, str(folder)], **kwargs)
        self.processes.append(process)
        self.addCleanup(terminate_tree, process)
        return process

    def exercise_stop(self, close):
        with patch('autospine_workbench.automation.motion_generation_jobs.availability',
                   return_value='configured'), patch(
                       'autospine_workbench.automation.motion_intake_jobs.subprocess.Popen',
                       side_effect=self.launch):
            job = submit(self.jobs, BODY)['job_id']
            folder = self.jobs.folder(job)
            before = (folder / 'request.json').read_bytes()
            self.await_value(lambda: self.jobs.get(job).get('step') == 'generate_motion')
            pid = int((folder / 'child.pid').read_text())
            handle = self.api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            self.assertTrue(handle, ctypes.get_last_error())
            self.addCleanup(self.api.CloseHandle, handle)
            self.assertEqual(self.api.WaitForSingleObject(handle, 0), 258)  # still live
            if close:
                self.jobs.close()
            else:
                self.jobs.cancel(job)
            result = self.await_value(lambda: (
                self.jobs.get(job) if self.jobs.get(job)['status'] not in ('pending', 'running') else None))
            self.assertEqual(result['status'], 'canceled')
            self.assertEqual(result['reason_code'], 'motion_canceled')
            self.assertEqual(self.api.WaitForSingleObject(handle, 5000), 0)
            self.assertIsNotNone(self.processes[0].poll())
            self.assertFalse((folder / 'worker-result.json').exists())
            self.assertEqual((folder / 'request.json').read_bytes(), before)

        reopened = MotionIntakeJobs(self.projects)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.get(job), result)
        with patch('autospine_workbench.automation.motion_generation_jobs.availability',
                   return_value='configured'), patch.object(reopened._pool, 'submit'):
            retry = reopened.retry(job)['job_id']
        self.assertNotEqual(retry, job)
        self.assertEqual(read_document(reopened.folder(retry) / 'request.json')['generation'], BODY)
        self.assertEqual((folder / 'request.json').read_bytes(), before)
        self.assertEqual(reopened.get(job), result)

    def test_cancel_stops_real_worker_and_descendant_and_preserves_retry(self):
        self.exercise_stop(close=False)

    def test_graceful_close_stops_real_worker_and_descendant_and_preserves_retry(self):
        self.exercise_stop(close=True)

    def test_forced_host_exit_kills_descendants_and_reopens_as_interrupted(self):
        script = Path(__file__).parent / 'fixtures/motion_crash_host.py'
        host = self.real_popen([sys.executable, str(script), str(self.root)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(terminate_tree, host)
        def ready():
            try:
                return json.loads((self.root / 'pids.json').read_text())
            except (OSError, ValueError):
                return None
        pids = self.await_value(ready)
        handles = []
        for pid in pids:
            handle = self.api.OpenProcess(0x00100000, False, pid)
            self.assertTrue(handle, ctypes.get_last_error())
            self.addCleanup(self.api.CloseHandle, handle)
            self.assertEqual(self.api.WaitForSingleObject(handle, 0), 258)
            handles.append(handle)
        job = json.loads((self.root / 'job.json').read_text())['job_id']
        folder = self.jobs.folder(job)
        before = (folder / 'request.json').read_bytes()
        # Kill ONLY the manager host, without taskkill /T or running its finally.
        host.kill()
        host.wait(timeout=5)
        for handle in handles:
            self.assertEqual(self.api.WaitForSingleObject(handle, 5000), 0)
        reopened = MotionIntakeJobs(self.projects)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.get(job)['status'], 'interrupted')
        self.assertFalse((folder / 'result.json').exists())
        with patch('autospine_workbench.automation.motion_generation_jobs.availability',
                   return_value='configured'), patch.object(reopened._pool, 'submit'):
            retry = reopened.retry(job)['job_id']
        self.assertNotEqual(retry, job)
        self.assertEqual(read_document(reopened.folder(retry) / 'request.json')['generation'], BODY)
        self.assertEqual((folder / 'request.json').read_bytes(), before)

    def test_ownership_failure_never_runs_worker(self):
        for boundary in ('attach_kill_on_close_process_job', 'resume_suspended_primary_thread'):
            with self.subTest(boundary=boundary):
                marker = self.root / (boundary + '.txt')
                command = [sys.executable, '-c',
                           'from pathlib import Path; import sys; Path(sys.argv[1]).write_text("ran")',
                           str(marker)]
                created = []
                def capture(*args, **kwargs):
                    process = self.real_popen(*args, **kwargs)
                    created.append(process)
                    return process
                with (self.root / 'ownership.log').open('wb') as log, patch(
                        'autospine_workbench.automation.motion_process_owner.subprocess.Popen',
                        side_effect=capture), patch(
                            'autospine_workbench.automation.motion_process_owner.' + boundary,
                            side_effect=RuntimeError('injected ownership failure')):
                    with self.assertRaisesRegex(PipelineRunError, 'motion_process_ownership_failed'):
                        launch_owned(command, log)
                self.assertFalse(marker.exists())
                self.assertIsNotNone(created[0].poll())
