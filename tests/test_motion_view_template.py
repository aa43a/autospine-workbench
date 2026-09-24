from io import BytesIO
import json
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import test_view_pose_candidate as fixtures
from autospine_workbench.automation.motion_view_template import download
from autospine_workbench.automation.motion_intake_routes import _methods


class ViewTemplateTests(unittest.TestCase):
    def invoke(self, views, mutate=None):
        files, _, _ = fixtures.ViewPoseCandidateTests().fixture()
        if mutate:
            doc = json.loads(files['skeleton.json'])
            mutate(doc)
            files['skeleton.json'] = json.dumps(doc).encode()
        request = dict(view_needs=views, artifact_sha256='a'*64, slot='leg', animation='move', event=dict(time=1))
        stream = BytesIO()
        with ZipFile(stream, 'w') as archive:
            archive.writestr('request.json', json.dumps(request))
        with patch('autospine_workbench.automation.motion_repair_material.download', return_value=stream.getvalue()), \
             patch('autospine_workbench.automation.motion_target_jobs.context', return_value=({'artifact_sha256':'a'*64}, files)):
            return json.loads(download(SimpleNamespace(_lock=RLock()), 'parent', '1'))

    def test_template_is_not_an_authored_pose(self):
        result = self.invoke(['side'])
        self.assertEqual(result['view_pose']['poses'], [])
        self.assertIsNone(result['view_pose']['texture_sha256'])
        self.assertEqual(len(result['control_template']['source_uv']), 4)
        self.assertEqual(result['view_pose']['interval'], [0, 2])
        self.assertEqual(_methods(['parent', 'view-pose-template', '1']), 'GET, HEAD, OPTIONS')
        self.assertEqual(_methods(['parent', 'view-pose-execute']), 'POST, OPTIONS')

    def test_plain_texture_task_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'requires_view_task'):
            self.invoke([])

    def test_switched_source_cannot_emit_wrong_base_coordinates(self):
        def switch(doc):
            doc['animations']['move']['slots'] = {'leg': {'attachment': [
                {'time': 0, 'name': 'leg'}, {'time': .5, 'name': None}]}}
        with self.assertRaisesRegex(ValueError, 'existing_attachment_timeline'):
            self.invoke(['side'], switch)

    def test_setup_attachment_identity_must_match(self):
        def switch(doc):
            next(s for s in doc['slots'] if s['name'] == 'leg')['attachment'] = 'other'
        with self.assertRaisesRegex(ValueError, 'setup_attachment_mismatch'):
            self.invoke(['side'], switch)
