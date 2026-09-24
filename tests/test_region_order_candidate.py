from copy import deepcopy
import unittest

from test_depth_region_partition import source
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.region_order_candidate import build


class RegionOrderTests(unittest.TestCase):
    def test_order_only_preserves_multi_influence_sparse_deformation(self):
        doc, _ = source()
        mesh = doc['skins'][0]['attachments']['a']['a']
        mesh['vertices'] = [2, 0, 0, 2, .4, 1, 0, 2, .6] + mesh['vertices'][5:]
        tracks = doc['animations']['test']['attachments']['default']['a']['a']
        tracks['deform'] = [dict(time=0), dict(time=1, offset=2, vertices=[.2, .3, .1, .4])]
        original = deepcopy(doc)
        candidate, report = build(doc, 'a', [0, 2], 'b', 'after')
        self.assertEqual([s['name'] for s in candidate['slots']],
                         ['a-depth-002', 'b', 'a-depth-001', 'a-depth-003'])
        self.assertEqual(sorted(t for r in report['regions'] for t in r['triangles']), [0, 1, 2])
        # The CPU sampler accepts dense deform only; expand test copies, while
        # separately asserting exact sparse tracks in the actual output below.
        def dense(document):
            result = deepcopy(document)
            for attachments in result['animations']['test']['attachments']['default'].values():
                for attachment in attachments.values():
                    for key in attachment['deform']:
                        values = [0.] * 10
                        start = key.pop('offset', 0)
                        raw = key.get('vertices', [])
                        values[start:start + len(raw)] = raw
                        key['vertices'] = values
            return result
        dense_source, dense_candidate = dense(doc), dense(candidate)
        for t in [0, .125, .5, .875, 1]:
            expected = sample(dense_source, 'test', t)[0]
            actual = sample(dense_candidate, 'test', t)[0]
            self.assertEqual(actual['b'], expected['b'])
            for region in report['regions']:
                name = region['slot']
                self.assertEqual(actual[name], expected['a'])
                part = candidate['skins'][0]['attachments'][name][name]
                for key in ('uvs', 'vertices'):
                    self.assertEqual(part[key], mesh[key])
                self.assertEqual(candidate['animations']['test']['attachments']['default'][name][name], tracks)
        self.assertEqual(doc, original)
        self.assertFalse(report['selected'])
        self.assertFalse(report['triangle_order_preserved'])

    def test_before_and_whole_region(self):
        doc, _ = source()
        candidate, _ = build(doc, 'a', [0, 1, 2], 'b', 'before')
        self.assertEqual([s['name'] for s in candidate['slots']], ['a-depth-001', 'b'])

    def test_bad_selection_and_unsupported_order_do_not_mutate(self):
        doc, _ = source(); original = deepcopy(doc)
        for selection in ([], [True], [-1], [3], [0, 0], [0.5]):
            with self.assertRaisesRegex(ValueError, 'triangles_invalid'):
                build(doc, 'a', selection, 'b', 'after')
        for reference, side in [('a', 'after'), ('missing', 'after'), ('b', 'front')]:
            with self.assertRaises(ValueError):
                build(doc, 'a', [0], reference, side)
        self.assertEqual(doc, original)
        doc['animations']['test']['drawOrder'] = [dict(time=0)]
        with self.assertRaisesRegex(ValueError, 'existing_order'):
            build(doc, 'a', [0], 'b', 'after')


if __name__ == '__main__':
    unittest.main()
