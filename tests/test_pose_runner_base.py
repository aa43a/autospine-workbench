"""Interchangeable explicit pose producers; file import is not inference."""
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
from autospine_workbench.runners.pose.base import CanonicalPoseFileImporter, ModelRunner, PoseRunnerRequest
from tests.test_pose_observations import observation_fixture


class PoseRunnerBaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / 'composite.png'
        self.raw = encode_rgba_png(RgbaImage(100, 200, bytes([0, 0, 0, 0])*20000))
        self.image.write_bytes(self.raw)
        self.request = PoseRunnerRequest('sample-a', hashlib.sha256(self.raw).hexdigest(), (100, 200), self.image)
        document = observation_fixture()
        document['source']['image_sha256'] = self.request.image_sha256
        self.pose = self.root / 'pose.json'
        self.pose.write_text(json.dumps(document), encoding='utf-8')

    def test_import_preserves_file_and_validates_frozen_request(self):
        before = self.pose.read_bytes()
        runner = CanonicalPoseFileImporter(self.pose)
        self.assertIsInstance(runner, ModelRunner)
        self.assertEqual(runner.produce(self.request), self.pose)
        self.assertEqual(before, self.pose.read_bytes())
        self.assertIs(self.request.validate(), self.request)
        with self.assertRaises(FrozenInstanceError):
            self.request.project_id = 'changed'

    def test_request_rejects_image_identity_canvas_and_invalid_id(self):
        for request, reason in ((replace(self.request, image_sha256='0'*64), 'image_changed'),
                                (replace(self.request, canvas_size=(200, 100)), 'canvas_mismatch'),
                                (replace(self.request, project_id='../outside'), 'request_invalid'),
                                (replace(self.request, canvas_size=(True, 200)), 'request_invalid')):
            with self.assertRaisesRegex(ValueError, reason):
                request.validate()

    def test_pose_must_match_source_and_project(self):
        document = json.loads(self.pose.read_text('utf-8'))
        document['source']['image_sha256'] = '0'*64
        self.pose.write_text(json.dumps(document), encoding='utf-8')
        with self.assertRaises(ValueError):
            CanonicalPoseFileImporter(self.pose).produce(self.request)

    def test_alternate_producer_satisfies_protocol_without_model_dependencies(self):
        output = self.pose
        class ExistingTestOutput:
            runner_id = 'test-only-output'
            def produce(self, request):
                request.validate()
                return output
        runner = ExistingTestOutput()
        self.assertIsInstance(runner, ModelRunner)
        self.assertEqual(runner.produce(self.request), self.pose)

    def test_huge_coordinate_and_duplicate_key_fail_with_stable_reason(self):
        before = self.pose.read_text('utf-8')
        document = json.loads(before)
        document['joints']['elbow.left']['xy'][0] = 10**1000
        self.pose.write_text(json.dumps(document), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '^pose_runner_observations_invalid$'):
            CanonicalPoseFileImporter(self.pose).produce(self.request)
        self.pose.write_text(before.replace('"format_version": 1', '"format_version": 1, "format_version": 1'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '^pose_runner_observations_invalid$'):
            CanonicalPoseFileImporter(self.pose).produce(self.request)


if __name__ == '__main__':
    unittest.main()
