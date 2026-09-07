"""Synthetic binding candidates preserve raster setup while withholding decisions."""
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.asset.joints.region_binding import build_region_bindings, validate_region_bindings
from autospine_workbench.asset.joints.reviewed_skeleton import build_reviewed_skeleton
from autospine_workbench.resolved_project import canonical_sha256
from tests.test_reviewed_skeleton import fixture as skeleton_fixture


def fixture():
    candidate, assisted = skeleton_fixture()
    candidate['layers'] = [{'layer_id': f'layer-{i:03}', 'traversal_index': i, 'image_sha256': str(i+1)*64,
                            'bbox': [10, 20, 50, 80], 'observed': {'empty': False, 'visible': True},
                            'semantic': semantic, 'raw_name_side': 'l'}
                           for i, semantic in enumerate(('body.face', 'body.arm.upper', None))]
    digest = canonical_sha256(candidate)
    assisted['candidate_sha256'] = assisted['draft']['candidate_sha256'] = digest
    return candidate, assisted, build_reviewed_skeleton(candidate, assisted)


class RegionBindingTests(unittest.TestCase):
    def test_pure_single_suggestion_paired_no_side_guess_and_unknown_block(self):
        args = fixture()
        before = deepcopy(args)
        doc = build_region_bindings(*args)
        self.assertEqual(args, before)
        self.assertEqual(validate_region_bindings(*args, doc), doc)
        first, paired, unknown = doc['bindings']
        self.assertEqual(first['suggested_bone_id'], 'head')
        self.assertIsNone(paired['suggested_bone_id'])
        self.assertEqual([r['bone_id'] for r in paired['bone_options']], ['upperarm_l', 'upperarm_r'])
        self.assertEqual(unknown['status'], 'blocked')
        self.assertEqual(unknown['bone_options'], [])
        self.assertEqual([r['layer_id'] for r in doc['bindings']], [r['layer_id'] for r in args[0]['layers']])

    def test_every_option_reconstructs_all_four_setup_corners(self):
        args = fixture()
        doc = build_region_bindings(*args)
        bones = {b['id']: b for b in args[2]['bones']}
        for row in doc['bindings']:
            x0, y0, x1, y1 = row['bbox']
            center = [(x0+x1)/2, (y0+y1)/2]
            for option in row['bone_options']:
                bone, local = bones[option['bone_id']], option['setup_local']
                r = math.radians(local['rotation_degrees'])
                b = math.radians(bone['world_rotation_degrees'])
                for x, y in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
                    dx, dy = x-center[0], y-center[1]
                    lx, ly = local['x']+dx*math.cos(r)-dy*math.sin(r), local['y']+dx*math.sin(r)+dy*math.cos(r)
                    world = [bone['head_xy'][0]+lx*math.cos(b)-ly*math.sin(b), bone['head_xy'][1]+lx*math.sin(b)+ly*math.cos(b)]
                    self.assertAlmostEqual(world[0], x, places=9)
                    self.assertAlmostEqual(world[1], y, places=9)

    def test_empty_hidden_outside_and_blocked_skeleton(self):
        for mutate, reason in ((lambda r: r['observed'].update(empty=True), 'empty_layer'),
                               (lambda r: r['observed'].update(visible=False), 'hidden_layer'),
                               (lambda r: r.update(bbox=[-1, 20, 50, 80]), 'layer_outside_canvas')):
            candidate, assisted, _ = fixture()
            mutate(candidate['layers'][0])
            assisted['candidate_sha256'] = assisted['draft']['candidate_sha256'] = canonical_sha256(candidate)
            doc = build_region_bindings(candidate, assisted, build_reviewed_skeleton(candidate, assisted))
            self.assertIn(reason, doc['bindings'][0]['reason_codes'])
            self.assertEqual(doc['bindings'][0]['bone_options'], [])
        candidate, assisted, _ = fixture()
        assisted['reviewed_joint_ids'] = []
        doc = build_region_bindings(candidate, assisted, build_reviewed_skeleton(candidate, assisted))
        self.assertEqual(doc['status'], 'blocked')
        self.assertTrue(all(not r['bone_options'] for r in doc['bindings']))

    def test_tamper_and_schema(self):
        args = fixture()
        doc = build_region_bindings(*args)
        forged = deepcopy(doc)
        forged['bindings'][1]['suggested_bone_id'] = 'upperarm_l'
        with self.assertRaises(ValueError):
            validate_region_bindings(*args, forged)
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/region-binding-candidates-v1.schema.json').read_text('utf-8'))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(doc)


if __name__ == '__main__':
    unittest.main()
