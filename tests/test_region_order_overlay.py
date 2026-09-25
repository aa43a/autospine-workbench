from copy import deepcopy
import struct
import unittest

from test_depth_region_partition import source
from autospine_workbench.spine42_draw_order_offsets import (
    apply_spine42_draw_order_offsets as decode,
    encode_spine42_draw_order_offsets as encode,
)
from autospine_workbench.targets.character43.region_order_candidate import build


def order(doc, animation, time):
    names = [s['name'] for s in doc['slots']]
    result = names
    for key in doc['animations'][animation].get('drawOrder', []):
        tick = struct.unpack('<f', struct.pack('<f', key.get('time', 0)))[0]
        if tick <= time:
            result = list(decode(names, key.get('offsets', [])))
    return result


class OverlayTests(unittest.TestCase):
    def fixture(self):
        doc, _ = source()
        doc['slots'].append(dict(name='c', bone='chest', attachment='c'))
        doc['skins'][0]['attachments']['c'] = {'c': deepcopy(doc['skins'][0]['attachments']['b']['b'])}
        names = ['a', 'b', 'c']
        doc['animations']['test']['drawOrder'] = [
            dict(offsets=encode(names, ['c', 'a', 'b'])),
            dict(time=.5, offsets=encode(names, ['b', 'c', 'a'])),
            dict(time=.75, offsets=encode(names, ['c', 'b', 'a'])),
            dict(time=.875, offsets=[])]
        doc['animations']['other'] = deepcopy(doc['animations']['test'])
        return doc

    def test_preserve_outside_and_compose_every_source_change(self):
        doc = self.fixture(); original = deepcopy(doc)
        result, report = build(doc, 'a', [0, 2], 'b', 'after', animation='test', interval=[.25, .75])
        parts = ['a-depth-001', 'a-depth-002', 'a-depth-003']
        selected = {parts[0], parts[2]}
        for time in [0, .2499, .25, .4999, .5, .7499, .75, .8, .875, 1]:
            base = [p for name in order(doc, 'test', time) for p in (parts if name == 'a' else [name])]
            expected = list(base)
            if .25 <= time < .75:
                moving = [n for n in base if n in selected]
                expected = [n for n in base if n not in selected]
                index = expected.index('b') + 1
                expected[index:index] = moving
            self.assertEqual(order(result, 'test', time), expected)
            self.assertEqual(order(result, 'other', time), base)
        self.assertEqual(doc, original)
        self.assertEqual(report['source_order_keys_composed'], 4)
        self.assertEqual([k.get('time', 0) for k in result['animations']['test']['drawOrder']],
                         [0, .25, .5, .75, .875])
        self.assertNotIn('time', result['animations']['test']['drawOrder'][0])
        self.assertEqual(result['animations']['test']['bones'], doc['animations']['test']['bones'])

    def test_runtime_coincident_boundary_is_one_key_and_restores_current_order(self):
        doc = self.fixture()
        doc['animations']['test']['drawOrder'] = [dict(time=.1, offsets=[])]
        result, _ = build(doc, 'a', [0], 'b', 'before', animation='test', interval=[.100000001, .5])
        keys = result['animations']['test']['drawOrder']
        self.assertEqual([k['time'] for k in keys], [.1, .5])
        self.assertEqual(order(result, 'test', .5), [s['name'] for s in result['slots']])

    def test_invalid_source_timeline_fails_without_mutation(self):
        doc = self.fixture()
        doc['animations']['test']['drawOrder'] = [dict(time=.5), dict(time=.500000001)]
        original = deepcopy(doc)
        with self.assertRaisesRegex(ValueError, 'time_collision'):
            build(doc, 'a', [0], 'b', 'after', animation='test', interval=[0, 1])
        self.assertEqual(doc, original)


if __name__ == '__main__':
    unittest.main()
