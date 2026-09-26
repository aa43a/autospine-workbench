"""Public related-review route enforces the same origin/intent protocol."""
import json
import unittest
from unittest.mock import patch
import test_motion_related_player_loading as fixtures
from test_server import WorkbenchHttpContractTests as HttpFixture
from autospine_workbench.automation import motion_related_review as review


class RelatedReviewHttpTests(unittest.TestCase):
    setUp = HttpFixture.setUp
    tearDown = HttpFixture.tearDown
    request = HttpFixture.request

    def test_real_registration_get_post_reload_and_isolated_download(self):
        data = fixtures.RelatedPlayerLoadingTests(); data.setUp(); self.addCleanup(data.doCleanups)
        path = '/api/motions/job/related-candidates/' + data.digest + '/stage-review'
        self.request('GET', '/api/motions')
        owner = self.server.automation_manager
        with patch.object(owner, '_motions', data.manager):
            state = json.loads(self.request('GET', path)[2])
            body = {k:state[k] for k in ('registration_sha256', 'artifact_sha256', 'evidence_sha256')}
            body.update(expected_revision=0, decision='accepted_with_exceptions', notes='HTTP fixture only')
            intent = {'Origin':f'http://{self.host}:{self.port}', 'X-Autospine-Intent':'pipeline-preview'}
            self.assertEqual(self.request('POST', path, body)[0], 403)
            self.assertEqual(self.request('POST', path, body, dict(intent, Origin='https://other.test'))[0], 403)
            self.assertEqual(self.request('POST', path, body, intent)[0], 202)
            status, _, raw = self.request('GET', path)
            self.assertEqual(status, 200); self.assertEqual(json.loads(raw)['revision'], 1)
            self.assertEqual(self.request('POST', path, body, intent)[0], 400)
            self.assertEqual(self.request('DELETE', path)[0], 405)
            status, headers, _ = self.request('OPTIONS', path)
            self.assertEqual(status, 204); self.assertIn('POST', headers['allow'])
            self.assertEqual(self.request('GET', path.replace(data.digest, 'f'*64))[0], 400)
            self.assertFalse((data.folder / 'stage-reviews').exists())
            self.assertEqual(review.inspect(data.manager, 'job', data.digest)['revision'], 1)


del HttpFixture
