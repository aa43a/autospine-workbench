"""Real subprocess lifecycle tests; these are not model inference evidence."""

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from autospine_workbench.automation.input_preparation_runner import (
    PosePreparationError, PoseRunnerConfig, _run_child, _runner_arguments, _probe, run_project_pose,
)


class InputPreparationRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def child(self, code, timeout=5, cancel=lambda: False):
        return _run_child([sys.executable, '-I', '-u', '-c', code], self.root,
                          timeout, cancel, dict(os.environ))

    def test_configuration_is_explicit_and_public_status_contains_no_paths(self):
        status = PoseRunnerConfig.from_environment({}).public_status()
        self.assertEqual(status['reason_code'], 'pose_runner_not_configured')
        config = PoseRunnerConfig.from_environment({'AUTOSPINE_POSE_PYTHON': str(self.root/'missing.exe'),
                                                    'AUTOSPINE_POSE_MODEL': str(self.root/'missing.onnx')})
        status = config.public_status()
        self.assertEqual(status['status'], 'missing')
        self.assertNotIn(str(self.root), json.dumps(status))
        with patch('autospine_workbench.automation.input_preparation_runner.subprocess.Popen') as popen:
            config.public_status()
        popen.assert_not_called()

    def test_embedded_runner_uses_fixed_engine_bootstrap_and_keeps_business_arguments_literal(self):
        args = ['--image', 'quoted "$()" image.png', '--project', 'project']
        command = _runner_arguments(self.root/'python.exe', args)
        self.assertEqual(command[1:4], ['-B', '-I', '-c'])
        self.assertEqual(command[5], str(Path(__file__).resolve().parents[1]/'src'))
        self.assertEqual(command[6:], ['run', *args])
        self.assertNotIn('quoted "$()" image.png', command[4])
        self.assertEqual(_runner_arguments(sys.executable, probe=True)[6], 'probe')

    def test_probe_requires_real_runner_import_receipt_and_is_not_cached_with_dependency_changes(self):
        from autospine_workbench.automation import input_preparation_runner as runner
        receipt = {'runner_entrypoint_supported': True, 'python_version': '3.14.3'}
        with patch.object(runner, '_verify_model'), patch.object(runner.subprocess, 'run') as child:
            child.return_value = SimpleNamespace(returncode=0, stdout=json.dumps(receipt).encode())
            self.assertEqual(_probe('python.exe', 'model.onnx', ('fingerprint',)), receipt)
            self.assertEqual(child.call_args.args[0], _runner_arguments('python.exe', probe=True))
            self.assertEqual(child.call_args.kwargs['timeout'], 10)
            child.return_value = SimpleNamespace(returncode=2, stdout=b'')
            with self.assertRaisesRegex(PosePreparationError, '^pose_runner_dependencies_missing$'):
                _probe('python.exe', 'model.onnx', ('fingerprint',))
            self.assertEqual(child.call_count, 2)

    def test_probe_rejects_unchecked_or_malformed_receipts_and_exposes_no_local_path(self):
        from autospine_workbench.automation import input_preparation_runner as runner
        for raw in (b'{}', b'{"runner_entrypoint_supported":false,"python_version":"3.14.3"}',
                    b'x'*8193, b'{"runner_entrypoint_supported":true,"python_version":"3.14.3","path":"secret"}'):
            with self.subTest(raw=raw[:40]), patch.object(runner, '_verify_model'), \
                 patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=raw)):
                with self.assertRaisesRegex(PosePreparationError, '^pose_runner_entrypoint_invalid$'):
                    _probe('python.exe', 'model.onnx', ('fingerprint',))

    def test_success_and_failure_use_exit_status_without_exposing_stderr(self):
        raw = self.child('print("ok")')
        self.assertEqual(raw.strip(), b'ok')
        other = self.root/'failure'
        other.mkdir()
        with self.assertRaisesRegex(PosePreparationError, '^pose_runner_failed$'):
            _run_child([sys.executable, '-c', 'import sys; sys.stderr.write("secret-local-path"); sys.exit(2)'],
                       other, 5, lambda: False, dict(os.environ))

    def test_timeout_and_cancellation_reap_owned_process(self):
        from autospine_workbench.automation import input_preparation_runner as runner
        actual = runner.subprocess.Popen
        children = []
        def tracked(*args, **kwargs):
            child = actual(*args, **kwargs)
            children.append(child)
            return child
        start = time.monotonic()
        with patch.object(runner.subprocess, 'Popen', side_effect=tracked):
            with self.assertRaisesRegex(PosePreparationError, '^pose_runner_timeout$'):
                self.child('import time; time.sleep(10)', timeout=.15)
        self.assertLess(time.monotonic()-start, 3)
        self.assertIsNotNone(children[-1].poll())
        folder = self.root/'cancel'
        folder.mkdir()
        start = time.monotonic()
        with patch.object(runner.subprocess, 'Popen', side_effect=tracked):
            with self.assertRaisesRegex(PosePreparationError, '^pipeline_canceled$'):
                _run_child([sys.executable, '-c', 'import time; time.sleep(10)'], folder, 5,
                           lambda: time.monotonic()-start>.15, dict(os.environ))
        self.assertIsNotNone(children[-1].poll())

    def test_output_budget_terminates_excessive_logs(self):
        with self.assertRaisesRegex(PosePreparationError, '^pose_runner_output_limit$'):
            self.child('import sys,time; sys.stdout.write("x"*1100000); sys.stdout.flush(); time.sleep(5)')

    def test_source_identity_and_canvas_rejected_before_process_launch(self):
        config = PoseRunnerConfig()
        with patch('autospine_workbench.automation.input_preparation_runner._run_child') as child:
            with self.assertRaisesRegex(PosePreparationError, '^pose_runner_source_mismatch$'):
                run_project_pose(config, 'project', b'not-png', 'a'*64, self.root)
            png_header = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', 9000, 10)
            with self.assertRaisesRegex(PosePreparationError, '^pose_runner_canvas_unsupported$'):
                run_project_pose(config, 'project', png_header, hashlib.sha256(png_header).hexdigest(), self.root)
        child.assert_not_called()

    def test_canonical_result_identity_is_checked_even_after_success_receipt(self):
        from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
        from autospine_workbench.resolved_project import canonical_sha256
        from tests.test_pose_observations import observation_fixture
        raw = encode_rgba_png(RgbaImage(100, 200, bytes([255, 255, 255, 255])*20000))
        digest = hashlib.sha256(raw).hexdigest()
        config = PoseRunnerConfig(Path(sys.executable), self.root/'unused.onnx')
        def output(arguments, folder, *_):
            self.assertEqual(arguments[1:4], ['-B', '-I', '-c'])
            self.assertEqual(arguments[6], 'run')
            self.assertEqual(arguments[7], '--image')
            document = observation_fixture()
            # Structurally valid result and matching receipt, but for another image.
            document['source']['image_sha256'] = 'f'*64
            (folder/'pose.json').write_text(json.dumps(document), encoding='utf-8')
            return json.dumps({'status':'succeeded','authority':'none',
                               'pose_sha256':canonical_sha256(document)}).encode()
        with patch.object(PoseRunnerConfig, 'public_status', return_value={'status':'ready'}), \
             patch('autospine_workbench.automation.input_preparation_runner._run_child', side_effect=output):
            with self.assertRaisesRegex(PosePreparationError, '^pose_runner_result_invalid$'):
                run_project_pose(config, 'sample-a', raw, digest, self.root)

    def test_import_does_not_load_onnx_or_opencv_in_service_process(self):
        code = ('import sys; import autospine_workbench.automation.input_preparation_runner; '
                'assert "onnxruntime" not in sys.modules; assert "cv2" not in sys.modules')
        # Explicit PYTHONPATH supplies repository code; optional inference stays isolated.
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
        _run_child([sys.executable, '-c', code], self.root, 5, lambda: False, env)


if __name__ == '__main__':
    unittest.main()
