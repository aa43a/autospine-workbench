import base64
import json
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import test_motion_repair_execution as execution_fixtures
import test_view_pose_candidate as candidate_fixtures
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_view_execution import submit, retry
from autospine_workbench.automation.storage_io import canonical_bytes, read_document
from autospine_workbench.resolved_project import canonical_sha256


class ViewExecutionTests(unittest.TestCase):
    setUp = execution_fixtures.SubmissionTests.setUp

    def fixture(self):
        files, pose, png = candidate_fixtures.ViewPoseCandidateTests().fixture()
        handoff = dict(job_id='parent', draft_revision=1, artifact_sha256='a'*64,
                       slot='leg', animation='move', view_needs=['side'])
        stream = BytesIO()
        with ZipFile(stream, 'w') as archive:
            archive.writestr('request.json', canonical_bytes(handoff))
        store = AnimatedStore(Path(self.temp.name)/'store')
        self.manager.character_manager = lambda: SimpleNamespace(application=SimpleNamespace(store=store))
        for target, result in [('motion_repair_material.download', stream.getvalue()),
                               ('motion_target_jobs.context', ({'artifact_sha256': 'a'*64}, files)),
                               ('motion_target_jobs.assert_current', None)]:
            mock = patch('autospine_workbench.automation.'+target, return_value=result)
            handle = mock.start(); self.addCleanup(mock.stop)
            if target.endswith('download'): self.download = handle
            if target.endswith('context'): self.context = handle
        return dict(request=handoff, view_pose=pose, png_base64=base64.b64encode(png).decode('ascii'))

    def test_frozen_submission_and_retry_revalidate_live_handoff(self):
        body = self.fixture(); before = deepcopy(body)
        result = submit(self.manager, 'parent', body)
        saved = read_document(self.manager.folder(result['job_id'])/'request.json')
        self.assertEqual(body, before)
        self.assertEqual(saved['repair_execution']['draft']['action'], 'additional_view')
        self.assertEqual(read_document(self.manager.folder('parent')/'request.json'), self.request)
        self.download.side_effect = RuntimeError('motion_material_plan_superseded')
        with self.assertRaisesRegex(RuntimeError, 'superseded'):
            retry(self.manager, saved)
        self.manager._pool.submit.assert_called_once()

    def test_bad_identity_and_texture_do_not_queue(self):
        body = self.fixture()
        for target in ('texture_sha256', 'document_sha256', 'slot'):
            bad = deepcopy(body); bad['view_pose'][target] = 'wrong'
            with self.subTest(target=target), self.assertRaises(RuntimeError):
                submit(self.manager, 'parent', bad)
        self.manager._pool.submit.assert_not_called()

    def test_queue_full_before_material_publication(self):
        body = self.fixture()
        self.manager._jobs = {'a': {'status': 'pending'}, 'b': {'status': 'running'}}
        with self.assertRaisesRegex(RuntimeError, 'queue_full'):
            submit(self.manager, 'parent', body)
        self.manager._pool.submit.assert_not_called()

    def test_switched_attachment_rejected_before_queue_or_publication(self):
        body = self.fixture()
        result, files = self.context.return_value
        doc = json.loads(files['skeleton.json'])
        doc['animations']['move']['slots'] = {'leg': {'attachment': [{'time': .5, 'name': None}]}}
        files['skeleton.json'] = canonical_bytes(doc)
        body['view_pose']['document_sha256'] = canonical_sha256(doc)
        store = self.manager.character_manager().application.store
        with patch.object(store, 'publish') as publish:
            with self.assertRaisesRegex(ValueError, 'existing_attachment_timeline'):
                submit(self.manager, 'parent', body)
            publish.assert_not_called()
        self.manager._pool.submit.assert_not_called()
