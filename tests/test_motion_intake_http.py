"""Motion import routes enforce intent and expose actual compiled source playback."""
import http.client
import json
import time
import unittest
from unittest.mock import patch
from urllib.parse import quote

from test_mixamo_map import source
from test_server import WorkbenchHttpContractTests as Fixture


class MotionHttpTests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    request = Fixture.request

    def test_stage_review_http_keeps_intent_and_revision_guards(self):
        from autospine_workbench.resolved_project import canonical_sha256
        self.request('GET', '/api/motions')
        manager = self.server.automation_manager._motions
        job = 'motion-' + 'a'*32
        manager.folder(job, True)
        path = '/api/motions/' + job + '/stage-review'
        report = dict(artifact_sha256='asset', status='needs_changes', stages=[
            dict(stage='Runtime', status='sampled_pass')])
        body = dict(artifact_sha256='asset', evidence_sha256=canonical_sha256(report),
                    expected_revision=0, decision='accepted_with_exceptions', notes='测试限定范围')
        intent = {'Origin': f'http://{self.host}:{self.port}', 'X-Autospine-Intent': 'pipeline-preview'}
        with patch('autospine_workbench.automation.motion_stage_review.evidence',
                   return_value=(report, canonical_sha256(report))):
            self.assertEqual(self.request('POST', path, body)[0], 403)
            self.assertEqual(self.request('POST', path, body, dict(intent, Origin='https://other.test'))[0], 403)
            self.assertEqual(self.request('GET', path)[0], 200)
            self.assertEqual(self.request('POST', path, body, intent)[0], 202)
            status, _, data = self.request('GET', path)
            saved = json.loads(data)
            self.assertEqual(status, 200)
            self.assertEqual(saved['revision'], 1)
            self.assertTrue(saved['current_applies'])
            self.assertEqual(saved['readiness']['status'], 'needs_changes')
            self.assertEqual(self.request('POST', path, body, intent)[0], 400)
            self.assertEqual(self.request('DELETE', path)[0], 405)

    def test_generation_requires_intent_and_rejects_client_runtime_paths(self):
        from test_motion_generation import BODY
        self.assertEqual(self.request('GET', '/api/motions/generate')[0], 405)
        self.assertEqual(self.request('POST', '/api/motions/generate', BODY)[0], 403)
        intent = {'Origin': f'http://{self.host}:{self.port}', 'X-Autospine-Intent': 'pipeline-preview'}
        self.assertEqual(self.request('POST', '/api/motions/generate', dict(BODY, runtime='x'), intent)[0], 400)
        with patch('autospine_workbench.automation.motion_generation_jobs.availability', return_value='unavailable'):
            status, _, payload = self.request('POST', '/api/motions/generate', BODY, intent)
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(payload)['reason_code'], 'motion_generation_unavailable')

    def upload(self, raw, headers):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=10)
        connection.request('POST', '/api/motions', raw, headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_raw_intake_and_source_preview(self):
        raw = source()
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Autospine-File-Name': quote('行走.bvh'), 'X-Autospine-Motion-View': 'front'}
        self.assertEqual(self.upload(raw, headers)[0], 403)
        headers.update(Origin=f'http://{self.host}:{self.port}', **{'X-Autospine-Intent': 'pipeline-preview'})
        self.assertEqual(self.upload(raw, dict(headers, Origin='https://unrelated.test'))[0], 403)
        status, value = self.upload(raw, headers)
        self.assertEqual(status, 202, value)
        path = '/api/motions/' + value['job_id']
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            value = json.loads(self.request('GET', path)[2])
            if value['status'] not in ('pending', 'running'):
                break
            time.sleep(.05)
        self.assertEqual(value['status'], 'succeeded', value)
        self.assertEqual(value['result']['motion_status'], 'compiled')
        status, _, payload = self.request('GET', path + '/preview')
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(payload)['frames']), 2)
        status, _, diagnostic = self.request('GET', path + '/projection.json')
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(diagnostic)['records']), 8)
        self.assertEqual(json.loads(diagnostic)['authority'], 'none')
        status, _, html = self.request('GET', path + '/projection')
        self.assertEqual(status, 200)
        self.assertIn('源动作投影诊断', html.decode('utf-8'))
        self.assertEqual(self.request('POST', path + '/projection', {})[0], 405)
        status, _, overview = self.request('GET', '/api/motions')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(overview)['jobs'][0]['name'], '行走.bvh')
        self.assertEqual(self.request('GET', path + '/cancel')[0], 405)
        self.assertEqual(self.request('GET', path + '/unknown')[0], 404)
        intent = {'Origin': headers['Origin'], 'X-Autospine-Intent': 'pipeline-preview'}
        self.assertEqual(self.request('POST', path + '/retry', {'path': 'arbitrary'}, intent)[0], 400)
        self.assertEqual(self.request('POST', path + '/retry', {}, intent)[0], 202)

    def test_npz_requires_explicit_profile_and_returns_source_timeline(self):
        from tests.fixtures.kimodo_npz_archive import build_npz, motion_member_bytes
        raw = build_npz(motion_member_bytes())
        headers = {'Content-Type': 'application/octet-stream', 'X-Autospine-File-Name': 'motion.npz',
                   'X-Autospine-Motion-View': 'front', 'Origin': f'http://{self.host}:{self.port}',
                   'X-Autospine-Intent': 'pipeline-preview'}
        self.assertEqual(self.upload(raw, headers)[0], 400)
        headers.update({'X-Autospine-Npz-Profile': 'kimodo-soma77-v1', 'X-Autospine-Npz-Fps': '24'})
        status, value = self.upload(raw, headers)
        self.assertEqual(status, 202, value)
        path = '/api/motions/' + value['job_id']
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            value = json.loads(self.request('GET', path)[2])
            if value['status'] not in ('pending', 'running'):
                break
            time.sleep(.05)
        self.assertEqual(value['status'], 'succeeded', value)
        self.assertEqual(value['result']['fps'], 24)
        self.assertEqual(value['result']['motion']['source_kind'], 'kimodo_npz')
        self.assertEqual(self.request('GET', path + '/preview')[0], 200)


del Fixture
