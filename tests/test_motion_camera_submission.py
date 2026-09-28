from copy import deepcopy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs
from autospine_workbench.automation.motion_intake_worker import compile_source
from autospine_workbench.automation.motion_target_jobs import submit
from autospine_workbench.automation.storage_io import read_document
from test_mixamo_map import source
from test_motion_camera_policy import request


class CameraSubmissionTests(unittest.TestCase):
    def test_verified_duration_full_track_and_retry_are_frozen(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);manager=MotionIntakeJobs(SimpleNamespace(state_root=root,workspace_root=root))
            self.addCleanup(manager.close)
            with patch.object(manager._pool,'submit'):
                raw=source();queued=manager.upload(BytesIO(raw),len(raw),'source.bvh','front')
                result=compile_source(raw,'front',manager.folder(queued['job_id']),root)
                manager._jobs[queued['job_id']].update(status='succeeded',step='complete',result=result)
                character=dict(status='needs_review',artifact_sha256='b'*64)
                manager.character_manager=lambda:SimpleNamespace(verified_snapshot=lambda *_:(dict(character),{}),get=lambda *_:character)
                body=dict(request(),project_id='alice',character_job_id='job-'+'c'*32)
                before=set(manager._jobs)
                with self.assertRaisesRegex(Exception,'key_invalid'):submit(manager,queued['job_id'],body)
                self.assertEqual(set(manager._jobs),before)
                body['projection']['keys'][-1]=dict(time=.5,yaw=5)
                body['projection']['sampling_profile']='camera-world-linear-adaptive-v1'
                accepted=submit(manager,queued['job_id'],body)
                frozen=read_document(manager.folder(accepted['job_id'])/'request.json')
                self.assertEqual(frozen['projection'],body['projection'])
                body['projection']['keys'][-1]['yaw']=360
                self.assertEqual(frozen['projection']['keys'][-1]['yaw'],5)
                manager._jobs[accepted['job_id']]['status']='failed'
                retried=manager.retry(accepted['job_id'])
                again=read_document(manager.folder(retried['job_id'])/'request.json')
                self.assertEqual(again['projection'],frozen['projection'])
                self.assertEqual(again['moving_ankle_profile'],frozen['moving_ankle_profile'])
                self.assertEqual(again['source_job_sha256'],frozen['source_job_sha256'])
