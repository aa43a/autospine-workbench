"""Preparation cannot accept model paths or execute through GET."""
from unittest.mock import Mock
import unittest

from tests import test_pipeline_web_http as fixture_http


class InputPreparationHttpTests(unittest.TestCase):
    close_server = fixture_http.PipelineWebHttpTests.close_server
    request = fixture_http.PipelineWebHttpTests.request
    document = fixture_http.PipelineWebHttpTests.document

    def setUp(self):
        fixture_http.PipelineWebHttpTests.setUp(self)
        self.base += '/animated/preparation'
        self.preparation = Mock()
        self.preparation.application.overview.return_value = {'status': 'ready', 'authority': 'none'}
        self.preparation.submit.return_value = {'status': 'pending', 'authority': 'none'}
        self.preparation.get.return_value = {'status': 'running', 'authority': 'none'}
        self.preparation.cancel.return_value = {'status': 'running', 'cancel_requested': True, 'authority': 'none'}
        self.manager._preparation = self.preparation

    def test_only_explicit_bounded_request_submits(self):
        self.assertEqual(self.document('GET')[0], 200)
        self.preparation.submit.assert_not_called()
        body = {'expected_resolved_sha256': 'a' * 64}
        self.assertEqual(self.request('POST', '', {**body, 'model': 'elsewhere.onnx'})[0], 400)
        self.preparation.submit.assert_not_called()
        self.assertEqual(self.document('POST', '', body)[0], 202)
        self.preparation.submit.assert_called_once_with('fixture-project', **body)
        self.assertEqual(self.request('POST', '/jobs/job-' + 'b' * 32 + '/cancel', {})[0], 202)
        self.assertEqual(self.request('GET', '/jobs/job-' + 'b' * 32 + '/cancel')[0], 405)
