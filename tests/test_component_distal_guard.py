from copy import deepcopy
import unittest
from autospine_workbench.asset.planning.component_distal_guard import gate, inventory


class DistalGuardTests(unittest.TestCase):
    def test_exact_replay_pairing_and_preserved_inputs(self):
        from tests.test_component_weight_transition import limb_fixture
        from autospine_workbench.asset.planning.component_mesh import build as mesh
        from autospine_workbench.asset.planning.component_weight_transition import build as transition
        from autospine_workbench.asset.planning.component_parent_distal import build as distal
        from autospine_workbench.asset.planning.component_local_correction import build as correction
        from autospine_workbench.asset.planning.component_collar import build as collar
        from autospine_workbench.asset.planning.component_collar_keys import build as keys
        from autospine_workbench.asset.planning.component_distal_guard import build
        args = limb_fixture(); old = transition(mesh(*args), args[1], args[0])
        trial = distal(old, args[0], args[1])
        def finish(source): return keys(source, collar(source, correction(source, args[1]), args[1]), args[1])
        a, b = finish(old), finish(trial); snapshot = deepcopy((old, trial, a, b))
        result = build(old, trial, a, b, args[1])
        self.assertEqual(result, build(old, trial, a, b, args[1]))
        self.assertEqual(snapshot, (old, trial, a, b))
        selected = result['evidence'][0]['selected_trial']
        self.assertEqual(result['records'][0], (trial if selected else old)['records'][0])
        self.assertEqual(result['rows'][0], (b if selected else a)['rows'][0])
        self.assertFalse(result['production_authorized'])
        b['source_sha256'] = '0'*64
        with self.assertRaises(ValueError): build(old, trial, a, b, args[1])

    def test_regression_on_one_tick_blocks_aggregate_gain(self):
        bad = dict(inversions=2, min_area_ratio=-.1, max_area_ratio=1.5, max_edge_stretch=2.5, bad_triangles=[1,2])
        good = dict(inversions=0, min_area_ratio=.8, max_area_ratio=1.2, max_edge_stretch=1.5, bad_triangles=[])
        before = [deepcopy(bad) for _ in range(129)]
        after = [deepcopy(good) for _ in range(129)]
        self.assertEqual(gate(before, after), ([], True))
        after[127]['inversions'] = 3
        self.assertIn('new_inversion', gate(before, after)[0])
        after[127] = deepcopy(bad); after[127]['max_edge_stretch'] = 3
        self.assertIn('edge_stretch_regression', gate(before, after)[0])
        self.assertEqual(gate(before, before), ([], False))

    def test_inventory_and_nonfinite_fail_closed(self):
        with self.assertRaises(ValueError): gate([], [])
        row = dict(inversions=0, min_area_ratio=float('nan'), max_area_ratio=1., max_edge_stretch=1., bad_triangles=[])
        with self.assertRaises(ValueError): gate([row]*129, [row]*129)
        with self.assertRaises(ValueError): inventory([dict(layer_id='x', component_id='y')]*2)
