"""Verify opt-in lifetime ownership and exact disposable worker cleanup."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import Mock, patch

from autospine_workbench import studio_process_lifetime as subject


class StudioLifetimeTests(unittest.TestCase):
    def test_non_windows_explicitly_reports_no_containment_and_does_not_create_job(self):
        with patch.object(subject, '_owned_lifetime', None), patch.object(subject, '_failed_job', None), patch.object(subject, '_IS_WINDOWS', False), \
                patch.object(subject, '_create_windows_job_backend') as create:
            self.assertFalse(subject.keep_owned_process_tree().owns_windows_process_tree)
            create.assert_not_called()

    def test_containment_is_verified_and_retained_without_an_early_close_api(self):
        backend = Mock(); backend.create.return_value = 73
        backend.process_is_in_job.return_value = True
        with patch.object(subject, '_owned_lifetime', None), patch.object(subject, '_failed_job', None), patch.object(subject, '_IS_WINDOWS', True), \
                patch.object(subject, '_create_windows_job_backend', return_value=backend), \
                patch.object(subject, '_current_process_and_noninheritable_job', return_value=41):
            owner = subject.keep_owned_process_tree()
            self.assertIs(subject.keep_owned_process_tree(), owner)
            backend.create.assert_called_once()
            backend.configure_kill_on_close.assert_called_once_with(73)
            backend.assign.assert_called_once_with(73, 41)
            backend.process_is_in_job.assert_called_once_with(41, 73)
            backend.close.assert_not_called()
            self.assertTrue(owner.owns_windows_process_tree)
            self.assertFalse(hasattr(owner, 'close'))

    def test_assignment_failure_is_reported_and_unassigned_handle_is_closed(self):
        backend = Mock(); backend.create.return_value = 73
        backend.assign.side_effect = RuntimeError('denied')
        with patch.object(subject, '_owned_lifetime', None), patch.object(subject, '_failed_job', None), patch.object(subject, '_IS_WINDOWS', True), \
                patch.object(subject, '_create_windows_job_backend', return_value=backend), \
                patch.object(subject, '_current_process_and_noninheritable_job', return_value=41):
            with self.assertRaisesRegex(subject.StudioProcessLifetimeError, 'ownership failed'):
                subject.keep_owned_process_tree()
            backend.close.assert_called_once_with(73)
            self.assertIsNone(subject._owned_lifetime)

    def test_unverified_membership_fails_before_engine_start_without_premature_self_termination(self):
        backend = Mock(); backend.create.return_value = 73
        backend.process_is_in_job.return_value = False
        with patch.object(subject, '_owned_lifetime', None), patch.object(subject, '_failed_job', None), patch.object(subject, '_IS_WINDOWS', True), \
                patch.object(subject, '_create_windows_job_backend', return_value=backend), \
                patch.object(subject, '_current_process_and_noninheritable_job', return_value=41):
            with self.assertRaisesRegex(subject.StudioProcessLifetimeError, 'membership'):
                subject.keep_owned_process_tree()
            self.assertIsNone(subject._owned_lifetime)
            self.assertEqual(subject._failed_job, (73, backend))
            with self.assertRaisesRegex(subject.StudioProcessLifetimeError, 'membership remains unverified'):
                subject.keep_owned_process_tree()
            backend.create.assert_called_once()
            backend.close.assert_not_called()

    def test_inheritable_or_unverifiable_job_is_closed_without_assigning_current_process(self):
        backend = Mock(); backend.create.return_value = 73
        with patch.object(subject, '_owned_lifetime', None), patch.object(subject, '_failed_job', None), patch.object(subject, '_IS_WINDOWS', True), \
                patch.object(subject, '_create_windows_job_backend', return_value=backend), \
                patch.object(subject, '_current_process_and_noninheritable_job', side_effect=subject.StudioProcessLifetimeError('inheritable')):
            with self.assertRaisesRegex(subject.StudioProcessLifetimeError, 'inheritable'):
                subject.keep_owned_process_tree()
            backend.assign.assert_not_called()
            backend.close.assert_called_once_with(73)
            self.assertIsNone(subject._owned_lifetime)

    @unittest.skipUnless(os.name == 'nt', 'Actual Windows Job Object tree regression')
    def test_abrupt_owned_host_exit_ends_child_and_grandchild_despite_close_fds_false(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, PYTHONPATH=str(root/'src'))
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        api.TerminateProcess.restype = wintypes.BOOL
        api.CloseHandle.argtypes = [wintypes.HANDLE]; api.CloseHandle.restype = wintypes.BOOL
        with TemporaryDirectory() as name:
            folder = Path(name)
            process = subprocess.Popen([sys.executable, str(root/'tests/fixtures/studio_lifetime_host.py'), name],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            handles = []
            try:
                deadline = time.monotonic()+10
                while not (folder/'pids.json').exists() and time.monotonic() < deadline and process.poll() is None:
                    time.sleep(.02)
                self.assertTrue((folder/'pids.json').exists(), process.communicate(timeout=1) if process.poll() is not None else 'fixture startup timeout')
                for pid in json.loads((folder/'pids.json').read_text()):
                    handle = api.OpenProcess(0x00100001, False, pid)  # Exact owned handle: SYNCHRONIZE | TERMINATE
                    self.assertTrue(handle)
                    handles.append(handle)
                    self.assertEqual(api.WaitForSingleObject(handle, 0), 258)
                process.kill(); process.wait(timeout=5)
                for handle in handles:
                    self.assertEqual(api.WaitForSingleObject(handle, 5000), 0)
                size = (folder/'heartbeat').stat().st_size
                time.sleep(.15)
                self.assertEqual((folder/'heartbeat').stat().st_size, size)
            finally:
                if process.poll() is None:
                    process.kill(); process.wait(timeout=5)
                for handle in handles:
                    if api.WaitForSingleObject(handle, 0) == 258:
                        api.TerminateProcess(handle, 125); api.WaitForSingleObject(handle, 5000)
                    api.CloseHandle(handle)
                process.communicate(timeout=2)
