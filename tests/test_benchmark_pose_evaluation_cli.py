"""Synthetic-only CLI evaluation; no real human annotation is created."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from tests import test_benchmark_r2a_cli as fixtures
from autospine_workbench.benchmark.artifacts import publish_report
from autospine_workbench.benchmark.joint_draft import build_joint_draft
from autospine_workbench.benchmark.joint_reference_cli import read_joint_reference
from autospine_workbench.benchmark.pose_accuracy_cli import read_pose_evaluation
from autospine_workbench.resolved_project import canonical_sha256


class PoseEvaluationCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.R2aCliTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.state, self.manifest = self.fixture.root, self.fixture.state, self.fixture.manifest
        code, run = self.fixture.invoke()
        self.assertEqual(code, 0, run)
        self.run_path = self.root / 'r2a.json'
        self.run_path.write_text(json.dumps(run), encoding='utf-8')

    def invoke(self, *args):
        return self.fixture.fixture.fixture.fixture.fixture.invoke(*args)

    def evaluate(self, reference=None):
        args = ['evaluate-pose-benchmark', '--manifest', self.root / 'manifest.json', '--workspace', self.root,
                '--run', self.run_path, '--html', self.root / ('accuracy-reference.html' if reference else 'accuracy.html')]
        if reference:
            args += ['--reference', reference]
        return self.invoke(*args)

    def draft(self, observed=True):
        draft = build_joint_draft(self.fixture.candidate)
        if observed:
            pose = json.loads(self.fixture.pose_path.read_text('utf-8'))
            row = next(r for r in draft['records'] if r['joint_id'] == 'shoulder.left')
            row.update(status='observed', position=pose['joints']['shoulder.left']['xy'], notes='SYNTHETIC TEST ONLY')
        path = self.root / 'synthetic-reference-draft.json'
        path.write_text(json.dumps(draft), encoding='utf-8')
        return path

    def record(self, path, confirm=True, independent=True):
        args = ['record-joint-reference', '--manifest', self.root / 'manifest.json', '--evidence', self.root / 'evidence.json',
                '--workspace', self.root, '--character', self.fixture.candidate['character_id'], '--draft', path,
                '--reviewer', 'synthetic-test-only-reviewer']
        if confirm:
            args += ['--confirm-human-review']
        if independent:
            args += ['--confirm-independent-annotation']
        return self.invoke(*args)

    def test_no_reference_unknown_errors_exact_replay_and_idempotence(self):
        code, report = self.evaluate()
        self.assertEqual(code, 0, report)
        self.assertIsNone(report['reference_sha256'])
        self.assertEqual(read_pose_evaluation(self.state, self.manifest, canonical_sha256(report), workspace=self.root), report)
        self.assertEqual(self.evaluate(), (0, report))
        self.assertFalse(report['analysis']['accuracy_evaluated'])
        for method in ('baseline', 'pose', 'optimized'):
            self.assertIsNone(report['analysis']['summary'][method]['median_distance_px'])
            for row in report['analysis']['records']:
                self.assertIsNone(row['methods'][method]['distance_px'])

    def test_synthetic_reference_records_and_evaluates(self):
        code, reference = self.record(self.draft())
        self.assertEqual(code, 0, reference)
        self.assertEqual(reference['scope'], 'benchmark_only')
        self.assertEqual(read_joint_reference(self.state, self.manifest, canonical_sha256(reference), workspace=self.root), reference)
        self.assertEqual(self.record(self.draft()), (0, reference))
        path = self.root / 'synthetic-reference.json'
        path.write_text(json.dumps(reference), encoding='utf-8')
        code, report = self.evaluate(path)
        self.assertEqual(code, 0, report)
        self.assertEqual(report['reference_sha256'], canonical_sha256(reference))
        self.assertTrue(report['analysis']['accuracy_evaluated'])
        for method in ('baseline', 'pose', 'optimized'):
            self.assertEqual(report['analysis']['summary'][method]['compared'], 1)
            self.assertIsInstance(report['analysis']['summary'][method]['median_distance_px'], (int, float))
        self.assertEqual(report['analysis']['summary']['pose']['median_distance_px'], 0)
        self.assertEqual(read_pose_evaluation(self.state, self.manifest, canonical_sha256(report), workspace=self.root), report)

    def test_missing_confirmation_blank_and_wrong_candidate_publish_no_reference(self):
        self.assertEqual(self.record(self.draft(), confirm=False)[0], 1)
        self.assertEqual(self.record(self.draft(), independent=False)[0], 1)
        self.assertEqual(self.record(self.draft(observed=False))[0], 1)
        path = self.draft()
        draft = json.loads(path.read_text('utf-8'))
        draft['candidate_sha256'] = '0'*64
        path.write_text(json.dumps(draft), encoding='utf-8')
        self.assertEqual(self.record(path)[0], 1)
        folder = self.state / 'benchmarks' / self.manifest['dataset_id'] / 'joint-references'
        self.assertFalse(folder.exists())

    def test_forged_reference_and_evaluation_source_changes_fail(self):
        _, reference = self.record(self.draft())
        forged = deepcopy(reference)
        forged['reviewer'] = 'forged-reviewer'
        digest = publish_report(self.state, self.manifest['dataset_id'], 'joint-references', forged)
        with self.assertRaises(ValueError):
            read_joint_reference(self.state, self.manifest, digest, workspace=self.root)
        _, report = self.evaluate()
        forged = deepcopy(report)
        forged['reference_sha256'] = canonical_sha256(reference)
        digest = publish_report(self.state, self.manifest['dataset_id'], 'pose-evaluations', forged)
        with self.assertRaises(ValueError):
            read_pose_evaluation(self.state, self.manifest, digest, workspace=self.root)
        (self.root / 'composite.png').write_bytes(b'changed-source')
        with self.assertRaises(ValueError):
            read_pose_evaluation(self.state, self.manifest, canonical_sha256(report), workspace=self.root)
        with self.assertRaises(ValueError):
            read_joint_reference(self.state, self.manifest, canonical_sha256(reference), workspace=self.root)


if __name__ == '__main__':
    unittest.main()
