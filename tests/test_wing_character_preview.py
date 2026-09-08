"""Whole-character context must preserve candidate motion and source identity."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest
from PIL import Image
from autospine_workbench.asset.planning.wing_edge_ownership import encode as png
from autospine_workbench.benchmark.wing_spine_preview import encode
from autospine_workbench.benchmark.wing_pendant_preview import local, setup_frames
from autospine_workbench.benchmark.wing_character_preview import build, verify
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.spine43.continuous_pose import world


def fixture():
    bones = [dict(name='root', x=0, y=0, rotation=0),
             dict(name='chest', parent='root', x=10, y=-20, rotation=13),
             dict(name='wing-c0', parent='chest', x=-4, y=3, rotation=-5)]
    frames = setup_frames(bones)
    attachments, regions, slots = {}, [], []
    points = [[10, 20], [30, 20], [30, 50], [10, 50]]
    for name, index in [('wing-c0', 2), ('topwear', 1)]:
        vertices = []
        for x, y in points:
            vertices.extend([1, index, *local(x, -y, frames[bones[index]['name']]), 1])
        attachments[name] = {name: dict(type='mesh', path=name, uvs=[0, 0, 1, 0, 1, 1, 0, 1],
                                      triangles=[0, 1, 2, 0, 2, 3], vertices=vertices, width=20, height=30)}
        slots.append(dict(name=name, bone=bones[index]['name'], attachment=name))
        regions.append(dict(id=name, setup_vertices_xy=points))
    tracks = {n: {'rotate': [dict(time=i*.5, value=v) for i, v in enumerate([0, -8, 0, 8, 0])]}
              for n in ['chest', 'wing-c0']}
    doc = dict(skeleton={'spine': '4.3.26'}, bones=bones, slots=slots,
               skins=[dict(name='default', attachments=attachments)], animations={'wing-root-inspection': {'bones': tracks}})
    raw = png(Image.new('RGBA', (20, 30), (90, 160, 200, 255)))
    roots = dict(character_id='fixture', rows=[dict(layer_id='layer-001', target_layer_id='layer-003')])
    layers = [dict(layer_id=f'layer-{i:03}', name=f'part <{i}>', bbox=[10, 20, 30, 50], image_sha256=sha256(raw).hexdigest()) for i in range(4)]
    candidate = dict(character_id='fixture', layers=layers)
    files = {'skeleton.json': encode(doc), 'skeleton.atlas': b'', 'editor/images/wing-c0.png': raw,
             'editor/images/topwear.png': raw, 'pendants/residual.png': raw}
    source = dict(schema='autospine.wing-pendant-preview/v1', authority='none', production_authorized=False,
                  source_roots_sha256=canonical_sha256(roots), mounted_pendants=[], regions=regions,
                  pendant_candidates={'residual_visible_pixels': 7}, files={n: sha256(r).hexdigest() for n, r in files.items()})
    return source, files, roots, candidate, {r['layer_id']: raw for r in layers}


class WingCharacterTests(unittest.TestCase):
    def test_source_order_wings_back_and_no_original_topwear_duplicate(self):
        inputs = fixture()
        old_inputs = deepcopy(inputs)
        report, files = build(*inputs)
        doc = json.loads(files['skeleton.json'])
        self.assertEqual([s['name'] for s in doc['slots']], ['wing-c0', 'context-layer-000', 'context-layer-002', 'topwear'])
        self.assertEqual(report['context_layer_count'], 2)
        self.assertNotIn('editor/images/context-layer-003.png', files)
        self.assertEqual(files['editor/images/wing-c0.png'], inputs[1]['editor/images/wing-c0.png'])
        self.assertEqual(files['editor/images/topwear.png'], inputs[1]['editor/images/topwear.png'])
        self.assertEqual(inputs, old_inputs)
        self.assertIn(b'part &lt;0&gt;', files['review.html'])
        self.assertFalse(report['full_character_animation'])
        self.assertEqual(report['residual_visible_pixels'], 7)
        original = json.loads(inputs[1]['skeleton.json'])
        self.assertEqual(doc['bones'], original['bones'])
        self.assertEqual(doc['animations'], original['animations'])
        for time in [0, .17, .5, 1.5, 2]:
            before, after = world(original, time), world(doc, time)
            for name in before:
                self.assertEqual(before[name], after[name])
            self.assertEqual(after['context-layer-000'], after['topwear'])

    def test_exact_replay_schema_and_file_inventory(self):
        inputs = fixture()
        report, files = build(*inputs)
        self.assertEqual(build(*inputs), (report, files))
        self.assertEqual(verify(report, *inputs), report)
        for name, digest in report['files'].items():
            self.assertEqual(sha256(files[name]).hexdigest(), digest)
        import jsonschema
        jsonschema.validate(report, json.loads(Path('schemas/wing-character-preview-v1.schema.json').read_text()))
        report['full_character_animation'] = True
        with self.assertRaisesRegex(ValueError, 'replay'):
            verify(report, *inputs)

    def test_changed_pixels_roots_inventory_and_authority_reject(self):
        for mutation in ['pixels', 'roots', 'missing', 'duplicate', 'authority', 'bundle']:
            inputs = list(fixture())
            if mutation == 'pixels': inputs[4]['layer-000'] = b'changed'
            if mutation == 'roots': inputs[2]['rows'][0]['layer_id'] = 'layer-000'
            if mutation == 'missing': del inputs[4]['layer-000']
            if mutation == 'duplicate': inputs[3]['layers'].append(inputs[3]['layers'][0])
            if mutation == 'authority': inputs[0]['production_authorized'] = True
            if mutation == 'bundle': inputs[1]['skeleton.atlas'] = b'changed'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                build(*inputs)
