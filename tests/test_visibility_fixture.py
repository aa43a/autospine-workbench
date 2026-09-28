from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from m4_visibility_fixture import prepare


class VisibilityFixtureTests(unittest.TestCase):
    def fixture(self, root, mutation=None):
        doc = dict(slots=[dict(name='hand')], skins=[dict(attachments={
            'hand': {'mesh': dict(type='mesh')}})])
        if mutation: mutation(doc)
        files = {'skeleton.json': json.dumps(doc).encode(), 'skeleton.atlas': b'', 'textures/a.png': b'png'}
        row = dict(time=.5, region='hand', body='skirt', hypotheses=[dict(time=.5,
            pair=['hand', 'skirt'], status='requires_partition_or_more_depth',
            counts=dict(back=1, ambiguous=0), pixel_locations=dict(back=[[0, -2]], ambiguous=[]))])
        diagnostic = dict(pixel_locations=True, skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
                          source_artifact_sha256='source', rows=[row])
        runtime = dict(passed=True, bundle_sha256='bundle', info=dict(left=0, bottom=0, width=2, height=2),
                       runtime_sha256='runtime', runtime_version='4.3.13',
                       results=[dict(animation='external-motion', time=.5, index=0, draw_order=['hand'])],
                       screenshots=[dict(animation='external-motion', index=0, file='0.png', sha256=sha256(b'png').hexdigest())])
        (root/'partitioned').mkdir(); (root/'partitioned/0.png').write_bytes(b'png')
        (root/'partitioned/report.json').write_text(json.dumps(runtime))
        path = root/'diagnostic.json'; path.write_text(json.dumps(diagnostic))
        return files, path, diagnostic

    def test_exact_probe_and_identity_are_retained_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); files, path, _ = self.fixture(root)
            with patch('m4_visibility_fixture.AnimatedStore') as store:
                store.return_value.read.return_value = files
                prepare(path, root, root/'out.json')
                value = json.loads((root/'out.json').read_bytes())
                self.assertEqual(value['rows'][0]['points'], [dict(x=0, y=0, kind='back')])
                self.assertEqual(value['diagnostic_sha256'], sha256(path.read_bytes()).hexdigest())
                with self.assertRaises(FileExistsError): prepare(path, root, root/'out.json')

    def test_clipping_and_non_normal_blending_require_different_renderer(self):
        for mutate, reason in [(lambda d: d['slots'][0].update(blend='additive'), 'blend'),
                               (lambda d: d['skins'][0]['attachments']['hand']['mesh'].update(type='clipping'), 'clipping')]:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); files, path, _ = self.fixture(root, mutate)
                with patch('m4_visibility_fixture.AnimatedStore') as store:
                    store.return_value.read.return_value = files
                    with self.assertRaisesRegex(ValueError, reason): prepare(path, root, root/'out.json')
                self.assertFalse((root/'out.json').exists())

    def test_changed_screenshot_and_cross_frame_markers_reject(self):
        for kind in ['image', 'time', 'count']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); files, path, value = self.fixture(root)
                if kind == 'image': (root/'partitioned/0.png').write_bytes(b'changed')
                elif kind == 'time': value['rows'][0]['hypotheses'][0]['time'] = .6
                else: value['rows'][0]['hypotheses'][0]['counts']['back'] = 2
                path.write_text(json.dumps(value))
                with patch('m4_visibility_fixture.AnimatedStore') as store:
                    store.return_value.read.return_value = files
                    with self.assertRaises(ValueError): prepare(path, root, root/'out.json')
                self.assertFalse((root/'out.json').exists())
