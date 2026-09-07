"""Synthetic reviewed annotations exercise the independent assisted skeleton CLI."""
from copy import deepcopy
import json
import unittest

from tests import test_benchmark_assisted_joint_cli as fixtures
from autospine_workbench.benchmark.__main__ import parser, _execute
from autospine_workbench.benchmark.artifacts import publish_report
from autospine_workbench.benchmark.assisted_skeleton_cli import read_assisted_skeleton
from autospine_workbench.resolved_project import canonical_sha256


class AssistedSkeletonCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AssistedCliTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture.f

    def annotations(self, reviewed=True):
        draft = self.fixture.run_page()
        w, h = self.f.candidate['canvas']
        positions = {'root': [.50, .96], 'pelvis': [.48, .60], 'chest': [.52, .34],
                     'neck': [.51, .26], 'head': [.50, .16]}
        for side, sign in (('left', 1), ('right', -1)):
            for joint, dx, y in (('shoulder', .20, .35), ('elbow', .28, .46), ('wrist', .35, .57),
                                 ('hip', .10, .60), ('knee', .12, .74), ('ankle', .14, .88)):
                positions[f'{joint}.{side}'] = [.50+sign*dx, y]
        for row in draft['draft']['records']:
            x, y = positions[row['joint_id']]
            row.update(position=[round(x*w, 3), round(y*h, 3)], status='observed', notes='Synthetic CLI test only')
        draft['reviewed_joint_ids'] = [row['joint_id'] for row in draft['draft']['records']] if reviewed else []
        path = self.f.root / 'synthetic-reviewed-annotations.json'
        path.write_text(json.dumps(draft), encoding='utf-8')
        self.assertEqual(self.fixture.run_page('--draft', path, html='reviewed.html'), draft)
        return path

    def build(self, path):
        args = ['--state-root', self.f.state, 'build-assisted-skeleton', '--manifest', self.f.root/'manifest.json',
                '--workspace', self.f.root, '--draft', path, '--html', self.f.root/'reviewed-skeleton.html']
        return _execute(parser().parse_args(list(map(str, args))))

    def test_reviewed_chain_twenty_bones_central_anchors_and_idempotence(self):
        path = self.annotations()
        first = self.build(path)
        doc, _, _, code = first
        self.assertEqual(code, 0)
        self.assertEqual(doc['status'], 'candidate_requires_review')
        self.assertEqual(len(doc['bones']), 20)
        self.assertFalse(doc['production_authorized'])
        source = json.loads(path.read_text('utf-8'))
        positions = {r['joint_id']: r['position'] for r in source['draft']['records']}
        bones = {r['id']: r for r in doc['bones']}
        for joint in ('root', 'pelvis', 'chest', 'neck', 'head'):
            self.assertEqual(bones[joint]['head_xy'], positions[joint])
        self.assertEqual(self.build(path), first)
        self.assertEqual(read_assisted_skeleton(self.f.state, self.f.manifest, canonical_sha256(doc), workspace=self.f.root), doc)

    def test_missing_reviews_block_without_bones(self):
        doc, _, _, code = self.build(self.annotations(reviewed=False))
        self.assertEqual(code, 2)
        self.assertEqual(doc['bones'], [])
        self.assertIn('all_joint_reviews_required', doc['reason_codes'])

    def test_forged_document_and_changed_source_fail_exact_reader(self):
        doc = self.build(self.annotations())[0]
        forged = deepcopy(doc)
        forged['bones'][0]['head_xy'][0] += 1
        digest = publish_report(self.f.state, self.f.manifest['dataset_id'], 'assisted-skeleton-candidates', forged)
        with self.assertRaises(ValueError):
            read_assisted_skeleton(self.f.state, self.f.manifest, digest, workspace=self.f.root)
        (self.f.root/'layer-0.png').write_bytes(b'changed source')
        with self.assertRaises(ValueError):
            read_assisted_skeleton(self.f.state, self.f.manifest, canonical_sha256(doc), workspace=self.f.root)


if __name__ == '__main__':
    unittest.main()
