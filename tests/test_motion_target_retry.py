"""Retry never upgrades omitted legacy policies to current defaults."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs
from autospine_workbench.automation.storage_io import canonical_bytes, read_document
from autospine_workbench.automation.pipeline_run import PipelineRunError


class TargetRetryTests(TestCase):
    def test_preserves_exact_policies_and_missing_legacy_fields(self):
        for policies in ({}, {'pose_profile':'source-pose-post-contact-margin-v1'},
                {'pose_profile':'source-pose-post-contact-timeline-v2'},
                dict(contact_correction=False, depth_review_profile='external-regional-depth-order-v1',
                inferred_contact_profile='legacy', runtime_reference_profile='original',
                clip=dict(start_frame=2,end_frame=7), projection=dict(yaw_degrees=30),
                projection_selection=dict(comparison_sha256='a'*64, original='receipt'),
                local_depth_profile='original-local', torso_projection_profile='original-torso')):
            with self.subTest(policies=policies), TemporaryDirectory() as temp:
                manager=MotionIntakeJobs(SimpleNamespace(state_root=Path(temp),workspace_root=Path(temp)))
                try:
                    job='motion-'+'1'*32
                    request=dict(kind='adapt',job_id=job,project_id='alice',character_job_id='character',name='test',**policies)
                    folder=manager.folder(job,True);raw=canonical_bytes(request)
                    (folder/'request.json').write_bytes(raw)
                    with patch('autospine_workbench.automation.motion_target_jobs.assert_current') as verify, patch.object(manager._pool,'submit'):
                        queued=manager.retry(job)
                    verify.assert_called_once_with(manager,request)
                    copied=read_document(manager.folder(queued['job_id'])/'request.json')
                    self.assertEqual(copied.pop('retry_of'),dict(job_id=job,request_sha256=sha256(raw).hexdigest()))
                    self.assertNotEqual(copied.pop('job_id'),job)
                    expected=deepcopy(request);expected.pop('job_id');self.assertEqual(copied,expected)
                    self.assertEqual((folder/'request.json').read_bytes(),raw)
                    manager._jobs.clear()
                    with patch('autospine_workbench.automation.motion_target_jobs.assert_current',side_effect=PipelineRunError('motion_target_character_changed')):
                        with self.assertRaisesRegex(PipelineRunError,'motion_target_character_changed'):manager.retry(job)
                    self.assertEqual(len(list(manager.root.iterdir())),2)
                finally:manager.close()
