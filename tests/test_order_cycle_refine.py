from copy import deepcopy
import unittest

from autospine_workbench.targets.character43.motion_depth_order import build, _sort
from autospine_workbench.targets.character43.order_cycle_refine import compact_cycle, resolve


class Probe:
    def __init__(self, middle_overlap=False, fail=False):
        self.middle_overlap, self.fail = middle_overlap, fail

    def pair(self, a, b, time):
        if {a, b} == {'cloth', 'body'}:
            if self.fail:
                raise ValueError('depth_overlap_pixel_budget')
            return dict(overlap_pixels=int(self.middle_overlap and time == .05))
        return dict(overlap_pixels=1)


class CycleRefinementTests(unittest.TestCase):
    def setup_case(self):
        doc = dict(slots=[dict(name=n) for n in ['arm', 'cloth', 'body']], animations={'test': {}})
        depth = dict(pairs=[dict(arm_slot='arm', torso_slot='body', samples=[
            dict(tick=t, current_front_slot='arm', ambiguous=False) for t in [0, 100000]])])
        return doc, depth

    def test_disjoint_constraint_can_move_without_changing_visible_order(self):
        doc, depth = self.setup_case(); original = deepcopy(doc)
        self.assertIsNone(build(doc, 'test', depth, Probe())[0])
        candidate, report = build(doc, 'test', depth, Probe(), refine_cycles=True)
        self.assertIsNotNone(candidate)
        self.assertEqual(report['frames'][0]['order'], ['body', 'arm', 'cloth'])
        self.assertEqual(report['cycle_refinements'][0]['removed'][0]['times'], [0, .05])
        self.assertEqual(doc, original)
        self.assertFalse(report['selected'])

    def test_midpoint_overlap_keeps_cycle_and_budget_failure_abstains(self):
        doc, depth = self.setup_case()
        for probe, reason in [(Probe(True), 'visible_unmapped_order_conflict'),
                              (Probe(fail=True), 'depth_overlap_pixel_budget')]:
            candidate, report = build(doc, 'test', depth, probe, refine_cycles=True)
            self.assertIsNone(candidate)
            self.assertIn(reason, report['reason_codes'])

    def test_compact_cycle_uses_existing_edges_and_remains_closed(self):
        slots = ['a', 'b', 'c', 'd']
        evidence = {edge: dict(source='preserved_setup_order') for edge in
                    [('a', 'b'), ('b', 'c'), ('c', 'd'), ('a', 'd'), ('d', 'a')]}
        cycle = compact_cycle(slots, evidence)
        self.assertEqual(cycle['slots'], ['a', 'd', 'a'])
        for row in cycle['edges']:
            self.assertIn((row['back'], row['front']), evidence)
        order, audit = resolve(slots, set(evidence), deepcopy(evidence), Probe(), [0], _sort, check_limit=0)
        self.assertIsNone(order)
        self.assertEqual(audit['reason_code'], 'depth_cycle_check_limit')


if __name__ == '__main__':
    unittest.main()
