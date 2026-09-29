import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from autospine_workbench.automation.build_timing import BuildTiming
from autospine_workbench.automation.motion_intake_process import read_progress_detail
from autospine_workbench.automation.motion_joint_worker import execute


class BuildTimingTests(unittest.TestCase):
    def test_repeated_progress_accumulates_stage_and_persists_final(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); clock = [0.]
            timer = BuildTiming(root, clock=lambda: clock[0])
            timer('verify_source')
            clock[0] = 2.; timer('joint_validate')
            clock[0] = 4.; timer('joint_validate')
            clock[0] = 7.; timer('runtime')
            clock[0] = 10.; value = timer.finish('completed')
            self.assertEqual(value['elapsed_seconds'], 10)
            self.assertEqual(value['stages'], [dict(step='verify_source', seconds=2, calls=1),
                dict(step='joint_validate', seconds=5, calls=2), dict(step='runtime', seconds=3, calls=1)])
            self.assertEqual(json.loads((root/'build-timing.json').read_bytes()), value)
            self.assertEqual(read_progress_detail(root)['build_timing'], value)
            self.assertIsNone(value['active_step'])

    def test_failed_worker_keeps_measured_stage_without_a_success_receipt(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, 'frozen_config_changed'):
                execute(root, root, root, dict(joint_execution=dict(profile='wrong')))
            value = json.loads((root/'build-timing.json').read_bytes())
            self.assertEqual(value['status'], 'failed')
            self.assertEqual(value['stages'][0]['step'], 'verify_source')
            self.assertFalse((root/'worker-result.json').exists())


if __name__ == '__main__': unittest.main()
