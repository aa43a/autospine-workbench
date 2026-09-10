"""Exercise catalog HTTP authorization and reversible project visibility."""
import json
import unittest
from test_server import WorkbenchHttpContractTests as Fixture


class AssetHttpTests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    request = Fixture.request

    def test_lifecycle_and_origin(self):
        status, _, raw = self.request('GET', '/api/asset-library')
        self.assertEqual(status, 200)
        project = json.loads(raw)['projects'][0]['id']
        path = '/api/asset-library/' + project
        body = dict(action='archive', expected_revision=0)
        self.assertEqual(self.request('POST', path, body)[0], 403)
        headers = {'Origin': f'http://{self.host}:{self.port}', 'X-Autospine-Intent': 'pipeline-preview'}
        self.assertEqual(self.request('POST', path, body, headers)[0], 200)
        self.assertEqual(json.loads(self.request('GET', '/api/projects')[2])['count'], 0)
        self.assertEqual(self.request('POST', path, body, headers)[0], 409)
        self.assertEqual(self.request('POST', path, dict(action='restore', expected_revision=1), headers)[0], 200)
        self.assertEqual(json.loads(self.request('GET', '/api/projects')[2])['count'], 1)
        self.assertEqual(self.request('DELETE', path)[0], 405)


del Fixture  # Imported fixture helpers must not duplicate its test suite.
