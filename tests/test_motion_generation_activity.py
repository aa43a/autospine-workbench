import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_generation_activity import activity
from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs


class ActivityTests(unittest.TestCase):
    def test_missing_future_and_directory_do_not_claim_fresh_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertIsNone(activity(root,now=100)['log_age_seconds'])
            (root/'generation.log').mkdir()
            self.assertIsNone(activity(root,now=100)['log_bytes'])
            (root/'progress.json').write_text('{}')
            os.utime(root/'progress.json',(200,200))
            self.assertIsNone(activity(root,now=100)['stage_elapsed_seconds'])
            self.assertIsNone(activity(root,now=float('nan')))

    def test_elapsed_and_output_are_independent_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'progress.json').write_bytes(b'{"step":"generate_motion"}')
            (root/'generation.log').write_bytes(b'private prompt and local path')
            os.utime(root/'progress.json',(100,100));os.utime(root/'generation.log',(120,120))
            result=activity(root,now=145)
            self.assertEqual(result['stage_elapsed_seconds'],45)
            self.assertEqual(result['log_age_seconds'],25)
            self.assertEqual(result['log_bytes'],29)
            self.assertNotIn('private',str(result))
            self.assertEqual((root/'generation.log').read_bytes(),b'private prompt and local path')

    def test_manager_only_exposes_activity_for_running_generator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            jobs=MotionIntakeJobs(SimpleNamespace(state_root=root/'state',workspace_root=root))
            try:
                job='motion-'+'a'*32
                jobs.folder(job,True)
                for kind,status,expected in [('generate','running',True),('generate','pending',False),
                                             ('generate','failed',False),('import','running',False)]:
                    jobs._jobs[job]=dict(job_id=job,kind=kind,status=status,step='generate_motion')
                    with patch('autospine_workbench.automation.motion_generation_activity.activity',return_value={'observed':True}):
                        result=jobs.get(job)
                    self.assertEqual('activity' in result,expected)
                    self.assertNotIn('activity',jobs._jobs[job])
            finally:
                jobs._jobs.clear();jobs.close()


if __name__=='__main__':unittest.main()
