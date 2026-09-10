"""Bounded candidate improvement preserves labels, protected weights and fallback."""
from copy import deepcopy
import unittest
from test_ordinary_sleeve import fixture
from autospine_workbench.asset.planning.ordinary_sleeve import build as envelope
from autospine_workbench.asset.planning.ordinary_sleeve_repair import build
from autospine_workbench.asset.planning.component_distal_guard import gate
from autospine_workbench.resolved_project import canonical_sha256


class OrdinarySleeveRepairTests(unittest.TestCase):
    def test_role_bounded_graph_can_improve_with_no_track_regression(self):
        source, draft, skeleton = fixture()
        weights = source['records'][0]['mesh']['weights'][0]
        weights[1]['weight'] = 0.; weights[2]['weight'] = 1.
        original = deepcopy((source, draft, skeleton))
        result = build(source, draft, skeleton); record = result['records'][0]
        self.assertTrue(record['selected'])
        self.assertEqual(record['selected_trial'], 'cuff_graph')
        self.assertEqual(len(record['trials']), 3)
        self.assertFalse(result['production_authorized'])
        self.assertEqual((source, draft, skeleton), original)
        before, after = record['before'], record['selected_row']
        self.assertEqual(after['triangles'], before['triangles'])
        self.assertEqual(after['setup_vertices'], before['setup_vertices'])
        self.assertEqual(after['weights'][6:], before['weights'][6:])
        self.assertFalse(any(t['failed_ticks'] for t in after['tracks']))
        for old, new in zip(before['tracks'], after['tracks']):
            self.assertEqual(gate(old['qa'], new['qa'])[0], [])
        self.assertEqual(build(source, draft, skeleton), result)

    def test_already_passed_and_unknown_rows_keep_exact_original(self):
        source, draft, skeleton = fixture()
        result = build(source, draft, skeleton)
        self.assertFalse(result['records'][0]['selected'])
        self.assertEqual(result['records'][0]['selected_row'], envelope(source, draft, skeleton)['records'][0])
        self.assertEqual(result['records'][0]['trials'], [])
        draft['records'][0]['assignments'][2]['role'] = 'unknown'
        source['draft_sha256'] = canonical_sha256(draft)
        result = build(source, draft, skeleton)
        self.assertEqual(result['records'][0]['selected_row'], envelope(source, draft, skeleton)['records'][0])
        self.assertEqual(result['records'][0]['trials'], [])

    def test_unavailable_residual_is_retained_blocked(self):
        source, draft, skeleton = fixture()
        source['records'].append(dict(layer_id='arm', component_id='low-alpha-residual', mesh=None))
        result = build(source, draft, skeleton)
        self.assertEqual(len(result['records']), 2)
        self.assertEqual(result['records'][1]['component_id'], 'low-alpha-residual')
        self.assertEqual(result['records'][1]['selected_row']['status'], 'blocked')
        self.assertFalse(result['records'][1]['selected'])


if __name__ == '__main__': unittest.main()
