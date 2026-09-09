import copy
import math
import unittest
from autospine_workbench.asset.planning.component_ownership import template
from autospine_workbench.asset.planning.component_weight_samples import build, validate
from autospine_workbench.asset.planning.component_weight_review import render


class ComponentWeightSampleTests(unittest.TestCase):
    def fixture(self):
        layer = dict(layer_id='layer', name='handwear-l', bbox=[100, 200, 120, 260])
        region = dict(id='component-0000', runs=[[y, 0, 20] for y in range(60)])
        residual = dict(id='low-alpha-residual', runs=[])
        entries = [(layer, b'', dict(components=[region], residual=residual), 'a'*64)]
        bones = [dict(id=name, parent_id=parent, head_xy=[110, 200+i*20],
                      tail_xy=[110, 220+i*20], world_rotation_degrees=90.)
                 for i, (name, parent) in enumerate([('upperarm_l', 'chest'),
                     ('forearm_l', 'upperarm_l'), ('hand_l', 'forearm_l')])]
        skeleton = dict(bones=bones)
        draft = template('fixture', entries, {}, 'b'*64, [b['id'] for b in bones])
        draft['records'][0].update(status='assigned', semantic='body.arm', side='left',
                                   bone_ids=['hand_l', 'upperarm_l', 'forearm_l'])
        return entries, skeleton, draft, {}, 'b'*64

    def test_exact_mask_samples_weights_and_setup(self):
        args = self.fixture(); result = build(*args)
        self.assertEqual(validate(result, *args), result)
        row = result['records'][0]
        self.assertEqual(row['status'], 'sampled_candidate')
        self.assertEqual(len(row['samples']), 64)
        for sample in row['samples']:
            x, y = sample['canvas_xy']
            self.assertTrue(100 <= x < 120 and 200 <= y < 260)
            self.assertAlmostEqual(sum(w['weight'] for w in sample['influences']), 1.)
        self.assertLess(row['qa']['setup_max_error'], 1e-7)
        self.assertEqual(result['records'][1]['samples'], [])
        self.assertFalse(result['production_authorized'])
        mutated = copy.deepcopy(result); mutated['records'][0]['samples'][0]['influences'][0]['weight'] = .99
        with self.assertRaises(ValueError):
            validate(mutated, *args)

    def test_conflicts_topology_and_nonfinite_block(self):
        for field, value, reason in [('semantic', 'body.foot', 'source_semantic_conflict'),
                                     ('side', 'right', 'side_conflict'),
                                     ('bone_ids', ['hand_l'], 'semantic_chain_mismatch')]:
            args = self.fixture(); args[2]['records'][0][field] = value
            self.assertEqual(build(*args)['records'][0]['reason_code'], reason)
        args = self.fixture(); args[1]['bones'][1]['parent_id'] = 'chest'
        self.assertEqual(build(*args)['records'][0]['reason_code'], 'disconnected_bone_chain')
        args = self.fixture(); args[1]['bones'][1]['head_xy'][0] = math.inf
        # Nonfinite input cannot even acquire a canonical skeleton identity.
        with self.assertRaises(ValueError):
            build(*args)

    def test_stale_sources_and_immutable_input(self):
        args = self.fixture(); before = copy.deepcopy(args)
        build(*args)
        self.assertEqual(args, before)
        args[2]['sources']['plan_sha256'] = 'c'*64
        with self.assertRaises(ValueError):
            build(*args)

    def test_foot_rigid_and_skirt_unsupported(self):
        args = list(self.fixture())
        args[0][0][0]['name'] = 'footwear'
        args[1]['bones'] = [dict(id='foot_l', parent_id='calf_l', head_xy=[110,220],
                                 tail_xy=[110,240], world_rotation_degrees=90.)]
        args[2] = template('fixture', args[0], {}, 'b'*64, ['foot_l'])
        args[2]['records'][0].update(status='assigned', semantic='body.foot', side='left', bone_ids=['foot_l'])
        row = build(*args)['records'][0]
        self.assertTrue(all(s['influences'][0]['weight'] == 1 for s in row['samples']))
        args[0][0][0]['name'] = 'bottomwear'
        args[2]['records'][0]['semantic'] = 'wear.skirt'
        self.assertEqual(build(*args)['records'][0]['reason_code'], 'garment_or_accessory_solver_required')

    def test_review_escapes_user_names(self):
        args = self.fixture(); result = build(*args)
        args[0][0][0]['name'] = '<script>bad()</script>'
        page = render(result, args[0], args[1])
        self.assertNotIn('<script>bad()', page)
        self.assertIn('256', page)
