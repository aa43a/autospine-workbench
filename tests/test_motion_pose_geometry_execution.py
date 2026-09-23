from copy import deepcopy
import unittest
from unittest.mock import patch

from test_motion_repair_execution import SubmissionTests
from test_pose_geometry_candidate import bundle
from autospine_workbench.automation.motion_pose_geometry_execution import submit
from autospine_workbench.automation.motion_repair_execution import retry
from autospine_workbench.automation.storage_io import read_document


class PoseSubmissionTests(unittest.TestCase):
    setUp = SubmissionTests.setUp
    def pose_submit(self, body):
        files, _ = bundle()
        with patch('autospine_workbench.automation.motion_target_jobs.context',
                   return_value=({'artifact_sha256': 'a'*64}, files)), \
             patch('autospine_workbench.automation.motion_target_jobs.assert_current'):
            return submit(self.manager, 'parent', body)

    def test_pose_frozen_and_parent_untouched(self):
        _, plan = bundle()
        body = dict(artifact_sha256='a'*64, pose_geometry=plan['pose_geometry'])
        expected = deepcopy(body)
        value = self.pose_submit(body)
        body['pose_geometry']['poses'].clear()
        saved = read_document(self.manager.folder(value['job_id'])/'request.json')
        self.assertEqual(saved['repair_execution']['draft']['pose_geometry'], expected['pose_geometry'])
        self.assertEqual(read_document(self.manager.folder('parent')/'request.json'), self.request)
        with patch('autospine_workbench.automation.motion_pose_geometry_execution.submit', return_value={}) as call:
            retry(self.manager, saved)
        call.assert_called_once_with(self.manager, 'parent', expected)

    def test_stale_versions_do_not_queue(self):
        _, plan = bundle()
        for field in ('artifact_sha256', 'document_sha256', 'mesh_sha256'):
            with self.subTest(field=field):
                body = dict(artifact_sha256='a'*64, pose_geometry=deepcopy(plan['pose_geometry']))
                (body if field == 'artifact_sha256' else body['pose_geometry'])[field] = '0'*64
                with self.assertRaises(RuntimeError): self.pose_submit(body)
        self.manager._pool.submit.assert_not_called()

    def test_queue_full_does_not_publish(self):
        _, plan = bundle()
        self.manager._jobs = {'a': {'status': 'running'}, 'b': {'status': 'pending'}}
        with self.assertRaisesRegex(RuntimeError, 'queue_full'):
            self.pose_submit(dict(artifact_sha256='a'*64, pose_geometry=plan['pose_geometry']))
        self.manager._pool.submit.assert_not_called()
