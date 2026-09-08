"""Strategy evidence must not mutate decisions or authorize unsupported rigs."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import unittest
from PIL import Image
from autospine_workbench.asset.planning.rig_planner import build, validate, strategy
from autospine_workbench.benchmark.layer_binding_draft import build_layer_binding_draft
from autospine_workbench.resolved_project import canonical_sha256


def fixture():
    image = Image.new('RGBA', (4, 4), (255, 255, 255, 255))
    image.putpixel((1, 1), (0, 0, 0, 0))
    out = BytesIO(); image.save(out, format='PNG'); raw = out.getvalue()
    layer = {'layer_id': 'layer-000', 'name': 'mouth', 'semantic': None,
             'bbox': [0, 0, 4, 4], 'image_sha256': sha256(raw).hexdigest()}
    skeleton = {'bones': [{'id': 'head', 'head_xy': [0, 0], 'tail_xy': [3, 3]}]}
    binding = {**layer, 'status': 'needs_review', 'options': [
        {'id': 'rigid:head', 'mode': 'rigid', 'bone_ids': ['head']}]}
    bindings = {'schema': 'autospine.layer-binding-candidates/v2', 'authority': 'none',
        'production_authorized': False, 'status': 'needs_review', 'bindings': [binding],
        'source_skeleton_sha256': canonical_sha256(skeleton)}
    return ({'layers': [layer], 'character_id': 'synthetic'}, skeleton, bindings,
            build_layer_binding_draft(bindings), {'layer-000': raw})


class RigPlannerTests(unittest.TestCase):
    def test_deterministic_readonly_replay_and_schema(self):
        args = fixture(); before = deepcopy(args)
        doc = build(*args)
        self.assertEqual(args, before)
        self.assertEqual(validate(*args, doc), doc)
        self.assertEqual(doc['layers'][0]['strategy'], 'facial')
        self.assertEqual(doc['layers'][0]['preview']['rigid_option_ids'], ['rigid:head'])
        self.assertFalse(doc['production_authorized'])
        import jsonschema
        schema = json.loads(Path('schemas/rig-plan-v1.schema.json').read_text('utf-8'))
        jsonschema.validate(doc, schema)
        bad = deepcopy(doc); bad['layers'][0]['strategy'] = 'rigid'
        with self.assertRaises(ValueError): validate(*args, bad)

    def test_changed_sources_and_bad_scope_fail(self):
        for mutate in (lambda a: a[4].update({'layer-000': b'changed'}),
                       lambda a: a[1]['bones'][0].update(tail_xy=[8, 9])):
            args = list(fixture()); mutate(args)
            with self.assertRaises(ValueError): build(*args)
        for scope in ([], ['unknown'], ['layer-000', 'layer-000']):
            with self.assertRaises(ValueError): build(*fixture(), focus=scope)

    def test_ambiguous_conflicting_and_disconnected_inputs(self):
        evidence = {'component_count': 2, 'bone_alpha_samples': []}
        options = fixture()[2]['bindings'][0]
        for name, semantic, expected in [('bottomwear', None, 'semantic_review'),
             ('objects', None, 'semantic_review'), ('hair', None, 'secondary_motion'),
             ('mouth', 'hair.back', 'semantic_review'), ('headwear', None, 'rigid')]:
            result = strategy({'name': name, 'semantic': semantic}, options, evidence)
            self.assertEqual(result['strategy'], expected)
            self.assertIn('disconnected_alpha_does_not_authorize_split', result['reason_codes'])
        mesh = {'options': [{'mode': 'mesh_chain', 'bone_ids': ['a', 'b']}]}
        self.assertEqual(strategy({'name':'arm'}, mesh, evidence)['strategy'], 'semantic_review')
        evidence['bone_alpha_samples'] = [{'bone_id':'a'}, {'bone_id':'b'}]
        self.assertEqual(strategy({'name':'arm'}, mesh, evidence)['strategy'], 'weighted_mesh')
