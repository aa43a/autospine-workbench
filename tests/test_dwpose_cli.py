"""Source discovery is pinned to manifest identity, not the PSD display name."""
from argparse import Namespace
from pathlib import Path
import unittest

from tests import test_benchmark_r2a_cli as fixtures
from autospine_workbench.runners.pose.__main__ import resolve_source
from autospine_workbench.runners.pose.dwpose import DWPoseOnnxRunner


class DwposeCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.R2aCliTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.args = Namespace(character=f.candidate['character_id'], image=None, project=None,
                              manifest=f.root/'manifest.json', evidence=f.root/'evidence.json', workspace=f.root)

    def test_benchmark_resolves_exact_candidate_and_detects_later_image_change(self):
        request = resolve_source(self.args)
        self.assertEqual(request.image_sha256, self.fixture.candidate['composite_sha256'])
        self.assertEqual(request.project_id, self.fixture.candidate['character_id'])
        request.validate()
        request.input_image.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            request.validate()

    def test_conflicting_or_incomplete_sources_rejected(self):
        self.args.project = 'display-name.psd'
        with self.assertRaisesRegex(ValueError, 'arguments_invalid'):
            resolve_source(self.args)
        self.args.character = None; self.args.project = None
        with self.assertRaisesRegex(ValueError, 'arguments_invalid'):
            resolve_source(self.args)

    def test_wrong_model_is_rejected_before_loading_optional_runtime(self):
        request = resolve_source(self.args)
        model = self.fixture.root/'wrong.onnx'; model.write_bytes(b'not-a-model')
        with self.assertRaisesRegex(ValueError, 'model_identity_mismatch'):
            DWPoseOnnxRunner(model, self.fixture.state).produce(request)


if __name__ == '__main__':
    unittest.main()
