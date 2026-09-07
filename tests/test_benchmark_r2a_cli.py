"""Synthetic technical-chain fixtures, not detector or human accuracy evidence."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from tests import test_benchmark_contact_probe_cli as fixtures
from tests.test_pose_observations import observation_fixture
from autospine_workbench.benchmark.artifacts import publish_report, read_report
from autospine_workbench.benchmark.r2a_cli import read_r2a
from autospine_workbench.resolved_project import canonical_sha256


class R2aCliTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image, ImageDraw

        self.fixture = fixtures.ContactProbeCliTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.manifest, self.state = self.fixture.root, self.fixture.manifest, self.fixture.state
        underlying = self.fixture.fixture
        w, h = underlying.audit['canvas']
        composite = Image.new('RGBA', (w, h))
        draw = ImageDraw.Draw(composite)
        points = {}
        for side, sign in (('left', 1), ('right', -1)):
            for name, dx, y in (('shoulder', .22, .30), ('elbow', .30, .45), ('wrist', .38, .60),
                                ('hip', .08, .58), ('knee', .10, .74), ('ankle', .12, .90)):
                points[f'{name}.{side}'] = [round(w*(.5+sign*dx), 3), round(h*y, 3)]
            for a, b in (('shoulder', 'elbow'), ('elbow', 'wrist'), ('hip', 'knee'), ('knee', 'ankle')):
                draw.line([tuple(points[f'{a}.{side}']), tuple(points[f'{b}.{side}'])], fill='#399589', width=8)
        output = underlying.evidence['characters'][0]['outputs']
        specs = [('topwear', (.25, .27, .75, .34)), ('handwear-l', (.68, .28, .76, .55)),
                 ('handwear-r', (.24, .28, .32, .55))]
        for index, (name, ratios) in enumerate(specs):
            box = [int(v * (w if i % 2 == 0 else h)) for i, v in enumerate(ratios)]
            image = Image.new('RGBA', (box[2]-box[0], box[3]-box[1]), '#78b6d2')
            raw = BytesIO(); image.save(raw, format='PNG')
            output['layers'][index].update(name=name, bbox=box, image=underlying.write_asset(f'layer-{index}.png', raw.getvalue()))
            underlying.audit['layers'][index].update(name=name, bbox=box, empty=False, visible=True,
                                                     alpha_nonzero=image.width*image.height)
            composite.alpha_composite(image, (box[0], box[1]))
        raw = BytesIO(); composite.save(raw, format='PNG')
        output['composite'] = underlying.write_asset('composite.png', raw.getvalue())
        output['audit'] = underlying.write_asset('audit.json', json.dumps(underlying.audit).encode())
        self.candidate = underlying.load()[0]
        for name, doc in (('manifest', self.manifest), ('evidence', underlying.evidence)):
            (self.root / (name + '.json')).write_text(json.dumps(doc), encoding='utf-8')
        pose = observation_fixture()
        pose.update(project_id=self.candidate['character_id'], format_version=2)
        pose['source'].update(image_sha256=self.candidate['composite_sha256'], canvas_size=[w, h])
        pose['detector'].update(id='synthetic-fixture', model_revision='not-a-real-model', runtime='synthetic-test')
        pose['adapter'] = {'id': 'coco17-limb-adapter', 'version': '1', 'input_format': 'autospine-coco17-detections/v1',
                           'input_document_sha256': 'd'*64, 'input_side_naming': 'coco_character_side',
                           'coordinate_transform': 'identity', 'side_mapping': 'as_reported',
                           'view_orientation': 'front', 'mirror_state': 'not_mirrored', 'float_precision_decimals': 6}
        pose['joints'] = {key: {'xy': value, 'detector_score': .9, 'visibility': 'visible'} for key, value in points.items()}
        self.pose_path = self.root / 'synthetic-pose.json'
        self.pose_path.write_text(json.dumps(pose), encoding='utf-8')

    def invoke(self, *, pose=True, command='build-r2a'):
        args = [command, '--manifest', self.root / 'manifest.json', '--evidence', self.root / 'evidence.json',
                '--workspace', self.root, '--character', self.candidate['character_id'], '--html', self.root / 'r2a.html']
        if pose:
            args += ['--pose-observations', self.pose_path]
        return self.fixture.fixture.fixture.fixture.invoke(*args)

    def test_full_chain_matches_optimizes_and_builds_twenty_bones(self):
        code, doc = self.invoke()
        self.assertEqual(code, 0, doc)
        self.assertEqual(doc['bone_count'], 20)
        self.assertFalse(doc['production_authorized'])
        self.assertEqual(read_r2a(self.state, self.manifest, canonical_sha256(doc), workspace=self.root), doc)
        match = read_report(self.state, self.manifest['dataset_id'], 'pose-contact-matches', doc['match_sha256'])
        self.assertEqual(match['summary']['candidate_requires_review'], 2)
        opt = read_report(self.state, self.manifest['dataset_id'], 'joint-optimizations', doc['optimization_sha256'])
        self.assertTrue(any(j['source'] == 'pose_contact' and j['displacement_px'] > 0 for j in opt['joints']))
        self.assertIn('技术链已生成候选骨架', (self.root / 'r2a.html').read_text(encoding='utf-8'))
        self.assertEqual(self.invoke(), (0, doc))

    def test_missing_pose_blocks_without_bones(self):
        code, doc = self.invoke(pose=False)
        self.assertEqual(code, 2)
        self.assertEqual(doc['status'], 'blocked')
        self.assertEqual(doc['bone_count'], 0)

    def test_tampered_run_and_changed_source_fail_exact_replay(self):
        _, doc = self.invoke()
        forged = deepcopy(doc); forged['production_authorized'] = True
        digest = publish_report(self.state, self.manifest['dataset_id'], 'r2a-runs', forged)
        with self.assertRaises(ValueError):
            read_r2a(self.state, self.manifest, digest, workspace=self.root)
        self.pose_path.write_text('{}', encoding='utf-8')
        self.assertEqual(read_r2a(self.state, self.manifest, canonical_sha256(doc), workspace=self.root), doc)
        (self.root / 'layer-0.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            read_r2a(self.state, self.manifest, canonical_sha256(doc), workspace=self.root)

    def test_pose_match_cli_and_wrong_pose_identity(self):
        code, doc = self.invoke(command='match-pose-contacts')
        self.assertEqual(code, 0, doc)
        self.assertEqual(doc['summary']['candidate_requires_review'], 2)
        pose = json.loads(self.pose_path.read_text())
        pose['source']['image_sha256'] = '0'*64
        self.pose_path.write_text(json.dumps(pose), encoding='utf-8')
        self.assertEqual(self.invoke()[0], 1)


if __name__ == '__main__':
    unittest.main()
