import unittest
from autospine_workbench.targets.character43.material_frontier_sliding import compare, topology


def line(n, offset=0):
    return [dict(edge=[[0, x+offset], [1, x+offset]]) for x in range(n)]


class FrontierSlidingTests(unittest.TestCase):
    def test_tangential_motion_not_mistaken_for_normal_gap(self):
        result = compare(line(3), [[3, 0], [8, 2], [13, 0]], [[0, 0], [5, 0], [10, 0]])
        a, b, c = result['records']
        self.assertEqual(a['fixed_distance_px'], 3)
        self.assertEqual(a['sliding_distance_px'], 0)
        self.assertEqual(b['sliding_distance_px'], 2)
        self.assertEqual(c['sliding_distance_px'], 3)  # Never extend beyond the observed endpoint.
        self.assertFalse(result['selected'])

    def test_other_nearby_component_cannot_attract_query(self):
        samples = line(2)+line(2, 5)
        body = [[0, 0], [1, 0], [0, 10], [1, 10]]
        result = compare(samples, [[0, 10], [1, 0], [0, 10], [1, 10]], body)
        self.assertEqual(len(result['topology']['components']), 2)
        self.assertEqual(result['records'][0]['sliding_distance_px'], 10)

    def test_saddle_cell_is_not_joined_arbitrarily(self):
        samples = [dict(edge=e) for e in (
            [[0, 0], [0, 1]], [[1, 0], [1, 1]], [[0, 0], [1, 0]], [[0, 1], [1, 1]])]
        graph = topology(samples)
        self.assertEqual(graph['ambiguous_cells'], 1)
        self.assertEqual(graph['edges'], [])
        result = compare(samples, [[0, 0]]*4, [[0, 0]]*4)
        self.assertTrue(all(r['sliding_distance_px'] is None for r in result['records']))

    def test_nonfinite_and_invalid_edges_rejected(self):
        with self.assertRaises(ValueError):
            compare(line(2), [[float('nan'), 0], [1, 0]], [[0, 0], [1, 0]])
        with self.assertRaises(ValueError):
            topology([dict(edge=[[0, 0], [1, 1]])])

    def test_filtered_saddle_keeps_ambiguity_from_source_grid(self):
        from autospine_workbench.targets.character43.material_contact_frontier import locate
        samples = locate([[255, 255], [255, 0]], [[255, 0], [0, 255]],
                         [[[0, 0], [1, 0]], [[0, 1], [1, 1]]], [[True]*2]*2, [0, 0], 10)['samples']
        self.assertEqual(len(samples), 2)
        self.assertEqual(topology(samples)['edges'], [])
