from copy import deepcopy
import unittest

from autospine_workbench.targets.character43.motion_depth_order import build


class FakeProbe:
    def __init__(self, visible): self.visible = visible
    def pair(self, a, b, time):
        return dict(overlap_pixels=int(frozenset((a, b)) in self.visible))


class DepthOrderTests(unittest.TestCase):
    def make(self, middle=False, ambiguous=False):
        names = ['arm', 'unknown', 'body'] if middle else ['arm', 'body']
        doc = dict(slots=[dict(name=n) for n in names], animations={'test': {}})
        depth = dict(pairs=[dict(arm_slot='arm', torso_slot='body', samples=[
            dict(tick=t, current_front_slot='arm', ambiguous=ambiguous) for t in (0, 100000)])])
        return doc, depth

    def test_adjacent_order_changes_only_animation(self):
        doc, depth = self.make(); original = deepcopy(doc)
        candidate, report = build(doc, 'test', depth, FakeProbe({frozenset(('arm', 'body'))}))
        self.assertEqual(doc, original)
        self.assertEqual(report['frames'][0]['order'], ['body', 'arm'])
        self.assertEqual(candidate['animations']['test']['drawOrder'][0]['offsets'],
                         [dict(slot='arm', offset=1), dict(slot='body', offset=-1)])
        self.assertFalse(report['selected'])

    def test_unknown_visible_crossing_and_straddle_are_not_adopted(self):
        doc, depth = self.make(middle=True)
        visible = {frozenset(('arm', 'body')), frozenset(('arm', 'unknown'))}
        candidate, report = build(doc, 'test', depth, FakeProbe(visible))
        self.assertIsNone(candidate)
        self.assertIn('visible_unmapped_order_conflict', report['reason_codes'])
        conflict = report['failures'][0]['conflict']
        self.assertEqual(conflict['slots'], ['arm', 'unknown', 'body', 'arm'])
        self.assertEqual([e['source'] for e in conflict['edges']],
                         ['visible_setup_order', 'preserved_setup_order', 'source_depth'])
        self.assertEqual(conflict['edges'][0]['overlap'], dict(time=0, overlap_pixels=1))
        self.assertNotIn('overlap', conflict['edges'][1])
        doc, depth = self.make(ambiguous=True)
        self.assertIsNone(build(doc, 'test', depth, FakeProbe(visible))[0])

    def test_cycle_witness_handles_long_graph_without_recursion(self):
        from autospine_workbench.targets.character43.order_conflict import witness
        slots = [str(i) for i in range(2000)]
        evidence = {(a, b): dict(source='test') for a, b in zip(slots, slots[1:])}
        self.assertIsNone(witness(slots, evidence))
        evidence[slots[-1], slots[-3]] = dict(source='test')
        self.assertEqual(witness(slots, evidence)['slots'], slots[-3:] + [slots[-3]])

    def test_transparent_crossing_is_allowed_and_disjoint_pair_does_not_change(self):
        doc, depth = self.make(middle=True)
        candidate, report = build(doc, 'test', depth, FakeProbe({frozenset(('arm', 'body'))}))
        self.assertIsNotNone(candidate)
        self.assertEqual(report['frames'][0]['order'], ['unknown', 'body', 'arm'])
        candidate, report = build(doc, 'test', depth, FakeProbe(set()))
        self.assertEqual(candidate, doc)
        self.assertEqual(report['status'], 'no_visible_order_change')


if __name__ == '__main__':
    unittest.main()
