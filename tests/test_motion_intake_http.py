"""Motion import routes enforce intent and expose actual compiled source playback."""
import http.client
import json
import time
import unittest
from urllib.parse import quote

from test_mixamo_map import source
from test_server import WorkbenchHttpContractTests as Fixture


class MotionHttpTests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    request = Fixture.request

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
        status, _, overview = self.request('GET', '/api/motions')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(overview)['jobs'][0]['name'], '行走.bvh')
        self.assertEqual(self.request('GET', path + '/cancel')[0], 405)
        self.assertEqual(self.request('GET', path + '/unknown')[0], 404)
        intent = {'Origin': headers['Origin'], 'X-Autospine-Intent': 'pipeline-preview'}
        self.assertEqual(self.request('POST', path + '/retry', {'path': 'arbitrary'}, intent)[0], 400)
        self.assertEqual(self.request('POST', path + '/retry', {}, intent)[0], 202)


del Fixture
