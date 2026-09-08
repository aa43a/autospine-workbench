"""Canonical frame conversion, exact limb motion, and explicit residual substitution."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest
from PIL import Image
from tests.test_wing_character_preview import fixture
from autospine_workbench.benchmark.wing_character_preview import build as context
from autospine_workbench.benchmark.wing_limb_preview import build, verify
from autospine_workbench.benchmark.wing_spine_preview import encode
from autospine_workbench.asset.planning.wing_edge_ownership import encode as png, decode
from autospine_workbench.targets.spine43.wing_rebase import local, setup_frames, rebase
from autospine_workbench.targets.spine43.continuous_pose import world


def inputs():
    source, outputs = context(*fixture())
    files = {n: outputs[n] for n in source['files']}
    bones = [dict(name='root', x=100, y=-90, rotation=67),
             dict(name='chest', parent='root', x=15, y=23, rotation=-20),
             dict(name='limb', parent='chest', x=12, y=4, rotation=-110)]
    points = [[10, 20], [30, 20], [30, 50], [10, 50]]
    frame = setup_frames(bones)['limb']; vertices = []
    for x, y in points:
        vertices.extend([1, 2, *local(x, -y, frame), 1])
    attachment = dict(type='mesh', path='part-l', uvs=[0, 0, 1, 0, 1, 1, 0, 1],
                      triangles=[0, 1, 2, 0, 2, 3], vertices=vertices, width=20, height=30)
    track = {'rotate': [dict(time=i*.5, value=v) for i, v in enumerate([0, -10, 0, 10, 0])]}
    doc = dict(skeleton={'spine': '4.3.26'}, bones=bones, slots=[dict(name='part-l', bone='limb', attachment='part-l')],
               skins=[dict(name='default', attachments={'part-l': {'part-l': attachment}})],
               animations={'limb': dict(bones={'limb': track})})
    page = Image.new('RGBA', (24, 68))
    page.putpixel((4, 36), (40, 70, 100, 128))
    page_raw = png(page)
    donor_files = {'skeleton.json': encode(doc), 'skeleton.atlas': b'\nlimb-page',
                   'textures/layer-000.png': page_raw, 'preview-manifest.json': encode({'regions': [dict(id='part-l', setup_vertices_xy=points)]})}
    donor = dict(schema='autospine.seam-stable-fallback/v1', authority='none', production_authorized=False,
                 files={n: sha256(r).hexdigest() for n, r in donor_files.items()})
    atlas = dict(source_skeleton_sha256='a'*64, files={'layer-000/page.png': sha256(page_raw).hexdigest()},
                 layers=[dict(layer_id='layer-000', page_ref='layer-000/page.png', partitions=[{'id': 'part-l'}],
                              residual=dict(owner_code=3, visible_pixels=1), tiles=[dict(owner_code=3, rect=[2, 34, 20, 30])])])
    return source, files, donor, donor_files, atlas


class WingLimbTests(unittest.TestCase):
    def test_rotated_canonical_frame_and_residual_replaces_whole_context(self):
        args = inputs(); untouched = deepcopy(args)
        report, outputs = build(*args)
        doc = json.loads(outputs['skeleton.json']); donor = json.loads(args[3]['skeleton.json'])
        self.assertEqual(args, untouched)
        self.assertEqual(doc['bones'][:len(donor['bones'])], donor['bones'])
        self.assertEqual(doc['skins'][0]['attachments']['part-l'], donor['skins'][0]['attachments']['part-l'])
        self.assertEqual([s['name'] for s in doc['slots']], ['wing-c0', 'part-l', 'context-layer-000', 'context-layer-002', 'topwear'])
        image = decode(outputs['editor/images/context-layer-000.png'])
        self.assertEqual(image.getpixel((2, 2)), (40, 70, 100, 128))
        self.assertEqual(sum(a>0 for a in image.getchannel('A').tobytes()), 1)
        self.assertNotIn('chest', next(iter(doc['animations'].values()))['bones'])
        self.assertLess(report['wing_local_motion_max_error_px'], 1e-7)
        self.assertEqual(report['limb_residual_context_pixels'], 1)
        for time in [0, .123, .5, 1, 1.5, 2]:
            self.assertEqual(world(doc, time)['part-l'], world(donor, time)['part-l'])

    def test_replay_and_schema(self):
        args = inputs(); report, outputs = build(*args)
        self.assertEqual(verify(report, *args), report)
        for n, digest in report['files'].items():
            self.assertEqual(sha256(outputs[n]).hexdigest(), digest)
        import jsonschema
        jsonschema.validate(report, json.loads(Path('schemas/wing-limb-preview-v1.schema.json').read_text()))
        report['limb_motion_unchanged'] = False
        with self.assertRaisesRegex(ValueError, 'replay'): verify(report, *args)

    def test_stale_pixels_and_ownership_rejected(self):
        for kind in ['file', 'page', 'owner']:
            args = inputs()
            if kind == 'file': args[3]['skeleton.atlas'] = b'changed'
            if kind == 'page': args[4]['files']['layer-000/page.png'] = '0'*64
            if kind == 'owner': args[4]['layers'][0]['partitions'] = [{'id': 'missing'}]
            with self.subTest(kind=kind), self.assertRaises(ValueError): build(*args)

    def test_unsupported_scale_and_name_collision_rejected(self):
        args = inputs(); wing = json.loads(args[1]['skeleton.json']); canonical = json.loads(args[3]['skeleton.json'])
        canonical['bones'][0]['scaleX'] = 2
        with self.assertRaisesRegex(ValueError, 'transform'): rebase(wing, canonical)
        del canonical['bones'][0]['scaleX']
        next(iter(canonical['animations'].values()))['bones']['limb']['translate'] = []
        with self.assertRaisesRegex(ValueError, 'tracks'): rebase(wing, canonical)
        del next(iter(canonical['animations'].values()))['bones']['limb']['translate']
        canonical['bones'].append(dict(name='wing-c0', parent='chest', x=0, y=0, rotation=0))
        with self.assertRaisesRegex(ValueError, 'collision'): rebase(wing, canonical)
