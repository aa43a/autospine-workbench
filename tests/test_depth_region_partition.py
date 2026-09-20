from copy import deepcopy
import unittest

from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.affine_pose import sample


def source():
    doc, files = fixture()
    doc['bones'][0]['name'] = 'chest'
    doc['bones'].append(dict(name='cloth', parent='chest', x=0, y=0, rotation=0))
    for slot in doc['slots']:
        slot['bone'] = 'chest'
    mesh = doc['skins'][0]['attachments']['a']['a']
    mesh['vertices'] = list(mesh['vertices']); mesh['vertices'][16] = 1
    mesh['triangles'] = [0, 1, 2, 0, 2, 3, 0, 1, 2]
    doc['animations']['test'] = dict(bones={'cloth': {'rotate': [dict(time=0, value=0), dict(time=1, value=30)]}},
        attachments={'default': {'a': {'a': {'deform': [dict(time=0, vertices=[0]*8),
                                                     dict(time=1, vertices=[.2]*8)]}}}})
    return doc, files


class DepthRegionPartitionTests(unittest.TestCase):
    def test_order_texture_weights_and_deformation_are_preserved(self):
        doc, _ = source(); original = deepcopy(doc)
        candidate, report = build(doc, ['a'])
        rows = report['regions']
        self.assertEqual([r['group'] for r in rows], ['chest', 'mixed', 'chest'])
        self.assertEqual([t for r in rows for t in r['triangles']], [0, 1, 2])
        self.assertEqual([s['name'] for s in candidate['slots']], [r['slot'] for r in rows]+['b'])
        for time in [0, .5, 1]:
            expected = sample(doc, 'test', time)[0]
            actual = sample(candidate, 'test', time)[0]
            self.assertEqual(actual['b'], expected['b'])
            for row in rows:
                self.assertEqual(actual[row['slot']], expected['a'])
                mesh = candidate['skins'][0]['attachments'][row['slot']][row['slot']]
                self.assertEqual(mesh['path'], 'a')
                self.assertEqual(mesh['uvs'], doc['skins'][0]['attachments']['a']['a']['uvs'])
        self.assertEqual(doc, original)
        self.assertFalse(report['selected'])
        self.assertTrue(all(r['depth_status']=='unassigned' for r in rows))

    def test_unsupported_animation_and_bounds_preserve_source(self):
        doc, _ = source(); original = deepcopy(doc)
        with self.assertRaisesRegex(ValueError, 'part_limit'):
            build(doc, ['a'], part_limit=2)
        self.assertEqual(doc, original)
        for key, value, reason in [('drawOrder', [{'time': 0}], 'existing_order'),
                                  ('slots', {'a': {'attachment': []}}, 'slot_timeline')]:
            altered = deepcopy(doc); altered['animations']['test'][key] = value
            with self.assertRaisesRegex(ValueError, reason):
                build(altered, ['a'])
        doc['slots'].append(dict(name='a-depth-001', bone='chest', attachment='a'))
        with self.assertRaisesRegex(ValueError, 'collision'):
            build(doc, ['a'])


if __name__ == '__main__':
    unittest.main()
