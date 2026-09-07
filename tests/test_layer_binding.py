"""Chain choices are explicit, unweighted and independent of canvas-side guesses."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.asset.joints.layer_binding import build_layer_bindings, validate_layer_bindings
from autospine_workbench.asset.joints.region_binding import build_region_bindings
from autospine_workbench.asset.joints.reviewed_skeleton import build_reviewed_skeleton
from autospine_workbench.resolved_project import canonical_sha256
from tests.test_region_binding import fixture as rigid_fixture


def fixture(name='handwear-l'):
    candidate, assisted, _ = rigid_fixture()
    for row in candidate['layers']:
        row['name'] = 'face'
    candidate['layers'][1].update(name=name, semantic=None)
    assisted['candidate_sha256'] = assisted['draft']['candidate_sha256'] = canonical_sha256(candidate)
    return candidate, assisted, build_reviewed_skeleton(candidate, assisted)


class LayerBindingTests(unittest.TestCase):
    def test_named_arm_chain_both_options_and_no_weights(self):
        args = fixture()
        before = deepcopy(args)
        doc = build_layer_bindings(*args)
        self.assertEqual(args, before)
        self.assertEqual(doc, validate_layer_bindings(*args, doc))
        row = doc['bindings'][1]
        self.assertEqual(row['suggested_option_id'], 'mesh_chain:l:arm')
        self.assertEqual([o['bone_ids'] for o in row['options']], [['upperarm_l', 'forearm_l', 'hand_l'], ['upperarm_r', 'forearm_r', 'hand_r']])
        self.assertTrue(all(o['setup_local'] is None for o in row['options']))
        self.assertIn('mesh_weights_required', row['reason_codes'])
        self.assertIn('name_side_unreviewed', row['reason_codes'])
        self.assertNotIn('semantic_binding_unsupported', row['reason_codes'])

    def test_nfkc_and_unknown_side_do_not_guess_from_bbox(self):
        for name, suggestion in ((' ＨＡＮＤＷＥＡＲ－Ｒ ', 'mesh_chain:r:arm'), ('sleeve', None), ('leg', None)):
            doc = build_layer_bindings(*fixture(name))
            self.assertEqual(doc['bindings'][1]['suggested_option_id'], suggestion)
            self.assertEqual(len(doc['bindings'][1]['options']), 2 if suggestion else 3)

    def test_unsuffixed_bilateral_option_is_two_chains_not_vertex_weights(self):
        for name, chain in (('handwear', 'arm'), ('legwear', 'leg')):
            args = fixture(name)
            doc = build_layer_bindings(*args)
            row = doc['bindings'][1]
            option = row['options'][2]
            self.assertEqual(option['id'], f'mesh_chain:bilateral:{chain}')
            self.assertEqual(len(option['bone_ids']), 6)
            bones = {bone['id']: bone for bone in args[2]['bones']}
            for ids in (option['bone_ids'][:3], option['bone_ids'][3:]):
                self.assertEqual(bones[ids[1]]['parent_id'], ids[0])
                self.assertEqual(bones[ids[2]]['parent_id'], ids[1])
            self.assertNotEqual(bones[option['bone_ids'][3]]['parent_id'], option['bone_ids'][2])
            self.assertIsNone(option['setup_local'])
            self.assertNotIn('weights', option)
            self.assertIn('bilateral_coverage_requires_review', row['reason_codes'])

    def test_rigid_options_preserved_and_leg_chain(self):
        args = fixture('legwear-r')
        rigid = build_region_bindings(*args)
        doc = build_layer_bindings(*args)
        self.assertEqual(doc['bindings'][0]['options'][0]['setup_local'], rigid['bindings'][0]['bone_options'][0]['setup_local'])
        self.assertEqual(doc['bindings'][0]['options'][0]['id'], 'rigid:head')
        self.assertEqual(doc['bindings'][1]['options'][1]['bone_ids'], ['thigh_r', 'calf_r', 'foot_r'])

    def test_blocked_empty_and_topology_tamper(self):
        candidate, assisted, _ = fixture()
        candidate['layers'][1]['observed']['empty'] = True
        assisted['candidate_sha256'] = assisted['draft']['candidate_sha256'] = canonical_sha256(candidate)
        doc = build_layer_bindings(candidate, assisted, build_reviewed_skeleton(candidate, assisted))
        self.assertEqual(doc['bindings'][1]['options'], [])
        args = fixture()
        args[2]['bones'][8]['parent_id'] = 'root'
        with self.assertRaises(ValueError):
            build_layer_bindings(*args)

    def test_tamper_and_schema(self):
        args = fixture()
        doc = build_layer_bindings(*args)
        changed = deepcopy(doc)
        changed['bindings'][1]['options'][0]['bone_ids'].reverse()
        with self.assertRaises(ValueError):
            validate_layer_bindings(*args, changed)
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/layer-binding-candidates-v2.schema.json').read_text('utf-8'))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(doc)
        Draft202012Validator(schema).validate(build_layer_bindings(*fixture('handwear')))


if __name__ == '__main__':
    unittest.main()
