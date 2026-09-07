"""Real PNG diagnostics with synthetic inputs, never real review decisions."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from tests import test_benchmark_semantic_cli as fixtures
from autospine_workbench.benchmark.artifacts import publish_report
from autospine_workbench.benchmark.joint_comparison_cli import read_joint_comparison
from autospine_workbench.benchmark.joint_comparison_view import composite_height
from autospine_workbench.benchmark.joint_draft import build_joint_draft
from autospine_workbench.resolved_project import canonical_sha256


class JointComparisonCliTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image

        self.fixture = fixtures.SemanticCliTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.manifest = self.fixture.root, self.fixture.manifest
        self.state = self.fixture.fixture.fixture.state
        canvas = self.fixture.audit['canvas']
        image = Image.new('RGBA', canvas)
        image.paste((1, 2, 3, 255), (10, 20, 40, 80))
        raw = BytesIO()
        image.save(raw, format='PNG')
        self.raw = raw.getvalue()
        self.fixture.evidence['characters'][0]['outputs']['composite'] = self.fixture.write_asset('composite.png', self.raw)
        self.candidate = self.fixture.load()[0]
        for name, doc in (('manifest', self.manifest), ('evidence', self.fixture.evidence)):
            (self.root / (name + '.json')).write_text(json.dumps(doc), encoding='utf-8')

    def invoke(self, *extra):
        return self.fixture.fixture.fixture.invoke('compare-joints',
            '--manifest', self.root / 'manifest.json', '--evidence', self.root / 'evidence.json',
            '--workspace', self.root, '--character', self.candidate['character_id'],
            '--html', self.root / 'comparison.html', *extra)

    def test_empty_reference_is_null_and_replay_is_exact(self):
        code, report = self.invoke()
        self.assertEqual(code, 0, report)
        self.assertEqual(report['summary']['compared'], 0)
        self.assertIsNone(report['summary']['median_distance_px'])
        self.assertEqual(report['character_height_px'], 60)
        self.assertEqual(read_joint_comparison(self.state, self.manifest, canonical_sha256(report), workspace=self.root), report)
        html = (self.root / 'comparison.html').read_text(encoding='utf-8')
        self.assertIn('暂无可比较标注', html)
        self.assertIn('data:image/png;base64,', html)
        self.assertIn('id="base"', html)
        self.assertNotIn('<script', html)

    def test_observation_is_diagnostic_and_tampered_report_fails(self):
        draft = build_joint_draft(self.candidate)
        draft['records'][0].update(status='observed', position=[50, 60])
        draft['records'][1].update(status='unobservable', notes='TEST ONLY occlusion')
        path = self.root / 'draft.json'
        path.write_text(json.dumps(draft), encoding='utf-8')
        code, report = self.invoke('--draft', path)
        self.assertEqual(code, 0, report)
        self.assertTrue(report['diagnostic_only'])
        self.assertEqual(report['summary']['compared'], 1)
        self.assertEqual(report['summary']['unobservable'], 1)
        forged = deepcopy(report)
        forged['character_height_px'] = 120
        digest = publish_report(self.state, self.manifest['dataset_id'], 'joint-comparisons', forged)
        with self.assertRaises(ValueError):
            read_joint_comparison(self.state, self.manifest, digest, workspace=self.root)
        (self.root / 'composite.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            read_joint_comparison(self.state, self.manifest, canonical_sha256(report), workspace=self.root)

    def test_wrong_draft_publishes_nothing(self):
        draft = build_joint_draft(self.candidate)
        draft['candidate_sha256'] = '0' * 64
        path = self.root / 'bad.json'
        path.write_text(json.dumps(draft), encoding='utf-8')
        self.assertEqual(self.invoke('--draft', path)[0], 1)
        self.assertFalse(self.state.exists())
        self.assertFalse((self.root / 'comparison.html').exists())

    def test_alpha_height_is_not_canvas_height_and_requires_exact_image(self):
        self.assertEqual(composite_height(self.candidate, self.raw), 60)
        with self.assertRaises(ValueError):
            composite_height(self.candidate, self.raw + b'changed')


if __name__ == '__main__':
    unittest.main()
