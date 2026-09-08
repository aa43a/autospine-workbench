"""Component proposals fail closed on ambiguous geometry and preserve pixels."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import unittest

from tests.test_layer_binding import fixture
from autospine_workbench.asset.joints.binding_completion import build_completion
from autospine_workbench.asset.joints.reviewed_skeleton import build_reviewed_skeleton
from autospine_workbench.asset.joints.structure_candidates import assign_components, build_structure_candidates, validate_structure_candidates
from autospine_workbench.benchmark.layer_binding_draft import build_layer_binding_draft
from autospine_workbench.resolved_project import canonical_sha256


def inputs(name='footwear'):
    from PIL import Image, ImageDraw
    candidate, assisted, _ = fixture(name)
    image = Image.new('RGBA', (40, 60)); draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, 12, 30), fill='white'); draw.rectangle((26, 2, 36, 30), fill='white')
    draw.point((20, 50), fill='white')
    stream = BytesIO(); image.save(stream, format='PNG'); raw = stream.getvalue()
    candidate['layers'][1]['image_sha256'] = hashlib.sha256(raw).hexdigest()
    assisted['candidate_sha256'] = assisted['draft']['candidate_sha256'] = canonical_sha256(candidate)
    skeleton = build_reviewed_skeleton(candidate, assisted)
    bindings = build_completion(candidate, assisted, skeleton)
    draft = build_layer_binding_draft(bindings)
    for index in (0, 2):
        draft['records'][index].update(action='exclude', notes='outside synthetic test scope')
    return candidate, assisted, skeleton, bindings, draft, {'layer-001': raw}


class StructureCandidateTests(unittest.TestCase):
    def test_anatomical_side_not_screen_side_and_ties(self):
        bones = {'foot_l': {'head_xy': [90, 0], 'tail_xy': [90, 20]},
                 'foot_r': {'head_xy': [10, 0], 'tail_xy': [10, 20]}}
        points = [{'id': i, 'centroid': [x, 10]} for i, x in enumerate((12, 88, 50, 500))]
        rows = assign_components(points, ('foot',), bones, 100)
        self.assertEqual([r['side'] for r in rows], ['r', 'l', None, None])
        mirrored = {key: {k: [100-v[0], v[1]] for k,v in bone.items()} for key,bone in bones.items()}
        reversed_points = [{**r, 'centroid': [100-r['centroid'][0],10]} for r in points]
        self.assertEqual([r['side'] for r in assign_components(reversed_points, ('foot',), mirrored,100)],
                         [r['side'] for r in rows])

    def test_pixel_accounting_purity_and_exact_validator(self):
        args = inputs(); before = deepcopy(args)
        doc = build_structure_candidates(*args)
        self.assertEqual(args, before)
        self.assertEqual(doc, validate_structure_candidates(*args, doc))
        row = doc['layers'][0]
        self.assertEqual(row['component_count'], 3)
        self.assertEqual(row['omitted_alpha_pixel_count'], 1)
        self.assertEqual(sum(c['area'] for c in row['components'])+1, row['alpha_pixel_count'])
        self.assertFalse(doc['production_authorized'])
        bad = deepcopy(doc); bad['layers'][0]['alpha_pixel_count'] += 1
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            validate_structure_candidates(*args, bad)
        args[-1]['layer-001'] += b'changed'
        with self.assertRaisesRegex(ValueError, 'image_changed'):
            build_structure_candidates(*args)

    def test_garment_static_candidate_unknown_remains_blocked(self):
        row = build_structure_candidates(*inputs('bottomwear'))['layers'][0]
        self.assertEqual(row['proposal']['kind'], 'rigid_setup_only')
        self.assertEqual(row['proposal']['bone_ids'], ['pelvis'])
        row = build_structure_candidates(*inputs('objects'))['layers'][0]
        self.assertEqual(row['status'], 'blocked')
        self.assertIsNone(row['proposal'])

    def test_completed_layers_omitted_and_stale_draft_rejected(self):
        args = inputs('bottomwear')
        args[4]['records'][1].update(action='exclude', notes='reviewed')
        self.assertEqual(build_structure_candidates(*args)['layers'], [])
        args[4]['source_bindings_sha256'] = '0'*64
        with self.assertRaises(ValueError):
            build_structure_candidates(*args)

    def test_schema(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        path = Path(__file__).resolve().parents[1]/'schemas/structure-candidates-v1.schema.json'
        Draft202012Validator(json.loads(path.read_text('utf-8'))).validate(build_structure_candidates(*inputs()))
